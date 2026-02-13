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
print("[*] Scenario: CAR_1 (Lando) -> Transient Torque Anomaly | CAR_81 (Oscar) -> Baseline")
print("[*] Pattern: Burst Logic (Simulating Corner Exits)")

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
start_time = time.time()

# Fixed variable name typo (cando -> lando)
lando_temp = 90.0
oscar_temp = 90.0

try:
    while True:
        current_time = time.time()
        elapsed = current_time - start_time
        
        # --- CAR 1: LANDO (THE ANOMALY) ---
        # 1. Simulate Thermal Creep (Engine getting hotter over the "lap")
        if lando_temp < 115.0:
            lando_temp += 0.08  
        
        # 2. Simulate "High Load" Events (Corner Exits)
        # Using a sine wave to simulate On-Throttle (Positive) vs Off-Throttle (Negative)
        # Period is approx 4 seconds
        throttle_demand = math.sin(elapsed * 1.5)
        is_accelerating = throttle_demand > 0.4  # Only trigger under hard acceleration
        
        # LOGIC GATE: 
        # The Anomaly requires TWO conditions:
        # A. Engine is Expanded (Temp > 105)
        # B. Driver is demanding Torque (Accelerating)
        torque_anomaly_active = (lando_temp > 105.0) and is_accelerating
        
        lando_speed = 320.0 + (math.sin(elapsed) * 10)
        
        # Standard Ride Height is 30mm (+/- suspension travel)
        lando_rh = 30.0 + (5 * math.sin(elapsed * 2))
        
        if torque_anomaly_active:
            # PHYSICS SIMULATION: 
            # Torque Spike causes sudden squat (-2.5mm)
            lando_rh -= 2.5 
            # High Torque + Stalled Floor = Vertical Oscillation (Porpoising)
            # This makes the "Energy" value spike in your dashboard
            lando_vz = (math.sin(elapsed * 20) * 1.8) 
        else:
            # Nominal vertical velocity (road bumps)
            lando_vz = 0.3 

        # --- CAR 81: OSCAR (THE CONTROL) ---
        if oscar_temp < 98.0:
            oscar_temp += 0.02
            
        oscar_speed = 322.0 + (math.sin(elapsed) * 10)
        oscar_rh = 30.0 + (5 * math.sin(elapsed * 2)) 
        oscar_vz = 0.25 

        # --- BULLETPROOF PACKET GENERATION (<d10sffff) ---
        packet_lando = struct.pack('<d10sffff', current_time, b"CAR_1".ljust(10, b'\x00'), lando_speed, lando_rh, lando_vz, lando_temp)
        sock.sendto(packet_lando, (UDP_IP, UDP_PORT))
        
        packet_oscar = struct.pack('<d10sffff', current_time, b"CAR_81".ljust(10, b'\x00'), oscar_speed, oscar_rh, oscar_vz, oscar_temp)
        sock.sendto(packet_oscar, (UDP_IP, UDP_PORT))
        
        # ALIGNMENT CHANGE: Console output helps you narrate the "Burst" nature
        if elapsed % 0.5 < 0.05: 
            if torque_anomaly_active:
                status = "!!! TORQUE SPIKE !!!" 
            elif lando_temp > 105.0:
                status = "High Temp (Coasting)"
            else:
                status = "Nominal"
                
            print(f"Time: {elapsed:.0f}s | Lando: {lando_temp:.1f}C [{status}]")
        
        time.sleep(1/FREQUENCY)

except KeyboardInterrupt:
    print("\n[!] Bridge Stopped.")
