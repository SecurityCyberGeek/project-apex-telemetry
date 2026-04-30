#!/usr/bin/env python3
#  Copyright 2026 Timothy D. Harmon
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  You may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""
PROJECT APEX: ACTIVE AERO & INTEGRITY VALIDATION SERVICE (PRODUCTION)
---------------------------------------------------------------------
Context: F1 2026 Technical Regulations (MCL40)
Deployment: Cisco IOx Edge Compute / MTC Mission Control
Author: Timothy D. Harmon, CISSP

DESCRIPTION:
This service acts as the 'Edge Brain' for the Project Apex framework.
It consumes high-frequency (60 Hz) UDP telemetry from the ATLAS forwarder
and computes vertical energy, thermal mode, and basic integrity severity.

DYNAMIC MASS MODEL:
Vertical energy is computed using real-time car mass:
    E = 0.5 * (CAR_MIN_MASS_KG + fuel_load_kg) * vz²

This reflects 2026 F1 physics accurately:
    - Minimum car mass:  768.0 kg (2026 FIA Technical Regulations)
    - Full fuel load:   +100.0 kg at race start
    - Race start mass:   868.0 kg → E_anomaly = 212.7 J
    - Race end mass:     768.0 kg → E_anomaly = 188.2 J

Heavier cars at the race start produce higher vertical energy at the same
vertical velocity, correctly triggering RED/YELLOW thresholds sooner
when tyre grip is lower and the car is most vulnerable.

CHANGE LOG:
v1.0   (March 2026)  - Initial production release
v1.1   (March 2026)  - CORRECTED: CAR_MASS_KG 798.0 → 768.0 kg
v1.1.1 (March 2026)  - BUGFIX: HIGH_COMPRESSION/nominal-energy branch now
                       correctly sets compliance_status = 'WARNING: ELEVATED_TEMP'
v1.2   (March 2026)  - FEATURE: Dynamic mass model. PACKET_FORMAT updated
                       from '<d10sffff' (34 bytes) to '<d10sfffff' (38 bytes)
                       to include fuel_load_kg as field [6]. Vertical energy
                       now reflects the actual car mass at each moment in the race.
                       Emits dynamic_mass_kg and fuel_load_kg to Splunk.
