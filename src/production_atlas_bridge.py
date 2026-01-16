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

# --- MOCKING THE PROPRIETARY MCLAREN LIBRARIES ---
# In reality, this would be: import mclaren.atlas.sdk as atlas
class MockAtlasSession:
    """
    Simulates connecting to the McLaren ATLAS Telemetry Server.
    """
    def subscribe(self, topic):
        print(f"[ATLAS] Subscribed to {topic} stream...")

    def get_next_packet(self):
        # SIMULATION: The server sends interleaved packets from Lando (1) and Oscar (81)
        import random
        
        # Randomly decide whose data came in this millisecond
        car_id = "CAR_1" if random.random() > 0.5 else "CAR_81"
        
        # Simulate high-speed telemetry packet
        return {
            "timestamp": time.time(),
            "source_id": car_id,
            "metric_id": "vCar:Suspension:RR:Disp", # Standard ATLAS naming convention
            "value": 0.03 + (random.random() * 0.005), # 30mm + noise
            "velocity": 290.0 # kph
        }

class ProductionAtlasBridge(threading.Thread):
    def __init__(self, output_queue):
        super().__init__()
        self.output_queue = output_queue
        self.running = True
        self.atlas = MockAtlasSession()

    def run(self):
        logging.info("Connecting to MTC Telemetry Bus...")
        self.atlas.subscribe("LIVE_SESSION_2026_GP_SILVERSTONE")
        
        while self.running:
            # 1. Pull raw packet from the "Firehose"
            raw_data = self.atlas.get_next_packet()
            
            # 2. Normalize Data (The Adapter Pattern)
            apex_packet = {
                "timestamp": raw_data['timestamp'],
                "car_id": raw_data['source_id'], # "CAR_1" or "CAR_81"
                "speed_kph": raw_data['velocity'],
                "ride_height_raw": raw_data['value'],
                "status": "RAW"
            }
            
            # 3. Push to the Validator Service
            self.output_queue.put(apex_packet)
            time.sleep(0.001) 

    def stop(self):
        self.running = False