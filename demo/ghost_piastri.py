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

# --- CONFIGURATION ---
UDP_IP = "127.0.0.1"
UDP_PORT = 5000
GHOST_ID = "CAR_81" # Oscar Piastri

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"--- GHOST CAR ACTIVE: {GHOST_ID} ---")
    print(f"Injecting clean telemetry to {UDP_IP}:{UDP_PORT}")
    
    t = 0
    try:
        while True:
            # Simulate high speed cruising (300-310 KPH)
            # Oscar drives smoothly, so NO porpoising injection
            speed_kph = 305 + (math.sin(t * 0.5) * 5) 
            speed_ms = speed_kph / 3.6
            
            # Stable ride height with tiny natural vibration
            ride_height = 0.03 + (math.sin(t * 15) * 0.001)

            packet = {
                "timestamp": time.time(),
                "car_id": GHOST_ID,
                "speed": speed_ms,
                "speed_kph": speed_kph,
                "ride_height_raw": ride_height,
                "throttle": 1.0,
                "brake": 0.0
            }

            sock.sendto(json.dumps(packet).encode('utf-8'), (UDP_IP, UDP_PORT))
            
            t += 0.016 # ~60 Hz
            time.sleep(0.016)

    except KeyboardInterrupt:
        print("\nGhost Car Stopped.")

if __name__ == "__main__":
    main()