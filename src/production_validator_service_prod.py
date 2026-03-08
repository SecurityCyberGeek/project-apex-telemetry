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

#!/usr/bin/env python3
"""
PROJECT APEX: ACTIVE AERO & INTEGRITY VALIDATION SERVICE (PRODUCTION)
---------------------------------------------------------------------
Context:    F1 2026 Technical Regulations (MCL40)
Deployment: Cisco IOx Edge Compute / MTC Mission Control
Author:     Timothy D. Harmon, CISSP

DESCRIPTION:
This service acts as the 'Edge Brain' for the Project Apex framework.
It consumes high-frequency (60Hz) UDP telemetry from the ATLAS forwarder
and computes vertical energy, thermal mode, and basic integrity severity.

It emits enriched events to Splunk with:

  - compliance_status     (legacy physics classification)
  - apex_severity         (GREEN / YELLOW / RED)
  - apex_status           (WITHIN_SPEC / TRENDING / ANOMALY_DETECTED)
  - apex_message          (short human-readable description)
  - sensor_id             (logical sensor / channel identifier)

The detailed natural-language YELLOW/RED text lives in Splunk as
'apex_message' or can be expanded later as needed.
"""

import socket
import struct
import json
import time
import os
import sys
import requests
import logging
import urllib3
import threading
import queue
from datetime import datetime

# --- LOGGING CONFIGURATION ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("ApexValidator")

# --- SUPPRESS SSL WARNINGS ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- PRODUCTION CONFIGURATION (ENV VARS) ---
SPLUNK_HEC_URL = os.getenv("SPLUNK_HEC_URL", "https://splunk-hec.mclaren.internal:8088/services/collector/event")
SPLUNK_TOKEN = os.getenv("SPLUNK_TOKEN", "REPLACE_WITH_SECURE_TOKEN")
LISTEN_IP = os.getenv("LISTEN_IP", "0.0.0.0")
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "20777"))

# --- PHYSICS CONSTANTS (MCL40) ---
CAR_MASS_KG = 798.0
THERMAL_THRESHOLD_C = 130.0
ENERGY_LIMIT_J = 100.0           # Standard oscillation limit
THERMAL_ENERGY_LIMIT_J = 80.0    # Reduced threshold when floor is thermally loaded
AERO_STALL_RH_MM = 28.0          # Ride height where diffuser stall becomes imminent

# Packet format: [timestamp(d)][car_id(10s)][speed_kph(f)][ride_height_mm(f)][vert_vel_ms(f)][engine_temp_c(f)]
PACKET_FORMAT = '<d10sffff'
PACKET_SIZE = struct.calcsize(PACKET_FORMAT)

# --- THREADING CONFIGURATION ---
PACKET_QUEUE = queue.Queue(maxsize=2048)
QUEUE_FULL_WARNING_COOLDOWN = 0.0

# GLOBAL STATE FOR LOG THROTTLING
last_success_log_time = 0.0
last_error_log_time = 0.0

# --- HTTP SESSION ---
http_session = requests.Session()

def calculate_vertical_energy(vz: float) -> float:
    return 0.5 * CAR_MASS_KG * (vz ** 2)

