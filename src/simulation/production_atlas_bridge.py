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

UDP_IP    = "127.0.0.1"
UDP_PORT  = 20777
FREQUENCY = 60  # 60Hz

# PACKET FORMAT (v1.2) — must match production_validator_service_prod_2.py exactly.
# Field order: timestamp(d), car_id(10s), speed_kph(f), ride_height_mm(f),
#              vert_vel_ms(f), engine_temp_c(f), fuel_load_kg(f)
PACKET_FORMAT = '<d10sfffff'  # 38 bytes

# --- PER-CAR FUEL MODEL (Shanghai GP 2026) ---
# Fuel is tracked SEPARATELY per car to produce two distinct visible traces
# in the Splunk Fuel Over Time panel. Lando burns slightly more fuel due
# to higher-energy deployment profile; Oscar uses a more conservative strategy.
# Both values are physically plausible within the 2026 fuel allocation.
#
# Race: ~307 km, ~56 laps, ~90 min, max 100 kg fuel
# Lando (aggressive): 100 kg / ~87.7 min → 0.019 kg/s base burn
# Oscar (conservative): 100 kg / ~98.0 min → 0.017 kg/s base burn
# During Lando torque anomaly: +0.004 kg/s (higher electrical deployment)

FUEL_START_KG         = 100.0
LANDO_BURN_BASE_KGS   = 0.019    # kg/s base — 87.7 min race
OSCAR_BURN_KGS        = 0.017    # kg/s constant — 98 min race
ANOMALY_BURN_EXTRA    = 0.004    # kg/s added during Lando torque anomaly

# FAST DEMO: uncomment these to burn through fuel in ~3-5 minutes
# LANDO_BURN_BASE_KGS = 0.35
# OSCAR_BURN_KGS      = 0.30
# ANOMALY_BURN_EXTRA  = 0.05

print(f"[*] Project Apex: ATLAS Bridge v1.2 on {UDP_IP}:{UDP_PORT}")
print("[*] Mode: HEAD-TO-HEAD SIMULATION (CAR1: Norris | CAR81: Piastri)")
print(f"[*] Fuel model: per-car | CAR1={LANDO_BURN_BASE_KGS}kg/s | CAR81={OSCAR_BURN_KGS}kg/s")
print(f"[*] Packet format: {PACKET_FORMAT} (38 bytes) — includes fuel_load_kg")

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
start_time = time.time()

lando_temp        = 125.0
oscar_temp        = 110.0
lando_fuel_burned = 0.0   # cumulative kg burned by Lando
oscar_fuel_burned = 0.0   # cumulative kg burned by Oscar

last_time = start_time

try:
    while True:
        current_time = time.time()
        elapsed      = current_time - start_time
        dt           = current_time - last_time   # seconds since last tick
        last_time    = current_time

        # --- CAR 1: LANDO NORRIS (ANOMALY CAR) ---
        if lando_temp < 136.0:
            lando_temp += 0.05

        lando_speed      = 260.0 + (math.sin(elapsed * 0.8) * 60)
        is_accelerating  = math.cos(elapsed * 0.8) > 0.2
        torque_anomaly   = (lando_temp > 130.0) and is_accelerating

        lando_rh_mm = 32.0 + (1.5 * math.sin(elapsed * 4))
        lando_vz_ms = 0.15 * math.sin(elapsed * 15)

        if torque_anomaly:
            lando_rh_mm -= 5.5
            lando_vz_ms  = 0.6 + (0.1 * math.sin(elapsed * 25))

        # Per-car fuel burn — higher during Lando anomaly
        lando_burn_rate   = LANDO_BURN_BASE_KGS + (ANOMALY_BURN_EXTRA if torque_anomaly else 0.0)
        lando_fuel_burned = min(FUEL_START_KG, lando_fuel_burned + lando_burn_rate * dt)
        lando_fuel_kg     = max(0.0, FUEL_START_KG - lando_fuel_burned)

        # --- CAR 81: OSCAR PIASTRI (CONTROL CAR) ---
        if oscar_temp < 118.0:
            oscar_temp += 0.01

        oscar_speed  = 250.0 + (math.cos(elapsed * 0.5) * 75)
        oscar_rh_mm  = 31.5 + (1.8 * math.cos(elapsed * 3.5))
        oscar_vz_ms  = 0.12 * math.cos(elapsed * 12)

        oscar_fuel_burned = min(FUEL_START_KG, oscar_fuel_burned + OSCAR_BURN_KGS * dt)
        oscar_fuel_kg     = max(0.0, FUEL_START_KG - oscar_fuel_burned)

        # --- PACKET GENERATION ---
        # FIELD ORDER must exactly match PACKET_FORMAT and validator unpacking:
        #   [2] speed_kph       (f) kph
        #   [3] ride_height_mm  (f) mm      ← NOT m/s
        #   [4] vert_vel_ms     (f) m/s     ← drives E = 0.5 * dynamic_mass * vz²
        #   [5] engine_temp_c   (f) °C
        #   [6] fuel_load_kg    (f) kg      ← per-car, decreases during race

        lando_car_id = b'CAR1\x00\x00\x00\x00\x00\x00'   # 10 bytes
        oscar_car_id = b'CAR81\x00\x00\x00\x00\x00'        # 10 bytes

        lando_packet = struct.pack(
            PACKET_FORMAT,
            current_time, lando_car_id,
            lando_speed, lando_rh_mm, lando_vz_ms, lando_temp, lando_fuel_kg
        )
        oscar_packet = struct.pack(
            PACKET_FORMAT,
            current_time, oscar_car_id,
            oscar_speed, oscar_rh_mm, oscar_vz_ms, oscar_temp, oscar_fuel_kg
        )

        sock.sendto(lando_packet, (UDP_IP, UDP_PORT))
        sock.sendto(oscar_packet, (UDP_IP, UDP_PORT))

        # --- CONSOLE DIAGNOSTICS (every 5 seconds) ---
        lando_mass = 768.0 + lando_fuel_kg
        lando_E    = 0.5 * lando_mass * lando_vz_ms**2
        oscar_mass = 768.0 + oscar_fuel_kg

        if torque_anomaly:
            status = f"RED    | vz={lando_vz_ms:.3f}m/s E={lando_E:.1f}J rh={lando_rh_mm:.1f}mm"
        elif lando_temp > 130.0:
            status = f"YELLOW | vz={lando_vz_ms:.3f}m/s E={lando_E:.1f}J (elevated temp)"
        else:
            status = f"GREEN  | vz={lando_vz_ms:.3f}m/s E={lando_E:.1f}J"

        if int(elapsed) % 5 == 0 and elapsed % 1 < (1 / FREQUENCY):
            print(f"[t={elapsed:>6.1f}s] "
                  f"CAR1:  fuel={lando_fuel_kg:.2f}kg mass={lando_mass:.1f}kg | {status}")
            print(f"         "
                  f"CAR81: fuel={oscar_fuel_kg:.2f}kg mass={oscar_mass:.1f}kg | temp={oscar_temp:.1f}C")

        time.sleep(1 / FREQUENCY)

except KeyboardInterrupt:
    print("\n[!] Bridge Stopped.")
