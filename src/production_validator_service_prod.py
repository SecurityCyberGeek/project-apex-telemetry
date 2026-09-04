#!/usr/bin/env python3
#  Copyright 2026 Timothy D. Harmon
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
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
and computes vertical energy, thermal mode, and integrity severity.

This version also integrates governance anomaly detection for pit-lane
configuration / timing anomalies, enriches Splunk payloads with TD versioning
and governance metadata, and triggers evidence package generation for severe
findings that may warrant review.

DYNAMIC MASS MODEL:
Vertical energy is computed using real-time car mass:
    E = 0.5 * (CAR_MIN_MASS_KG + fuel_load_kg) * vz²
    
Where DYNAMIC_MASS_BASE_KG is derived from FIA 2026 Section C Article C4.1
minimum-mass offsets (currently using the "other sessions" 724 kg offset
as a baseline, excluding Nominal Tyre Mass for modelling purposes).
"""

import copy
import hashlib
import logging
import os
import queue
import socket
import struct
import threading
import time
from collections import deque
from typing import Deque, Dict, List, Optional

import requests
import urllib3

from config import load_td_config, load_governance_config
from governance_anomaly_detector import (
    detect_pitlane_configuration_anomalies,
    PenaltyEvent,
    TimingLoop,
)
from governance_evidence_package import (
    build_evidence_package,
    record_evidence_package_event,
)

# Regulation constants (centralized in regulations_2026.py)
from regulations_2026 import (
    REGULATION_VERSION,
    # Mass offsets and Heat Hazard increments (Section C4).
    MIN_MASS_OFFSET_QUALI_KG,
    MIN_MASS_OFFSET_OTHER_KG,
    HEAT_HAZARD_INCREASE_TTCS_KG,
    HEAT_HAZARD_INCREASE_OTHER_KG,
    # Power unit / ERS limits (Section C5.2).
    ES_MAX_SOC_DELTA_MJ,
    ERS_K_MAX_POWER_KW,
    ERS_RECHARGE_BASE_LIMIT_MJ,
    ERS_RECHARGE_LOW_ENERGY_LIMIT_MJ,
    ERS_RECHARGE_QUALI_REDUCED_MIN_MJ,
    ERS_ADDITIONAL_HARVEST_MJ,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ApexValidator")

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIGURATION ---
SPLUNK_HEC_URL = os.getenv(
    "SPLUNK_HEC_URL",
    "https://splunk-hec.mclaren.internal:8088/services/collector/event"
)
SPLUNK_TOKEN = os.getenv("SPLUNK_TOKEN", "REPLACE_WITH_SECURE_TOKEN")
LISTEN_IP = os.getenv("LISTEN_IP", "0.0.0.0")
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "20777"))

# Governance / TD config loaded once at startup
td_cfg = load_td_config()
gov_cfg = load_governance_config()

CURRENT_TD_VERSION = getattr(td_cfg, "td_version", "UNKNOWN_TD")
RIGHT_OF_REVIEW_THRESHOLD = getattr(gov_cfg, "right_of_review_severity_threshold", "HIGH")
INCIDENT_SALT = os.getenv("APEX_INCIDENT_SALT", "project_apex_2026")

# --- PACKET FORMAT (v1.2) ---
PACKET_FORMAT = "<d10sfffff"
PACKET_SIZE = struct.calcsize(PACKET_FORMAT)

# --- APEX MODEL CONSTANTS (NOT DIRECT FIA LIMITS) ---
# These are thresholds used by the validator’s physics/anomaly model. They are
# tuned against Section C behaviour but are not themselves Article values.
MAX_FUEL_LOAD_KG = 100.0          # model cap for fuel load in dynamic mass / energy
THERMAL_THRESHOLD_C = 130.0       # engine temp threshold for "HIGH_COMPRESSION" mode
ENERGY_LIMIT_J = 100.0            # nominal vertical energy envelope upper bound
THERMAL_ENERGY_LIMIT_J = 80.0     # elevated vertical energy threshold under high temp
AERO_STALL_RH_MM = 28.0           # rear ride height indicating aero squat risk

PACKET_QUEUE = queue.Queue(maxsize=2048)
http_session = requests.Session()

last_success_log_time = 0.0
last_error_log_time = 0.0
QUEUE_FULL_WARNING_COOLDOWN = 0.0

# Recent governance context buffers
RECENT_PENALTIES: Deque[PenaltyEvent] = deque(maxlen=128)
RECENT_TIMING_LOOPS: Deque[TimingLoop] = deque(maxlen=256)

# ---------------------------------------------------------------------------
# Regulation helpers – mass and ERS limits based on FIA Section C Issue 20
# ---------------------------------------------------------------------------

def get_minimum_mass_offset_kg(session_type: str, heat_hazard: bool) -> float:
    """
    Compute the minimum mass offset (excluding Nominal Tyre Mass) for a given
    F1 session type and Heat Hazard status.

    Implements Article C4.1 (Minimum mass) and C4.6 (Heat Hazard Mass Increase)
    from FIA 2026 F1 Regulations – Section C [Technical], Issue 20.[file:475]

    session_type:
        - 'SQ' : Sprint Qualifying
        - 'Q'  : Qualifying
        - 'R'  : Race
        - 'S'  : Sprint
        - 'FP' : Free Practice (or 'FP1', 'FP2', etc.)
    heat_hazard:
        - True if a Heat Hazard has been declared for the relevant TTCS /
          Competition; False otherwise.[file:475]
    """
    # Qualifying and Sprint Qualifying use the 726 kg + Nominal Tyre Mass base (C4.1).[file:475]
    if session_type in {"SQ", "Q"}:
        base = MIN_MASS_OFFSET_QUALI_KG
    else:
        # All other sessions use the 724 kg + Nominal Tyre Mass base (C4.1).[file:475]
        base = MIN_MASS_OFFSET_OTHER_KG

    if not heat_hazard:
        return base

    # Heat Hazard mass increase depends on session type per Article C4.6.[file:475]
    if session_type in {"SQ", "Q"}:  # TTCS sessions
        return base + HEAT_HAZARD_INCREASE_TTCS_KG
    else:
        return base + HEAT_HAZARD_INCREASE_OTHER_KG


def validate_car_mass(
    car_mass_kg: float,
    nominal_tyre_mass_kg: float,
    session_type: str,
    heat_hazard: bool,
) -> None:
    """
    Optional validator for car mass against FIA 2026 Section C Article C4.1/C4.6.[file:475]

    This is provided for use when Apex has access to scrutineering or detailed
    mass data (car mass + Nominal Tyre Mass). It is *not* currently wired into
    the live UDP telemetry pipeline, which does not carry full car mass.[file:476]

    Raises:
        ValueError if the car mass is below the computed minimum mass.
    """
    min_offset = get_minimum_mass_offset_kg(session_type, heat_hazard)
    min_mass_required = min_offset + nominal_tyre_mass_kg  # C4.1.[file:475]

    if car_mass_kg < min_mass_required:
        raise ValueError(
            (
                f"Car mass {car_mass_kg:.3f} kg below FIA minimum "
                f"{min_mass_required:.3f} kg for session {session_type} "
                f"(Section C4.1/C4.6 baseline {REGULATION_VERSION})."
            )
        )


def get_ers_recharge_limit_mj(
    session_type: str,
    low_energy_circuit: bool,
) -> float:
    """
    Compute the ERS-K recharge limit per lap at the CU-K HV DC Bus in MJ.

    Implements Article C5.2.10 from FIA 2026 Section C [Technical] Issue 20,
    combined with Sporting context (low-energy circuits / power-limited
    periods) defined via Article B7.2 and the 2026 refinements summary.[file:475][web:84]

    Logic:
      - Base limit: 8.5MJ per lap (Race/Sprint).[file:475]
      - Reduced limit: 7MJ per lap at certain competitions where FIA determines
        maximum possible harvested energy per lap is no more than 7MJ (C5.2.10 i).[file:475][web:84]
      - Further reduced limits for Sprint Qualifying and Qualifying (C5.2.10 ii);
        the exact value must be set in ERS_RECHARGE_QUALI_REDUCED_MIN_MJ once
        confirmed from the official PDF or FIA guidance.[file:475]
    """
    limit = ERS_RECHARGE_BASE_LIMIT_MJ

    if low_energy_circuit:
        limit = ERS_RECHARGE_LOW_ENERGY_LIMIT_MJ

    if session_type in {"SQ", "Q"} and ERS_RECHARGE_QUALI_REDUCED_MIN_MJ is not None:
        limit = ERS_RECHARGE_QUALI_REDUCED_MIN_MJ

    return limit


def validate_ers_recharge(
    recharge_mj: float,
    session_type: str,
    low_energy_circuit: bool,
) -> None:
    """
    Optional validator for ERS-K recharge per lap against FIA 2026 Section C
    Article C5.2.10.[file:475][web:84]

    This helper is intended for batch or offline analysis where Apex can
    aggregate lap-wise ERS recharge data – the live UDP pipeline in this
    service currently does not carry ERS fields.
    """
    limit_mj = get_ers_recharge_limit_mj(session_type, low_energy_circuit)
    if recharge_mj > limit_mj:
        raise ValueError(
            (
                f"ERS recharge {recharge_mj:.3f} MJ exceeds limit "
                f"{limit_mj:.3f} MJ for session {session_type} "
                f"(Section C5.2.10 baseline {REGULATION_VERSION})."
            )
        )


# ---------------------------------------------------------------------------
# Core physics / anomaly classification
# ---------------------------------------------------------------------------

def calculate_vertical_energy(vz: float, fuel_load_kg: float) -> float:
    """
    Compute vertical energy using a dynamic mass envelope.

    The model clamps fuel to [0, MAX_FUEL_LOAD_KG] and uses:
        dynamic_mass = DYNAMIC_MASS_BASE_KG + fuel_clamped
        energy = 0.5 * dynamic_mass * vz²

    DYNAMIC_MASS_BASE_KG is derived from Section C Article C4.1 offsets and
    represents a simplified chassis mass baseline (excluding Nominal Tyre Mass).
    """
    fuel_clamped = max(0.0, min(fuel_load_kg, MAX_FUEL_LOAD_KG))
    dynamic_mass = CAR_MIN_MASS_KG + fuel_clamped
    return 0.5 * dynamic_mass * (vz ** 2)


def classify_event(engine_temp: float, energy_joules: float, ride_height: float):
    """
    Classify the current telemetry frame into a compliance status and Apex severity.
    
    Uses:
    - THERMAL_THRESHOLD_C to detect high-compression / heat-hazard-like modes.
    - THERMAL_ENERGY_LIMIT_J and ENERGY_LIMIT_J to bound vertical energy.
    - AERO_STALL_RH_MM as a proxy for aero squat.
    """
    compliance_status = "LEGAL"
    apex_severity = "GREEN"
    apex_status = "WITHIN_SPEC"
    apex_message = "Within expected physics envelope."
    thermal_mode = "STANDARD"
    squat_detected = False

    if engine_temp > THERMAL_THRESHOLD_C:
        thermal_mode = "HIGH_COMPRESSION"
        squat_detected = ride_height < AERO_STALL_RH_MM

        if energy_joules > THERMAL_ENERGY_LIMIT_J and squat_detected:
            compliance_status = "CRITICAL: TORQUE_ANOMALY_CONFIRMED"
            apex_severity = "RED"
            apex_status = "ANOMALY_DETECTED"
            apex_message = (
                "High engine temp, high vertical energy, and aero squat detected "
                "(torque anomaly)."
            )
        elif energy_joules > THERMAL_ENERGY_LIMIT_J:
            compliance_status = "WARNING: TORQUE_ANOMALY_UNCONFIRMED"
            apex_severity = "YELLOW"
            apex_status = "TRENDING"
            apex_message = (
                "High engine temp and elevated vertical energy; monitor for torque anomaly."
            )
        else:
            compliance_status = "WARNING: ELEVATED_TEMP"
            apex_severity = "YELLOW"
            apex_status = "TRENDING"
            apex_message = (
                "Engine temperature above nominal; monitor vertical energy and ride height."
            )
    else:
        if energy_joules > ENERGY_LIMIT_J:
            compliance_status = "VIOLATION_RISK"
            apex_severity = "YELLOW"
            apex_status = "TRENDING"
            apex_message = (
                "Vertical energy above nominal limit; monitor for oscillation risk."
            )

    return compliance_status, apex_severity, apex_status, apex_message, thermal_mode

# ---------------------------------------------------------------------------
# Governance helpers
# ---------------------------------------------------------------------------

def build_incident_id(
    category: str,
    car_id: str,
    timestamp: float,
    loop_name: str = "unknown",
    severity: str = "INFO",
) -> str:
    incident_window = int(timestamp // 30)
    raw = f"{INCIDENT_SALT}|{category}|{car_id}|{loop_name}|{severity}|{incident_window}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"APEX-{category[:6].upper()}-{digest}"


def severity_meets_threshold(severity: str, threshold: str) -> bool:
    order = {
        "INFO": 1,
        "LOW": 2,
        "MEDIUM": 3,
        "HIGH": 4,
        "CRITICAL": 5,
    }
    return order.get(str(severity).upper(), 0) >= order.get(str(threshold).upper(), 999)


def extract_governance_inputs_from_packet(
    timestamp: float,
    car_id: str,
    speed: float,
    ride_height: float,
    vert_vel: float,
    engine_temp: float,
):
    penalties: List[PenaltyEvent] = []
    loops: List[TimingLoop] = []
    
    # Basic pit-lane speed risk proxy 
    if speed > 80.0:
        penalty_candidate = PenaltyEvent(
            car_id=car_id,
            timestamp=timestamp,
            penalty_type="PITLANE_SPEEDING_RISK",
            measured_value=float(speed),
            threshold_value=80.0,
            description=f"Potential pit-lane over-speed observed at {speed:.1f} kph.",
        )
        penalties.append(penalty_candidate)
        RECENT_PENALTIES.append(penalty_candidate)

    inferred_loop_state = "OK"
    if ride_height < AERO_STALL_RH_MM and engine_temp > THERMAL_THRESHOLD_C:
        inferred_loop_state = "SUSPECT"

    loop_event = TimingLoop(
        loop_id=f"pitloop_{car_id}",
        timestamp=timestamp,
        status=inferred_loop_state,
        measured_latency_ms=abs(vert_vel) * 10.0,
        expected_latency_ms=5.0,
        description=(
            "Synthetic timing-loop observation derived from current telemetry frame "
            "for governance correlation."
        ),
    )
    loops.append(loop_event)
    RECENT_TIMING_LOOPS.append(loop_event)

    return penalties, loops


def build_base_event(
    timestamp: float,
    car_id: str,
    speed: float,
    energy_joules: float,
    engine_temp: float,
    ride_height: float,
    fuel_clamped: float,
    dynamic_mass: float,
    compliance_status: str,
    thermal_mode: str,
    apex_severity: str,
    apex_status: str,
    apex_message: str,
) -> dict:
    return {
        "time": timestamp,
        "host": socket.gethostname(),
        "source": "atlas_edge_bridge",
        "sourcetype": "mcl_telemetry",
        "index": "project_apex",
        "event": {
            "car_id": car_id,
            "sensor_id": "VERT_PLATFORM",
            "speed_kph": int(round(speed)),
            "vertical_energy": round(energy_joules, 2),
            "engine_temp_c": round(engine_temp, 1),
            "rear_rh_mm": round(ride_height, 2),
            "fuel_load_kg": round(fuel_clamped, 2),
            "dynamic_mass_kg": round(dynamic_mass, 1),
            "compliance_status": compliance_status,
            "thermal_mode": thermal_mode,
            "apex_severity": apex_severity,
            "apex_status": apex_status,
            "apex_message": apex_message,

            # Added governance / traceability fields
            "td_version": CURRENT_TD_VERSION,
            "regulation_version": REGULATION_VERSION,
            "governance_category": "NONE",
            "governance_severity": "INFO",
            "governance_description": "No governance anomaly detected.",
            "incident_id": None,
            "evidence_bundle_ref": None,
        },
    }


def send_to_splunk(payload: dict, car_id: str) -> None:
    global last_success_log_time, last_error_log_time

    if SPLUNK_TOKEN == "REPLACE_WITH_SECURE_TOKEN":
        current_time = time.time()
        if current_time - last_error_log_time >= 5.0:
            logger.warning(
                "Security alert: default Splunk token in use. "
                "Set SPLUNK_TOKEN env var."
                )
            last_error_log_time = current_time
        return

    try:
        response = http_session.post(SPLUNK_HEC_URL, json=payload, verify=False, timeout=0.5)
        if response.status_code == 200:
            current_time = time.time()
            if current_time - last_success_log_time >= 60.0:
                logger.info(
                    "SUCCESS → Splunk ingestion active (heartbeat 60s) | Last car: %s",
                    car_id,
                )
                last_success_log_time = current_time
        else:
            current_time = time.time()
            if current_time - last_error_log_time >= 5.0:
                logger.error(f"Splunk HEC rejection: {response.text}")
                last_error_log_time = current_time
    except Exception as e:
        current_time = time.time()
        if current_time - last_error_log_time >= 5.0:
            logger.warning("HEC connection failed: %s", e)
            last_error_log_time = current_time

# ---------------------------------------------------------------------------
# Worker – decode packets, classify, enrich, send
# ---------------------------------------------------------------------------

def processing_worker() -> None:
    while True:
        try:
            data = PACKET_QUEUE.get(timeout=1.0)
        except queue.Empty:
            continue

        try:
            if len(data) != PACKET_SIZE:
                PACKET_QUEUE.task_done()
                continue

            unpacked = struct.unpack(PACKET_FORMAT, data)
            timestamp = unpacked[0]
            raw_car_id = unpacked[1]
            car_id = raw_car_id.decode("utf-8", errors="ignore").strip("\x00")
            speed = unpacked[2]
            ride_height = unpacked[3]
            vert_vel = unpacked[4]
            engine_temp = unpacked[5]
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

            telemetry_event = build_base_event(
                timestamp=timestamp,
                car_id=car_id,
                speed=speed,
                energy_joules=energy_joules,
                engine_temp=engine_temp,
                ride_height=ride_height,
                fuel_clamped=fuel_clamped,
                dynamic_mass=dynamic_mass,
                compliance_status=compliance_status,
                thermal_mode=thermal_mode,
                apex_severity=apex_severity,
                apex_status=apex_status,
                apex_message=apex_message,
            )

            penalties, loops = extract_governance_inputs_from_packet(
                timestamp=timestamp,
                car_id=car_id,
                speed=speed,
                ride_height=ride_height,
                vert_vel=vert_vel,
                engine_temp=engine_temp,
            )

            findings = detect_pitlane_configuration_anomalies(
                penalties=list(RECENT_PENALTIES),
                loops=list(RECENT_TIMING_LOOPS),
                config=gov_cfg,
            )

            if findings:
                for finding in findings:
                    enriched_event = copy.deepcopy(telemetry_event)
                    incident_id = build_incident_id(
                        category=getattr(finding, "category", "UNKNOWN"),
                        car_id=car_id,
                        timestamp=timestamp,
                        loop_name=getattr(finding, "loop_id", "unknown"),
                        severity=getattr(finding, "severity", "INFO"),
                    )

                    enriched_event["event"]["governance_category"] = getattr(
                        finding, "category", "UNKNOWN"
                    )
                    enriched_event["event"]["governance_severity"] = getattr(
                        finding, "severity", "INFO"
                    )
                    enriched_event["event"]["governance_description"] = getattr(
                        finding, "description", "Governance finding detected."
                    )
                    enriched_event["event"]["incident_id"] = incident_id

                    if severity_meets_threshold(
                        getattr(finding, "severity", "INFO"),
                        RIGHT_OF_REVIEW_THRESHOLD,
                    ):
                        evidence_bundle = build_evidence_package(
                            incident_id=incident_id,
                            finding=finding,
                            penalties=list(RECENT_PENALTIES),
                            loops=list(RECENT_TIMING_LOOPS),
                            td_version=CURRENT_TD_VERSION,
                            generated_at=timestamp,
                            car_id=car_id,
                        )

                        record_evidence_package_event(
                            incident_id=incident_id,
                            evidence_package=evidence_bundle,
                            severity=getattr(finding, "severity", "INFO"),
                            category=getattr(finding, "category", "UNKNOWN"),
                        )

                        enriched_event["event"]["evidence_bundle_ref"] = evidence_bundle.get(
                            "bundle_id", f"bundle-{incident_id}"
                        )

                    send_to_splunk(enriched_event, car_id)
            else:
                send_to_splunk(telemetry_event, car_id)

            PACKET_QUEUE.task_done()

        except Exception as e:
            logger.error(f"Worker exception: {e}")
            PACKET_QUEUE.task_done()

# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

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

    logger.info("Project Apex Validator v1.3 active on %s:%d", LISTEN_IP,LISTEN_PORT)
    logger.info(
        "Physics: DYNAMIC MASS | CAR_MIN=%s kg + fuel_load_kg (Regulation baseline: %s)",
        CAR_MIN_MASS_KG,
        REGULATION_VERSION,
    )
    logger.info(
        "Mass range: %.1f kg (empty) → %.1f kg (full fuel)",
        CAR_MIN_MASS_KG,
        CAR_MIN_MASS_KG + MAX_FUEL_LOAD_KG,
    )
    logger.info("Packet size: %d bytes | Format: %s", PACKET_SIZE, PACKET_FORMAT)
    logger.info("TD version loaded: %s", CURRENT_TD_VERSION)
    logger.info("Governance review threshold: %s", RIGHT_OF_REVIEW_THRESHOLD)

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
            logger.error("Main loop exception: %s", e)
            continue


if __name__ == "__main__":
    main()
