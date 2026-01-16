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

import socket
import threading
import queue
import time
import json
import logging
import requests
import urllib3

# Disable SSL warnings for local Splunk (self-signed certs)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIGURATION ---
LISTEN_IP = "0.0.0.0"
LISTEN_PORT = 5000

# --- SPLUNK CONFIGURATION ---
SPLUNK_HEC_URL = "https://127.0.0.1:8088/services/collector/event"
# *** PASTE YOUR TOKEN BELOW ***
SPLUNK_HEC_TOKEN = "60f19791-a02e-4ea4-bb17-365afab0885b" 
ENABLE_SPLUNK = True

# --- OPTIMIZATION SETTINGS ---
# Only send to Splunk every N seconds to prevent HTTP lag
# 0.1 = 10Hz (Updates dashboard 10 times/sec, plenty for visual smoothness)
SPLUNK_UPDATE_INTERVAL = 0.1 

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s')
logger = logging.getLogger("ApexService")

class SplunkForwarder:
    def send_event(self, event_data):
        if not ENABLE_SPLUNK: return

        headers = {"Authorization": f"Splunk {SPLUNK_HEC_TOKEN}"}
        
        # Wrap data in HEC format
        payload = {
            "time": time.time(),
            "host": "APEX_NODE_01",
            "source": "ProjectApex", 
            "sourcetype": "_json",
            "event": event_data
        }

        try:
            # Short timeout to fail fast if Splunk is busy
            requests.post(SPLUNK_HEC_URL, headers=headers, json=payload, verify=False, timeout=0.1)
        except Exception:
            pass # Drop packet if Splunk is slow to keep the queue moving

class TelemetryIngestor(threading.Thread):
    def __init__(self, data_queue):
        super().__init__()
        self.data_queue = data_queue
        self.running = True
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.bind((LISTEN_IP, LISTEN_PORT))
        except OSError:
            logger.error(f"Error: Port {LISTEN_PORT} is busy. Stop other scripts!")
            exit(1)
        # Non-blocking socket to prevent hang
        self.sock.settimeout(0.2)

    def run(self):
        logger.info(f"Ingestor listening on {LISTEN_IP}:{LISTEN_PORT}")
        while self.running:
            try:
                data, _ = self.sock.recvfrom(4096)
                packet = json.loads(data.decode('utf-8'))
                
                # OPTIMIZATION: If queue is getting full (lag is building), 
                # clear it to jump to 'Now'.
                if self.data_queue.qsize() > 50:
                    with self.data_queue.mutex:
                        self.data_queue.queue.clear()
                    logger.warning("Lag detected! Dropped old packets to sync with Real-Time.")
                
                self.data_queue.put(packet)
            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"Socket error: {e}")

    def stop(self):
        self.running = False
        self.sock.close()

class InternalValidator:
    def validate(self, packet):
        # Physics Logic: Calculate vertical energy (1/2 mv^2 proxy)
        rh = packet.get('ride_height_raw', 0)
        energy = abs(rh * 1000) # Scale up for visibility
        
        status = "STABLE"
        if energy > 100: 
            status = "CRITICAL" # Porpoising detected
            
        return {"status": status, "oscillation_energy": energy}

class ValidationWorker(threading.Thread):
    def __init__(self, data_queue):
        super().__init__()
        self.data_queue = data_queue
        self.running = True
        self.validator = InternalValidator()
        self.splunk = SplunkForwarder()
        self.last_sent_time = 0

    def run(self):
        logger.info("Validator Engine Started. Streaming to Splunk...")
        while self.running:
            try:
                packet = self.data_queue.get(timeout=1.0)
                
                # 1. ALWAYS run validation logic (Safety first)
                result = self.validator.validate(packet)
                
                # 2. DECIDE: Do we send this to Splunk?
                # Send if CRITICAL (Immediate Alert) OR if time interval passed (Visual Update)
                current_time = time.time()
                is_critical = result['status'] == "CRITICAL"
                time_to_send = (current_time - self.last_sent_time) > SPLUNK_UPDATE_INTERVAL
                
                if is_critical or time_to_send:
                    splunk_payload = {
                        "car_id": packet.get('car_id', 'UNKNOWN'),
                        "status": result['status'],
                        "speed_kph": packet.get('speed_kph', 0),
                        "oscillation_energy": result['oscillation_energy'],
                        "message": "PORPOISING DETECTED" if is_critical else "System Normal"
                    }
                    
                    self.splunk.send_event(splunk_payload)
                    self.last_sent_time = current_time
                
                # Terminal Feedback
                if is_critical:
                    logger.warning(f"CRITICAL | {packet.get('car_id')} | Energy: {result['oscillation_energy']:.2f}J")

            except queue.Empty:
                continue

    def stop(self):
        self.running = False

def main():
    telemetry_queue = queue.Queue()
    
    ingestor = TelemetryIngestor(telemetry_queue)
    worker = ValidationWorker(telemetry_queue)
    
    ingestor.start()
    worker.start()
    
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        ingestor.stop()
        worker.stop()
        ingestor.join()
        worker.join()

if __name__ == "__main__":
    main()