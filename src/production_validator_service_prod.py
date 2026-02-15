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

#!/usr/bin/env python3
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
# Essential for air-gapped garage networks utilizing self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- PRODUCTION CONFIGURATION (ENV VARS) ---
# SECURITY FIX: Default to HTTPS. 
# McLaren IT will override this via 'export SPLUNK_HEC_URL=...' in the IOx profile.
SPLUNK_HEC_URL = os.getenv("SPLUNK_HEC_URL", "https://splunk-hec.mclaren.internal:8088/services/collector/event")
SPLUNK_TOKEN = os.getenv("SPLUNK_TOKEN", "REPLACE_WITH_SECURE_TOKEN")
LISTEN_IP = os.getenv("LISTEN_IP", "0.0.0.0") 
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "20777"))

# --- PHYSICS CONSTANTS (MCL40) ---
CAR_MASS_KG = 798.0
THERMAL_THRESHOLD_C = 105.0 
ENERGY_LIMIT_J = 100.0       

# --- THREADING CONFIGURATION ---
# Queue size of 2048 handles ~34 seconds of buffered telemetry at 60Hz
PACKET_QUEUE = queue.Queue(maxsize=2048)
QUEUE_FULL_WARNING_COOLDOWN = 0.0

# GLOBAL STATE FOR LOG THROTTLING
last_success_log_time = 0.0
last_error_log_time = 0.0

# --- OPTIMIZATION: PERSISTENT SESSION ---
http_session = requests.Session()
http_session.headers.update({
    "Authorization": f"Splunk {SPLUNK_TOKEN}",
    "Content-Type": "application/json"
})

def calculate_vertical_energy(vz: float) -> float:
    return 0.5 * CAR_MASS_KG * (vz ** 2)

def send_to_splunk(payload: dict, car_id: str):
    global last_success_log_time, last_error_log_time
    
    # Security Gate: Prevent data leakage if the token is not configured
    if SPLUNK_TOKEN == "REPLACE_WITH_SECURE_TOKEN":
        current_time = time.time()
        if current_time - last_error_log_time >= 5.0:
            logger.warning("Security Alert: Default Token in use. Set SPLUNK_TOKEN env var.")
            last_error_log_time = current_time
        return

    try:
        # verify=False is required for internal self-signed certs (Air-Gap Standard)
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

# --- WORKER THREAD (CONSUMER) ---
def processing_worker():
    """Reads packets from Queue, parses physics, sends to Splunk."""
    while True:
        try:
            # Block for 1 sec waiting for data to prevent CPU spin
            data = PACKET_QUEUE.get(timeout=1.0)
        except queue.Empty:
            continue

        try:
            # --- BULLETPROOF UNPACKING ---
            if len(data) == struct.calcsize('<d10sffff'):
                unpacked = struct.unpack('<d10sffff', data)
            else:
                PACKET_QUEUE.task_done()
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

            # --- PROJECT APEX PHYSICS LOGIC ---
            if engine_temp > THERMAL_THRESHOLD_C:
                thermal_mode = "HIGH_COMPRESSION" 
                # Transient Torque Anomaly Logic
                if energy_joules > 80.0: 
                    compliance_status = "CRITICAL: TORQUE_ANOMALY"
            elif energy_joules > ENERGY_LIMIT_J:
                compliance_status = "VIOLATION_RISK"

            # CONSTRUCT SPLUNK PAYLOAD
            telemetry_event = {
                "time": timestamp,
                "host": "mtc-edge-node", 
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
            
            # Heavy I/O Operation (HTTP POST)
            send_to_splunk(telemetry_event, car_id)
            PACKET_QUEUE.task_done()
            
        except Exception as e:
            logger.error(f"Worker Exception: {e}")
            PACKET_QUEUE.task_done()

# --- MAIN THREAD (PRODUCER) ---
def main():
    global QUEUE_FULL_WARNING_COOLDOWN
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((LISTEN_IP, LISTEN_PORT))
    
    # OS Buffer Optimization (1MB) to prevent UDP drops
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)
    
    logger.info(f"Project Apex Validator Active on {LISTEN_IP}:{LISTEN_PORT}")
    logger.info(f"Architecture: Multi-Threaded Producer/Consumer (Queue: 2048)")
    
    # Start the Worker Thread
    worker = threading.Thread(target=processing_worker, daemon=True)
    worker.start()

    while True:
        try:
            # Hot Loop: Only receives data and puts it in the queue. 
            data, _ = sock.recvfrom(1024)
            
            try:
                PACKET_QUEUE.put_nowait(data)
            except queue.Full:
                # Tail Drop Strategy: If the queue is full, drop new packets to protect memory
                current_time = time.time()
                if current_time - QUEUE_FULL_WARNING_COOLDOWN >= 5.0:
                    logger.warning("QUEUE FULL: Dropping packets. Check Splunk connectivity.")
                    QUEUE_FULL_WARNING_COOLDOWN = current_time
                    
        except KeyboardInterrupt:
            logger.info("Stopping Validator Service...")
            http_session.close() 
            break
        except Exception as e:
            continue

if __name__ == "__main__":
    main()
