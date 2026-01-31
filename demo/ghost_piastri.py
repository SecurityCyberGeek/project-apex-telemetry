#  Copyright 2026 Timothy D. Harmon, CISSP
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
import random
import datetime

# --- CONFIGURATION ---
UDP_IP = "127.0.0.1"
UDP_PORT = 5000
CAR_ID = "CAR_1" # Lando Norris

# --- AUTO-STOP SETTINGS (24-Hour Format) ---
# 8:00 AM PST = 8
STOP_HOUR = 8
STOP_MINUTE = 0

# --- PHYSICS CONSTANTS ---
MAX_SPEED_KPH = 330.0
MIN_SPEED_KPH = 80.0
ACCEL_RATE = 150.0  # kph per second
BRAKE_RATE = 250.0  # kph per second (F1 brakes are strong!)

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"--- GHOST CAR ACTIVE: {CAR_ID} ---")
    print(f"Simulating realistic lap profile to {UDP_IP}:{UDP_PORT}")
    
    # Initial State
    current_speed = 100.0
    state = "ACCEL" # ACCEL, BRAKE, COAST
    state_timer = 0
    ride_height = 0.03
    
    try:
        while True:
            # --- AUTO-STOP CHECK ---
            # This block checks the time every loop.
            now = datetime.datetime.now()
            if now.hour == STOP_HOUR and now.minute >= STOP_MINUTE:
                print(f"\n--- SHAKEDOWN COMPLETE ({now.strftime('%H:%M:%S')}) ---")
                print("Stopping simulation per schedule.")
                break
            
            # 1. State Machine to mimic a lap (Straights vs Corners)
            # Randomly switch states to simulate a dynamic track layout
            state_timer -= 0.016
            
            if state_timer <= 0:
                if state == "ACCEL":
                    # End of straight -> Brake for corner
                    state = "BRAKE"
                    state_timer = random.uniform(1.0, 3.0) # Braking zones are short
                elif state == "BRAKE":
                    # End of braking -> Mid corner coast/throttle modulation
                    state = "COAST"
                    state_timer = random.uniform(2.0, 5.0) # Corners take time
                elif state == "COAST":
                    # Exit corner -> Full throttle
                    state = "ACCEL"
                    state_timer = random.uniform(5.0, 12.0) # Straights are long

            # 2. Physics Update based on State
            if state == "ACCEL":
                current_speed += ACCEL_RATE * 0.016
                throttle = 1.0
                brake = 0.0
            elif state == "BRAKE":
                current_speed -= BRAKE_RATE * 0.016
                throttle = 0.0
                brake = 1.0
            elif state == "COAST":
                # Slight speed bleed or maintain in corner
                current_speed -= 10.0 * 0.016
                throttle = 0.2
                brake = 0.0

            # Clamp Speed
            if current_speed > MAX_SPEED_KPH: current_speed = MAX_SPEED_KPH
            if current_speed < MIN_SPEED_KPH: current_speed = MIN_SPEED_KPH

            # 3. Ride Height Physics (Downforce Compression)
            # Faster = Lower ride height (Aerodynamic load)
            # Slower = Higher ride height
            # Base = 30mm (0.03m), compresses by up to 25mm at max speed
            compression = (current_speed / MAX_SPEED_KPH) * 0.025
            ride_height = 0.035 - compression + (random.uniform(-0.001, 0.001)) # Add road noise

            # 4. Data Packet
            packet = {
                "timestamp": time.time(),
                "car_id": CAR_ID,
                "speed": current_speed / 3.6, # m/s
                "speed_kph": current_speed,
                "ride_height_raw": ride_height,
                "throttle": throttle,
                "brake": brake
            }

            sock.sendto(json.dumps(packet).encode('utf-8'), (UDP_IP, UDP_PORT))
            
            time.sleep(0.016) # 60 Hz

    except KeyboardInterrupt:
        print("\nGhost Car Stopped.")

if __name__ == "__main__":
    main()