def classify_event(engine_temp: float, energy_joules: float, ride_height: float):
    """
    Returns:
        compliance_status, apex_severity, apex_status, apex_message
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
            apex_message = "High engine temp, high vertical energy, and aero squat detected (torque anomaly)."
        elif energy_joules > THERMAL_ENERGY_LIMIT_J:
            compliance_status = "WARNING: TORQUE_ANOMALY_UNCONFIRMED"
            apex_severity = "YELLOW"
            apex_status = "TRENDING"
            apex_message = "High engine temp and elevated vertical energy; monitor for torque anomaly."
        else:
            # High temperature but energy still within threshold
            apex_severity = "YELLOW"
            apex_status = "TRENDING"
            apex_message = "Engine temperature above nominal; monitor vertical energy and ride height."
    else:
        if energy_joules > ENERGY_LIMIT_J:
            compliance_status = "VIOLATION_RISK"
            apex_severity = "YELLOW"
            apex_status = "TRENDING"
            apex_message = "Vertical energy above nominal limit; monitor for oscillation risk."

    return compliance_status, apex_severity, apex_status, apex_message, thermal_mode

def send_to_splunk(payload: dict, car_id: str):
    global last_success_log_time, last_error_log_time

    if SPLUNK_TOKEN == "REPLACE_WITH_SECURE_TOKEN":
        current_time = time.time()
        if current_time - last_error_log_time >= 5.0:
            logger.warning("Security Alert: Default Token in use. Set SPLUNK_TOKEN env var.")
            last_error_log_time = current_time
        return

    try:
        response = http_session.post(SPLUNK_HEC_URL, json=payload, verify=False, timeout=0.5)

        if response.status_code == 200:
            current_time = time.time()
            if current_time - last_success_log_time >= 60.0:
                logger.info(f"SUCCESS -> Splunk Ingestion Active (Heartbeat: 60s) | Last Car: {car_id}")
                last_success_log_time = current_time
        else:
            current_time = time.time()
            if current_time - last_error_log_time >= 5.0:
                logger.error(f"Splunk HEC Rejection: {response.text}")
                last_error_log_time = current_time

    except Exception as e:
        current_time = time.time()
        if current_time - last_error_log_time >= 5.0:
            logger.warning(f"HEC Connection Failed: {e}")
            last_error_log_time = current_time

def processing_worker():
    """Reads packets from Queue, parses physics, sends to Splunk."""
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
            raw_car_id = unpacked[1].decode('utf-8', errors='ignore')
            car_id = raw_car_id.strip('\x00')
            speed = unpacked[2]
            ride_height = unpacked[3]
            vert_vel = unpacked[4]
            engine_temp = unpacked[5]

            energy_joules = calculate_vertical_energy(vert_vel)

            compliance_status, apex_severity, apex_status, apex_message, thermal_mode = classify_event(
                engine_temp, energy_joules, ride_height
            )

            # For this prototype, we treat vertical platform as the primary sensor_id
            sensor_id = "VERT_PLATFORM"

            telemetry_event = {
                "time": timestamp,
                "host": socket.gethostname(),
                "source": "atlas_edge_bridge",
                "sourcetype": "mcl_telemetry",
                "index": "project_apex",
                "event": {
                    "car_id": car_id,
                    "sensor_id": sensor_id,
                    "speed_kph": int(round(speed)),
                    "vertical_energy": round(energy_joules, 2),
                    "engine_temp_c": round(engine_temp, 1),
                    "rear_rh_mm": round(ride_height, 2),
                    "compliance_status": compliance_status,
                    "thermal_mode": thermal_mode,
                    "apex_severity": apex_severity,
                    "apex_status": apex_status,
                    "apex_message": apex_message
                }
            }

            send_to_splunk(telemetry_event, car_id)
            PACKET_QUEUE.task_done()

        except Exception as e:
            logger.error(f"Worker Exception: {e}")
            PACKET_QUEUE.task_done()

def main():
    global QUEUE_FULL_WARNING_COOLDOWN

    http_session.headers.update({
        "Authorization": f"Splunk {SPLUNK_TOKEN}",
        "Content-Type": "application/json"
    })

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((LISTEN_IP, LISTEN_PORT))
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)

    logger.info(f"Project Apex Validator Active on {LISTEN_IP}:{LISTEN_PORT}")
    logger.info("Architecture: Multi-Threaded Producer/Consumer (Queue: 2048)")
    logger.info("Logic Profile: MCL40_TRANSIENT_TORQUE_V2_WITH_SEVERITY")

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
                    logger.warning("QUEUE FULL: Dropping packets. Check Splunk connectivity.")
                    QUEUE_FULL_WARNING_COOLDOWN = current_time

        except KeyboardInterrupt:
            logger.info("Stopping Validator Service...")
            http_session.close()
            break
        except Exception as e:
            logger.error(f"Main loop exception: {e}")
            continue

if __name__ == "__main__":
    main()
