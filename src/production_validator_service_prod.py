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

#!/usr/bin/env python3
"""
PROJECT APEX: ACTIVE AERO VALIDATION SERVICE (PRODUCTION)
Deployment: Cisco IOx Edge Compute / MTC Server
Context: F1 2026 Regulations (MCL40)
Author: Timothy D. Harmon, CISSP

DESCRIPTION:
This service acts as the 'Edge Brain' for the Project Apex framework.
It listens for high-frequency UDP telemetry from the ATLAS forwarder,
calculates vertical oscillation energy in real-time, and enforces
the FIA 100J compliance limit. It also correlates Engine Temperature
to detect thermally-induced aero squat (The 'Mercedes Loophole').
"""

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

#!/usr/bin/env python3
"""
PROJECT APEX: ACTIVE AERO VALIDATION SERVICE (PRODUCTION)
Deployment: Cisco IOx Edge Compute / MTC Server
Context: F1 2026 Regulations (MCL40)
Author: Timothy D. Harmon, CISSP

DESCRIPTION:
This service acts as the 'Edge Brain' for the Project Apex framework.
It listens for high-frequency UDP telemetry from the ATLAS forwarder,
calculates vertical oscillation energy in real-time, and enforces
the FIA 100J compliance limit.
"""

import socket
import struct
import json
import time
import os
import sys
import requests
import logging
from datetime import datetime

# --- LOGGING CONFIGURATION ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("ApexValidator")

# --- ENTERPRISE CONFIGURATION (SECURE) ---
# Secrets MUST be injected via Environment Variables in production (Docker/Kubernetes/IOx)
SPLUNK_HEC_URL = os.getenv("SPLUNK_HEC_URL", "https://splunk-hec.mclaren.internal:8088/services/collector/event")
SPLUNK_TOKEN = os.getenv("SPLUNK_TOKEN")
LISTEN_IP = os.getenv("LISTEN_IP", "0.0.0.0") # Bind to all interfaces for network multicast
LISTEN_PORT = int(os.getenv("LISTEN_PORT", 20777))
VERIFY_SSL = os.getenv("VERIFY_SSL", "True").lower() in ("true", "1", "t")

# Failsafe: Do not start if security tokens are missing
if not SPLUNK_TOKEN:
    logger.critical("FATAL: SPLUNK_TOKEN environment variable missing. Aborting startup.")
    sys.exit(1)

# MCL40 PHYSICS CONSTANTS (2026 Spec)
CAR_MASS_KG = 798.0
THERMAL_THRESHOLD_C = 105.0 
ENERGY_LIMIT_J = 100.0      

# GLOBAL STATE: Throttle the Success logs to prevent terminal flooding
last_success_log_time = 0.0

def calculate_vertical_energy(vz: float) -> float:
    return 0.5 * CAR_MASS_KG * (vz ** 2)

def send_to_splunk(payload: dict, car_id: str):
    global last_success_log_time
    headers = {"Authorization": f"Splunk {SPLUNK_TOKEN}", "Content-Type": "application/json"}
    
    try:
        if not VERIFY_SSL:
            requests.packages.urllib3.disable_warnings()

        response = requests.post(SPLUNK_HEC_URL, json=payload, headers=headers, verify=VERIFY_SSL, timeout=1.0)
        
        if response.status_code == 200:
            current_time = time.time()
            # HEARTBEAT LOGIC: Only print "SUCCESS" if 60 seconds have passed
            if current_time - last_success_log_time >= 60.0:
                logger.info(f"SUCCESS -> Splunk Ingestion Active (Heartbeat: 60s) | Last Car: {car_id}")
                last_success_log_time = current_time
        else:
            logger.error(f"Splunk HEC Rejection: {response.text}")
            
    except Exception as e:
        logger.warning(f"HEC Connection Failed: {e}")

def main():
    # Setup High-Performance UDP Socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((LISTEN_IP, LISTEN_PORT))
        # OPTIMIZATION: Set 1MB Buffer for High-Frequency Trackside Data
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1048576) 
    except PermissionError:
        logger.critical(f"FATAL: Permission denied binding to port {LISTEN_PORT}.")
        sys.exit(1)

    logger.info(f"Project Apex Validator Active on {LISTEN_IP}:{LISTEN_PORT}")

    while True:
        try:
            data, _ = sock.recvfrom(4096) # Increased buffer size for real ATLAS packets
            
            # --- ATLAS ICD UNPACKING ---
            # NOTE: In actual production, this exact struct format will be updated
            # to match the proprietary McLaren ATLAS Interface Control Document (ICD).
            try:
                if len(data) == struct.calcsize('<d10sffff'):
                    unpacked = struct.unpack('<d10sffff', data)
                else:
                    continue # Skip garbage packets
            except struct.error:
                continue

            timestamp = unpacked[0]
            car_id = unpacked[1].decode('utf-8').strip('\x00')
            speed = unpacked[2]
            ride_height = unpacked[3]
            vert_vel = unpacked[4]
            engine_temp = unpacked[5] 

            energy_joules = calculate_vertical_energy(vert_vel)

            compliance_status = "LEGAL"
            thermal_mode = "STANDARD"

            # THE "MERCEDES LOOPHOLE" LOGIC GATE
            if engine_temp > THERMAL_THRESHOLD_C:
                thermal_mode = "HIGH_COMPRESSION"
                if energy_joules > 80.0: 
                    compliance_status = "CRITICAL: THERMAL_SQUAT"
            elif energy_joules > ENERGY_LIMIT_J:
                compliance_status = "VIOLATION_RISK"

            # CONSTRUCT SPLUNK PAYLOAD
            telemetry_event = {
                "time": timestamp,
                "host": socket.gethostname(), # Dynamically get the Edge Node hostname
                "source": "atlas_edge_bridge",
                "sourcetype": "mcl_telemetry",
                "index": "project_apex", 
                "event": {
                    "car_id": car_id,
                    "speed_kph": int(round(speed)),
                    "vertical_energy": round(energy_joules, 2),
                    "engine_temp_c": round(engine_temp, 1),
                    "rear_rh_mm": round(ride_height, 2),
                    "compliance_status": compliance_status,
                    "thermal_mode": thermal_mode
                }
            }

            send_to_splunk(telemetry_event, car_id)

        except KeyboardInterrupt:
            logger.info("Stopping Validator Service...")
            break
        except Exception as e:
            # Catch-all to ensure the service NEVER crashes during a live race session
            logger.error(f"Packet Processing Exception: {e}")
            continue

if __name__ == "__main__":
    main()