"""

import socket
import struct
import time
import requests
import logging
import urllib3
import threading
import queue
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ApexValidator")

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIGURATION ---
SPLUNK_HEC_URL = os.getenv("SPLUNK_HEC_URL", "https://splunk-hec.mclaren.internal:8088/services/collector/event")
SPLUNK_TOKEN = os.getenv("SPLUNK_TOKEN", "REPLACE_WITH_SECURE_TOKEN")
LISTEN_IP = os.getenv("LISTEN_IP", "0.0.0.0")
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "20777"))

# --- PACKET FORMAT (v1.2) ---
# Field order: timestamp(d), car_id(10s), speed_kph(f), ride_height_mm(f),
#              vert_vel_ms(f), engine_temp_c(f), fuel_load_kg(f)
PACKET_FORMAT = "<d10sfffff"
PACKET_SIZE   = struct.calcsize(PACKET_FORMAT)  # 38 bytes

# --- PHYSICS CONSTANTS (2026 FIA F1 Technical Regulations) ---
CAR_MIN_MASS_KG        = 768.0   # Minimum car + driver mass, no fuel (2026 regs)
MAX_FUEL_LOAD_KG       = 100.0   # Maximum permitted fuel load at race start
THERMAL_THRESHOLD_C    = 130.0   # High-compression regime threshold
ENERGY_LIMIT_J         = 100.0   # Nominal vertical oscillation limit
THERMAL_ENERGY_LIMIT_J = 80.0    # Reduced limit under high thermal load
AERO_STALL_RH_MM       = 28.0    # Rear ride height stall-risk threshold

# ─────────────────────────────────────────────────────────────────────────────
# FIA 2026 REGULATORY REFINEMENTS (ERS / ENERGY MANAGEMENT)
# Source: FIA / FOM stakeholder agreement, April 19–20 2026
# These constants are configured only in v1.2.
# They do NOT alter GREEN/YELLOW/RED severity yet; ERS-aware logic will be
# introduced in a future backward-compatible release.[web:1709][web:1708]
# ─────────────────────────────────────────────────────────────────────────────
ERS_MAX_RECHARGE_MJ: float           = 7.0    # Max permitted recharge per lap (reduced from 8 MJ)
ERS_DEPLOY_ACCEL_KW: float           = 350.0  # MGU-K in key acceleration/overtaking zones
ERS_DEPLOY_NON_ACCEL_KW: float       = 250.0  # MGU-K limit in other parts of the lap
ERS_BOOST_CAP_KW: float              = 150.0  # Max additional Boost in race conditions
ERS_SUPERCLIP_MAX_DURATION_S: float  = 4.0    # Target upper bound of superclip duration per lap (2–4 s window)

# In future, optional ERS telemetry fields (ers_deploy_kw, ers_recharge_mj,
# ers_superclip_duration_s, in_acceleration_zone) will be evaluated against
# these constants, and logged as ERS compliance status, separate from severity.

# NOTE (v1.2 compatibility contract):
# - ERS_* constants are configuration-only in v1.2 and are intentionally not
#   wired into GREEN/YELLOW/RED severity classification.
# - A future release may add an ERS compliance layer that runs in parallel with
#   existing vertical-energy severity logic, without changing current behavior.
# - Any ERS telemetry inputs must remain optional so older packet streams stay
#   backward-compatible.

PACKET_QUEUE = queue.Queue(maxsize=2048)
http_session = requests.Session()

last_success_log_time = 0.0
last_error_log_time   = 0.0
QUEUE_FULL_WARNING_COOLDOWN = 0.0


def calculate_vertical_energy(vz: float, fuel_load_kg: float) -> float:
    """
    Compute the vertical energy using the car's dynamic mass.

    E = 0.5 * (CAR_MIN_MASS_KG + fuel_load_kg) * vz²

    Dynamic mass reflects actual race conditions:
      - Race start (100 kg fuel): mass = 868.0 kg → higher energy, earlier threshold
      - Race end   (  0 kg fuel): mass = 768.0 kg → lower energy, later threshold
    """
    fuel_clamped = max(0.0, min(fuel_load_kg, MAX_FUEL_LOAD_KG))
    dynamic_mass = CAR_MIN_MASS_KG + fuel_clamped
    return 0.5 * dynamic_mass * (vz ** 2)


def classify_event(engine_temp: float, energy_joules: float, ride_height: float):
    """
    Classify a telemetry packet into a severity state.
    
    compliance_status MUST be explicitly set in every non-GREEN branch.
    It drives Event Stream row background coloring in Splunk Dashboard Studio
    via matchValue(). Leaving it as 'LEGAL' in any YELLOW branch causes
    those events to render as green rows.
    """
    compliance_status = "LEGAL"
    apex_severity     = "GREEN"
    apex_status       = "WITHIN_SPEC"
    apex_message      = "Within expected physics envelope."
    thermal_mode      = "STANDARD"
    squat_detected    = False

    if engine_temp > THERMAL_THRESHOLD_C:
        thermal_mode   = "HIGH_COMPRESSION"
        squat_detected = ride_height < AERO_STALL_RH_MM

        if energy_joules > THERMAL_ENERGY_LIMIT_J and squat_detected:
            compliance_status = "CRITICAL: TORQUE_ANOMALY_CONFIRMED"
            apex_severity     = "RED"
            apex_status       = "ANOMALY_DETECTED"
            apex_message      = (
                "High engine temp, high vertical energy, and aero squat detected "
                "(torque anomaly)."
            )
        elif energy_joules > THERMAL_ENERGY_LIMIT_J:
            compliance_status = "WARNING: TORQUE_ANOMALY_UNCONFIRMED"
            apex_severity     = "YELLOW"
            apex_status       = "TRENDING"
            apex_message      = (
                "High engine temp and elevated vertical energy; monitor for torque anomaly."
            )
        else:
            compliance_status = "WARNING: ELEVATED_TEMP"
            apex_severity     = "YELLOW"
            apex_status       = "TRENDING"
            apex_message      = (
                "Engine temperature above nominal; monitor vertical energy and ride height."
            )
    else:
        if energy_joules > ENERGY_LIMIT_J:
            compliance_status = "VIOLATION_RISK"
            apex_severity     = "YELLOW"
            apex_status       = "TRENDING"
            apex_message      = (
                "Vertical energy above nominal limit; monitor for oscillation risk."
            )

    return compliance_status, apex_severity, apex_status, apex_message, thermal_mode


def send_to_splunk(payload: dict, car_id: str) -> None:
    global last_success_log_time, last_error_log_time

    if SPLUNK_TOKEN == "REPLACE_WITH_SECURE_TOKEN":
        current_time = time.time()
        if current_time - last_error_log_time >= 5.0:
            logger.warning("Security alert: default Splunk token in use. Set SPLUNK_TOKEN env var.")
            last_error_log_time = current_time
        return

    try:
        response = http_session.post(SPLUNK_HEC_URL, json=payload, verify=False, timeout=0.5)
        if response.status_code == 200:
            current_time = time.time()
            if current_time - last_success_log_time >= 60.0:
                logger.info(f"SUCCESS → Splunk ingestion active (heartbeat 60s) | Last car: {car_id}")
                last_success_log_time = current_time
        else:
            current_time = time.time()
            if current_time - last_error_log_time >= 5.0:
                logger.error(f"Splunk HEC rejection: {response.text}")
                last_error_log_time = current_time
    except Exception as e:
        current_time = time.time()
        if current_time - last_error_log_time >= 5.0:
            logger.warning(f"HEC connection failed: {e}")
            last_error_log_time = current_time


def processing_worker() -> None:
    """Read packets from queue, parse physics with dynamic mass, send to Splunk."""
    while True:
        try:
            data = PACKET_QUEUE.get(timeout=1.0)
        except queue.Empty:
            continue

        try:
            if len(data) != PACKET_SIZE:
                PACKET_QUEUE.task_done()
                continue

            unpacked     = struct.unpack(PACKET_FORMAT, data)
            timestamp    = unpacked[0]
            raw_car_id   = unpacked[1]
            car_id       = raw_car_id.decode("utf-8", errors="ignore").strip("\x00")
            speed        = unpacked[2]
            ride_height  = unpacked[3]
            vert_vel     = unpacked[4]
            engine_temp  = unpacked[5]
            fuel_load_kg = unpacked[6]

            fuel_clamped = max(0.0, min(fuel_load_kg, MAX_FUEL_LOAD_KG))
            dynamic_mass = CAR_MIN_MASS_KG + fuel_clamped
            energy_joules = calculate_vertical_energy(vert_vel, fuel_load_kg)

            (
                compliance_status,
                apex_severity,
                apex_status,
                apex_message,
                thermal_mode,
            ) = classify_event(engine_temp, energy_joules, ride_height)

            logger.debug(
                "classification_decision car_id=%s engine_temp_c=%.1f rear_rh_mm=%.2f "
                "fuel_load_kg=%.2f dynamic_mass_kg=%.1f vertical_energy_j=%.2f "
                "compliance_status=%s apex_severity=%s apex_status=%s thermal_mode=%s",
                car_id,
                engine_temp,
                ride_height,
                fuel_clamped,
                dynamic_mass,
                energy_joules,
                compliance_status,
                apex_severity,
                apex_status,
                thermal_mode,
            )

            telemetry_event = {
                "time":       timestamp,
                "host":       socket.gethostname(),
                "source":     "atlas_edge_bridge",
                "sourcetype": "mcl_telemetry",
                "index":      "project_apex",
                "event": {
                    "car_id":           car_id,
                    "sensor_id":        "VERT_PLATFORM",
                    "speed_kph":        int(round(speed)),
                    "vertical_energy":  round(energy_joules, 2),
                    "engine_temp_c":    round(engine_temp, 1),
                    "rear_rh_mm":       round(ride_height, 2),
                    "fuel_load_kg":     round(fuel_clamped, 2),
                    "dynamic_mass_kg":  round(dynamic_mass, 1),
                    "compliance_status": compliance_status,
                    "thermal_mode":      thermal_mode,
                    "apex_severity":     apex_severity,
                    "apex_status":       apex_status,
                    "apex_message":      apex_message,
                    # Future: ERS telemetry fields and ers_compliance will be added here.
                },
            }

            send_to_splunk(telemetry_event, car_id)
            PACKET_QUEUE.task_done()

        except Exception as e:
            logger.error(f"Worker exception: {e}")
            PACKET_QUEUE.task_done()


def main() -> None:
    global QUEUE_FULL_WARNING_COOLDOWN

    http_session.headers.update(
        {
            "Authorization": f"Splunk {SPLUNK_TOKEN}",
            "Content-Type": "application/json",
        }
    )

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((LISTEN_IP, LISTEN_PORT))
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)

    logger.info(f"Project Apex Validator v1.2 active on {LISTEN_IP}:{LISTEN_PORT}")
    logger.info(f"Physics: DYNAMIC MASS | CAR_MIN={CAR_MIN_MASS_KG} kg + fuel_load_kg")
    logger.info(
        "Mass range: %.1f kg (empty) → %.1f kg (full fuel)",
        CAR_MIN_MASS_KG,
        CAR_MIN_MASS_KG + MAX_FUEL_LOAD_KG,
    )
    logger.info(f"Packet size: {PACKET_SIZE} bytes | Format: {PACKET_FORMAT}")

    worker = threading.Thread(target=processing_worker, daemon=True)
    worker.start()

    while True:
        try:
            data, _ = sock.recvfrom(1024)
            try:
                PACKET_QUEUE.put_nowait(data)
            except queue.Full:
                current_time = time.time()
                if current_time - QUEUE_FULL_WARNING_COOLDOWN >= 5.0:
                    logger.warning("QUEUE FULL: dropping packets.")
                    QUEUE_FULL_WARNING_COOLDOWN = current_time
        except KeyboardInterrupt:
            logger.info("Stopping validator service...")
            http_session.close()
            break
        except Exception as e:
            logger.error(f"Main loop exception: {e}")
            continue


if __name__ == "__main__":
    main()