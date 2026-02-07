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

import socket
import struct
import time
import math
import random

# CONFIGURATION
UDP_IP = "127.0.0.1"
UDP_PORT = 20777
FREQUENCY = 60  # 60Hz Telemetry Standard

print(f"[*] Project Apex: ATLAS Bridge Initialized on {UDP_IP}:{UDP_PORT}")
print("[*] Mode: HEAD-TO-HEAD SIMULATION (Lando vs Oscar)")
print("[*] Scenario: CAR_1 (Lando) testing High-Comp Map | CAR_81 (Oscar) Baseline")

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
start_time = time.time()

# SIMULATION STATE
cando_temp = 90.0
oscar_temp = 90.0

try:
    while True:
        current_time = time.time()
        elapsed = current_time - start_time
        
        # --- CAR 1: LANDO (THE RISK) ---
        if cando_temp < 115.0:
            cando_temp += 0.08
        
        lando_squat_active = cando_temp > 105.0
        lando_speed = 320.0 + (math.sin(elapsed) * 10)
        lando_rh = 30.0 + (5 * math.sin(elapsed * 2))
        
        if lando_squat_active:
            lando_rh -= 2.5 # THERMAL SQUAT
            lando_vz = (math.sin(elapsed * 15) * 1.8) # Porpoising
        else:
            lando_vz = 0.3 

        # --- CAR 81: OSCAR (THE CONTROL) ---
        if oscar_temp < 98.0:
            oscar_temp += 0.02
        oscar_speed = 322.0 + (math.sin(elapsed) * 10)
        oscar_rh = 30.0 + (5 * math.sin(elapsed * 2)) 
        oscar_vz = 0.25 

        # --- PACKET GENERATION ---
        # PACKET 1: LANDO (5-char ID)
        packet_lando = struct.pack('d5sffff', current_time, b"CAR_1", lando_speed, lando_rh, lando_vz, cando_temp)
        sock.sendto(packet_lando, (UDP_IP, UDP_PORT))
        
        # PACKET 2: OSCAR (6-char ID)
        packet_oscar = struct.pack('d6sffff', current_time, b"CAR_81", oscar_speed, oscar_rh, oscar_vz, oscar_temp)
        sock.sendto(packet_oscar, (UDP_IP, UDP_PORT))
        
        if elapsed % 1.0 < 0.1: 
            print(f"Time: {elapsed:.0f}s | Lando: {cando_temp:.1f}C | Oscar: {oscar_temp:.1f}C")
        
        time.sleep(1/FREQUENCY)

except KeyboardInterrupt:
    print("\n[!] Bridge Stopped.")
