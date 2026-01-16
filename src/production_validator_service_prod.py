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

import threading
import queue
import time
import logging
import requests
import os
import sys
from production_atlas_bridge import ProductionAtlasBridge

# --- ENTERPRISE CONFIGURATION ---
SPLUNK_HEC_URL = "https://splunk-hec.mclaren-racing.com:8088/services/collector/event"
# SECURITY: Read token from secure environment variable
SPLUNK_HEC_TOKEN = os.environ.get("SPLUNK_APEX_TOKEN") 
SSL_CERT_PATH = "/etc/ssl/certs/mclaren-internal-ca.pem"

logging.basicConfig(level=logging.WARNING) # Only log warnings in production
logger = logging.getLogger("ApexProdService")

class SplunkForwarder:
    def send_event(self, event_data):
        headers = {"Authorization": f"Splunk {SPLUNK_HEC_TOKEN}"}
        
        payload = {
            "time": time.time(),
            "host": "MTC_COMPUTE_NODE_04",
            "source": "ProjectApexProd", 
            "sourcetype": "_json",
            "index": "telemetry", # OPTIMIZATION: Specific index
            "event": event_data
        }

        try:
            # SECURITY: SSL Verification Enabled
            requests.post(SPLUNK_HEC_URL, headers=headers, json=payload, verify=SSL_CERT_PATH, timeout=0.5)
        except Exception as e:
            logger.error(f"Splunk Drop: {e}")

class MultiCarValidator(threading.Thread):
    def __init__(self, input_queue):
        super().__init__()
        self.input_queue = input_queue
        self.running = True
        self.splunk = SplunkForwarder()
        self.car_states = {} # Dictionary to track state for entire grid

    def run(self):
        logger.info("Validator Engine Online. Monitoring Grid...")
        while self.running:
            try:
                packet = self.input_queue.get(timeout=1.0)
                car = packet['car_id']
                
                # Dynamic Registration
                if car not in self.car_states:
                    self.car_states[car] = {"energy_buffer": [], "status": "STABLE"}
                    logger.info(f"New Vehicle Detected: {car}")

                self.validate_vehicle(car, packet)
                
            except queue.Empty:
                continue

    def validate_vehicle(self, car_id, packet):
        rh = packet['ride_height_raw']
        energy = abs(rh * 1000)
        
        status = "STABLE"
        if energy > 100: status = "CRITICAL"
        
        # In production, we send everything so Engineers have full history
        payload = {
            "car_id": car_id,
            "status": status,
            "speed_kph": packet['speed_kph'],
            "oscillation_energy": energy
        }
        self.splunk.send_event(payload)

def main():
    if not SPLUNK_HEC_TOKEN:
        logger.critical("No Splunk Token found in Environment Variables. Exiting.")
        sys.exit(1)

    telemetry_bus = queue.Queue()
    
    # Start Bridge (ATLAS)
    bridge = ProductionAtlasBridge(telemetry_bus)
    bridge.start()
    
    # Start Logic (Multi-Car)
    validator = MultiCarValidator(telemetry_bus)
    validator.start()
    
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        bridge.stop()
        validator.stop()

if __name__ == "__main__":
    main()