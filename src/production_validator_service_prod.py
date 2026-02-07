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

import socket
import struct
import json
import time
import os
import sys
import requests
from datetime import datetime

# --- ENTERPRISE CONFIGURATION ---
# CISSP Best Practice: Secrets are loaded from Environment Variables.
# These are injected by the Docker container / Cisco IOx runtime.
SPLUNK_HEC_URL = os.getenv("SPLUNK_HEC_URL", "https://splunk-hec.mclaren.internal:8088/services/collector")
SPLUNK_TOKEN = os.getenv("SPLUNK_TOKEN", "REPLACE_WITH_SECURE_TOKEN")
LISTEN_IP = os.getenv("LISTEN_IP", "0.0.0.0")
LISTEN_PORT = int(os.getenv("LISTEN_PORT", 20777))

# MCL40 PHYSICS CONSTANTS (2026 Spec)
CAR_MASS_KG = 798.0
THERMAL_THRESHOLD_C = 105.0 # Trigger for High-Compression Map (18:1 CR)
ENERGY_LIMIT_J = 100.0      # FIA Porpoising Limit

def log_msg(level: str, msg: str):
    """
    Standardized logging format for MTC Ops aggregation (Splunk/ELK).
    Format: [TIMESTAMP] [LEVEL] Message
    """
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    print(f"[{timestamp}] [{level}] {msg}")

def calculate_vertical_energy(vz: float) -> float:
    """
    Calculates Kinetic Energy of the vertical oscillation.
    Formula: E = 0.5 * m * v^2
    """
    return 0.5 * CAR_MASS_KG * (vz ** 2)

def send_to_splunk(payload: dict):
    """
    Secure transmission to Splunk HEC.
    Includes timeouts (500ms) to prevent telemetry blocking during network congestion.
    """
    headers = {
        "Authorization": f"Splunk {SPLUNK_TOKEN}",
        "Content-Type": "application/json"
    }
    
    try:
        # In internal MTC networks, self-signed certs are common on Edge nodes.
        # We suppress the warning to keep production logs clean.
        requests.packages.urllib3.disable_warnings() 
        
        response = requests.post(
            SPLUNK_HEC_URL, 
            json=payload, 
            headers=headers, 
            verify=False, 
            timeout=0.5 # Fail fast to preserve real-time telemetry loop
        )
        
        if response.status_code != 200:
            log_msg("ERROR", f"Splunk HEC Rejection: {response.text}")
            
    except requests.exceptions.RequestException as e:
        log_msg("WARN", f"HEC Connectivity Loss: {e}")

def main():
    # Setup High-Performance UDP Socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((LISTEN_IP, LISTEN_PORT))
        # OPTIMIZATION: Set 1MB Buffer for High-Frequency Trackside Data
        # Prevents packet drops if the Python Garbage Collector pauses execution.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1048576) 
    except PermissionError:
        log_msg("FATAL", f"Permission denied binding to port {LISTEN_PORT}. Check Container Privileges.")
        sys.exit(1)

    log_msg("INFO", f"Project Apex Validator Active on {LISTEN_IP}:{LISTEN_PORT}")
    log_msg("INFO", "Mode: PRODUCTION | Thermal-Aero Logic: ACTIVE")

    while True:
        try:
            # 1. INGEST LIVE PACKET
            # Blocking call, waits for ATLAS forwarder
            data, _ = sock.recvfrom(1024)
            
            # 2. DYNAMIC STRUCT UNPACKING (Lando vs Oscar)
            # CAR_1 (Lando) uses a 5-char ID. CAR_81 (Oscar) uses 6-char.
            # We determine logic based on packet length.
            packet_len = len(data)
            
            if packet_len == 37: # CAR_1
                 unpacked = struct.unpack('d5sffff', data)
            elif packet_len == 38: # CAR_81
                 unpacked = struct.unpack('d6sffff', data)
            else:
                 # Filter out malformed packets or noise
                 continue 

            # Extract Telemetry Variables
            timestamp = unpacked[0]
            car_id = unpacked[1].decode('utf-8').strip('\x00')
            speed = unpacked[2]
            ride_height = unpacked[3]
            vert_vel = unpacked[4]
            engine_temp = unpacked[5] # CRITICAL: The Thermal Loophole Variable

            # 3. PHYSICS ENGINE
            energy_joules = calculate_vertical_energy(vert_vel)

            # 4. COMPLIANCE LOGIC GATE (The "Brain")
            compliance_status = "LEGAL"
            thermal_mode = "STANDARD"

            # Check A: Mercedes Engine Loophole (Thermal Squat)
            # If Engine is HOT (>105C) and producing oscillations -> Flag as Thermal Failure
            if engine_temp > THERMAL_THRESHOLD_C:
                thermal_mode = "HIGH_COMPRESSION"
                if energy_joules > 80.0: # Lower threshold because thermal instability is dangerous
                    compliance_status = "CRITICAL: THERMAL_SQUAT"
            
            # Check B: Standard Porpoising (Aero Stall)
            elif energy_joules > ENERGY_LIMIT_J:
                compliance_status = "VIOLATION_RISK"

            # 5. CONSTRUCT JSON PAYLOAD
            # Enrich data with Edge Metadata (Host)
            telemetry_event = {
                "time": timestamp,
                "host": socket.gethostname(), 
                "source": "atlas_edge_bridge",
                "sourcetype": "mcl_telemetry",
                "event": {
                    "car_id": car_id,
                    "speed_kph": round(speed, 2),
                    "vertical_energy": round(energy_joules, 2),
                    "engine_temp_c": round(engine_temp, 1),
                    "rear_rh_mm": round(ride_height, 2),
                    "compliance_status": compliance_status,
                    "thermal_mode": thermal_mode
                }
            }

            # 6. TRANSMIT TO MISSION CONTROL
            send_to_splunk(telemetry_event)

            # Console Alerting (For local debugging only)
            if compliance_status != "LEGAL":
                log_msg("ALERT", f"[{car_id}] {compliance_status} | Temp: {engine_temp:.1f}C | Energy: {energy_joules:.0f}J")

        except KeyboardInterrupt:
            log_msg("INFO", "Stopping Validator Service...")
            break
        except Exception as e:
            # Catch-all to ensure the service NEVER crashes during a session
            log_msg("ERROR", f"Packet Processing Exception: {e}")
            continue

if __name__ == "__main__":
    main()
