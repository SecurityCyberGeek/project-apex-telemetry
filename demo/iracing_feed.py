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
import time
import json
import math
import irsdk # pip install irsdk

# --- CONFIGURATION ---
UDP_IP = "127.0.0.1"
UDP_PORT = 5000
DEMO_SPEED_THRESHOLD_MS = 69.5 # ~250 KPH triggers porpoising

# --- SIMULATED ID ---
# Forces the Dashboard to see "Lando Norris (CAR_1)" regardless of iRacing settings
FORCE_CAR_ID = "CAR_1" 

def main():
    # 1. Setup UDP Connection
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # 2. Connect to iRacing SDK
    ir = irsdk.IRSDK()
    ir.startup()

    print("--- PROJECT APEX: IRACING BRIDGE ---")
    print(f"Target: {UDP_IP}:{UDP_PORT}")
    print(f"Vehicle: {FORCE_CAR_ID} (Simulating 2026 Champion)")
    print("Waiting for iRacing connection...")

    while not ir.is_connected:
        time.sleep(1)
        
    print("Connected! Waiting for physics engine...")

    # Wait for the session to actually start (user is in the car)
    while ir['SessionTime'] is None:
        time.sleep(1)
        ir.freeze_var_buffer_latest()

    print("Physics Active. Streaming Telemetry.")

    try:
        while True:
            ir.freeze_var_buffer_latest()
            
            # --- TELEMETRY EXTRACTION ---
            speed_ms = ir['Speed']
            if speed_ms is None: speed_ms = 0.0
            speed_kph = speed_ms * 3.6
            
            # Fallback if car doesn't have specific shock sensors
            if ir['LFshockDefl'] is not None:
                suspension_pos = (ir['LFshockDefl'] + ir['RFshockDefl']) / 2.0
            else:
                # Synthetic baseline for cars without sensors
                suspension_pos = 0.05 - (speed_ms * 0.0002)

            # --- DEMO INJECTION LOGIC ---
            # If speed > 250 KPH, inject 9cm oscillation to trigger RED ALERT
            if speed_ms > DEMO_SPEED_THRESHOLD_MS:
                oscillation = math.sin(time.time() * 20) * 0.09 
                suspension_pos += oscillation
                
            # --- PACKET CREATION ---
            telemetry_packet = {
                "timestamp": time.time(),
                "car_id": FORCE_CAR_ID,
                "speed": speed_ms,
                "speed_kph": speed_kph,
                "ride_height_raw": suspension_pos,
                "throttle": ir['Throttle'] if ir['Throttle'] else 0,
                "brake": ir['Brake'] if ir['Brake'] else 0
            }

            # Send via UDP
            sock.sendto(json.dumps(telemetry_packet).encode('utf-8'), (UDP_IP, UDP_PORT))
            
            # 60 Hz Update Rate
            time.sleep(1/60)

    except KeyboardInterrupt:
        print("\nStopping Telemetry Stream.")
        ir.shutdown()
        sock.close()

if __name__ == "__main__":
    main()