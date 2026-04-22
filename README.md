# Project Apex: MCL40 Real-Time Physics Validation System

![Status](https://img.shields.io/badge/Status-Deployment%20Ready-success?style=for-the-badge)
![Target](https://img.shields.io/badge/Target-F1%202026%20Regulations-orange?style=for-the-badge)
![Stack](https://img.shields.io/badge/Tech-Python%20%7C%20Splunk%20HEC%20%7C%20UDP-blue?style=for-the-badge)
![License](https://img.shields.io/badge/License-Apache%202.0-lightgrey?style=for-the-badge)

## 🏁 What Is Project Apex?

**Project Apex** is a real‑time physics validation and integrity monitoring service for F1‑style telemetry streams under the 2026 technical regulations.

It runs at the trackside edge, listens to the same 60 Hz UDP telemetry feed as the team’s primary tooling (e.g., ATLAS), computes vertical energy using a dynamic mass model, classifies each packet’s physics state and integrity severity, and forwards enriched JSON events into Splunk via HEC for visualization in a Mission Control dashboard.

Project Apex does not replace existing telemetry infrastructure. It adds an integrity layer that turns _“data is flowing”_ into _“data is physics‑validated and severity‑tagged against named thresholds.”_

---

## 📦 Core Components

| File | Purpose |
| --- | --- |
| `production_validator_service_prod.py` | Main edge validator service: UDP ingest, physics features, GREEN/YELLOW/RED classification, Splunk HEC output. |
| `production_atlas_bridge.py` | Local ATLAS‑style telemetry bridge: simulates two cars (CAR1: Norris, CAR81: Piastri) at 60 Hz and sends UDP packets to the validator. |
| `apex_mission_control_dashboard.json` | Splunk Dashboard Studio definition for “Project Apex: Mission Control (MCL40)”. |
| `requirements.txt` | Python dependencies (validator + bridge). |
| `AGENTS.md` | Guidance for AI/code assistants working in this repository (project purpose, coding standards, FIA constants, roadmap tasks). |

---

## 🧠 Physics Model & Classification (v1.2)

Apex v1.2 implements a dynamic‑mass vertical energy model aligned with the 2026 FIA Technical Regulations.

### Packet Format (v1.2)

Each UDP packet is a fixed‑length binary struct:

```text
PACKET_FORMAT = "<d10sfffff"  # 38 bytes
```

| Field           | Type   | Description                       |
|----------------|--------|-----------------------------------|
| `timestamp`    | double | Unix timestamp (seconds)          |
| `car_id`       | 10s    | Car identifier (e.g., `CAR1`)     |
| `speed_kph`    | float  | Vehicle speed (kph)               |
| `ride_height_mm` | float| Rear ride height (mm)             |
| `vert_vel_ms`  | float  | Vertical velocity \(v_z\) (m/s)   |
| `engine_temp_c`| float  | Engine/power‑unit temperature (°C)|
| `fuel_load_kg` | float  | Current fuel load (kg)            |

`production_atlas_bridge.py` generates packets in exactly this format for CAR1 and CAR81.  

### Dynamic Vertical Energy

Vertical energy is computed per packet using **real‑time car mass**:

\[
E = 0.5 \times (CAR\_MIN\_MASS\_KG + fuel\_load\_kg) \times v_z^2
\]

Where:

- `CAR_MIN_MASS_KG = 768.0` kg — minimum car + driver mass (no fuel).  
- `fuel_load_kg` is clamped between 0.0 and `MAX_FUEL_LOAD_KG = 100.0` before use.  

At race start (full fuel, 868 kg), the same vertical velocity produces more energy than at race end (768 kg), so high‑risk states are detected earlier when the car is heaviest and grip is lowest.

### Thresholds (v1.2)

The validator uses named physics constants:

```python
CAR_MIN_MASS_KG        = 768.0   # Minimum car + driver mass, no fuel
MAX_FUEL_LOAD_KG       = 100.0   # Max permitted fuel load at race start
THERMAL_THRESHOLD_C    = 130.0   # High-compression regime threshold
ENERGY_LIMIT_J         = 100.0   # Nominal vertical oscillation limit
THERMAL_ENERGY_LIMIT_J = 80.0    # Reduced limit under high thermal load
AERO_STALL_RH_MM       = 28.0    # Rear ride height stall-risk threshold
```

Severity is assigned based on **energy**, **engine temperature**, and **ride height**:

| Severity | Core condition (simplified) | Status | Example message (abridged) |
| --- | --- | --- | --- |
| GREEN | \(E \le 100\) J and temp \(\le 130\) °C | `WITHIN_SPEC` | Within expected physics envelope. |
| YELLOW (thermal) | temp \> 130 °C, \(E \le 80\) J | `TRENDING` | Engine temperature above nominal; monitor. |
| YELLOW (thermal + energy) | temp \> 130 °C and \(E \> 80\) J | `TRENDING` | High temp and elevated vertical energy; monitor for torque anomaly. |
| YELLOW (non‑thermal) | temp \(\le 130\) °C and \(E \> 100\) J | `TRENDING` | Vertical energy above nominal limit; monitor oscillation risk. |
| RED | temp \> 130 °C, \(E \> 80\) J, ride height \< 28 mm | `ANOMALY_DETECTED` | High temp, high energy, and aero squat: torque anomaly confirmed. |

The function `classify_event(engine_temp, energy_joules, ride_height)` returns:

```python
compliance_status, apex_severity, apex_status, apex_message, thermal_mode
```

and is the single source of truth for GREEN/YELLOW/RED classification and the text used by the dashboard’s Event Stream.  

> **Note:** There is **no** battery SOC or torque‑delta logic implemented in v1.2. Those examples that previously appeared in the README were design sketches, not actual code.

---

## ⚡ FIA 2026 ERS / Energy Management Constants (Configuration Only)

In v1.2, a set of ERS‑related constants is defined for future use, but **does not yet affect GREEN/YELLOW/RED severity**:

```python
ERS_MAX_RECHARGE_MJ          = 7.0    # Max recharge per lap (reduced from 8 MJ)
ERS_DEPLOY_ACCEL_KW          = 350.0  # MGU-K in key acceleration/overtaking zones
ERS_DEPLOY_NON_ACCEL_KW      = 250.0  # MGU-K in other parts of the lap
ERS_BOOST_CAP_KW             = 150.0  # Max additional Boost in race conditions
ERS_SUPERCLIP_MAX_DURATION_S = 4.0    # Target bound for "superclip" duration per lap
```

These values are sourced from the April 19–20, 2026 FIA/FOM stakeholder refinements and are intended to drive **ERS compliance checks** in a future, backward‑compatible release (e.g., using optional `ers_*` fields if present in telemetry). In v1.2, they are **configuration only** and are logged in code comments for traceability.

---

## ⚙️ System Architecture (v1.2)

To sustain 60 Hz telemetry on edge hardware (e.g., Cisco IOx), Apex uses a **threaded producer–consumer** design with a bounded queue.

### 1. Ingest (Producer)

- Binds a UDP socket on `LISTEN_IP` / `LISTEN_PORT` (defaults `0.0.0.0:20777`; overridable via environment).  
- Sets the OS receive buffer to 1 MB (`SO_RCVBUF = 1024 * 1024`) to tolerate short bursts.  
- Receives raw packets from the ATLAS‑style forwarder (`production_atlas_bridge.py` in local demos).  
- Immediately enqueues each packet into a `queue.Queue(maxsize=2048)` for processing.

### 2. Edge Compute (Logic Gate)

- A dedicated worker thread (`processing_worker`) dequeues packets.  
- Packets whose length does **not** equal `PACKET_SIZE` are dropped without unpacking.  
- Valid packets are unpacked with `PACKET_FORMAT = "<d10sfffff"` and converted to fields:

  - `car_id` is decoded from bytes, null‑stripped, and sanitized.
  - `fuel_load_kg` is clamped to \[0, 100\] kg and added to `CAR_MIN_MASS_KG` to compute dynamic mass.
  - Vertical energy is computed via `calculate_vertical_energy(vz, fuel_load_kg)` using the dynamic mass model.
  - `classify_event(...)` is called to derive severity and status fields.

- A JSON event is assembled with all derived fields (including `vertical_energy`, `dynamic_mass_kg`, `fuel_load_kg`, `apex_severity`, `compliance_status`, and `apex_message`) and passed to the transport layer.

### 3. Transport (Splunk HEC Consumer)

- A module‑level `requests.Session` (`http_session`) is reused for all HEC calls.  
- HEC endpoint and token are taken from the environment, with safe defaults:

  ```python
  SPLUNK_HEC_URL = os.getenv(
      "SPLUNK_HEC_URL",
      "https://splunk-hec.mclaren.internal:8088/services/collector/event",
  )
  SPLUNK_TOKEN = os.getenv("SPLUNK_TOKEN", "REPLACE_WITH_SECURE_TOKEN")
  ```

- If `SPLUNK_TOKEN` is still the placeholder `"REPLACE_WITH_SECURE_TOKEN"`, the validator logs a rate‑limited security warning and **refuses** to send telemetry until a real token is supplied.  
- Each event is sent with:

  ```python
  http_session.post(
      SPLUNK_HEC_URL,
      json=payload,
      verify=False,   # demo / lab; production should enable verification
      timeout=0.5,
  )
  ```

- Success and error logs are rate‑limited (heartbeat every 60 s; error messages at most every 5 s) to avoid log spam or disk exhaustion.

### 4. Visualization (Mission Control Dashboard)

- The **“Project Apex: Mission Control (MCL40)”** Dashboard Studio JSON is provided in `apex_mission_control_dashboard.json`.  
- It defines data sources and visualizations for:

  - Current peak vertical energy across cars.  
  - Count of active critical (RED) events.  
  - Dynamic mass and fuel traces for CAR1 vs CAR81 over time.  
  - Thermal scatter (engine temp vs. rear ride height).  
  - A color‑coded event stream table keyed on `compliance_status` and severity.

---

## 🛡️ Security & Hardening (v1.2)

v1.2 includes concrete hardening steps suitable for edge deployments.

### 1. Input Validation

- **Strict length checking**: packets are only unpacked if `len(data) == PACKET_SIZE`; malformed packets are discarded early.  
- **Fixed binary struct**: only the expected `<d10sfffff` format is accepted.  
- **Safe string decoding**: `car_id` is decoded as UTF‑8 with `errors="ignore"` and null‑stripped to avoid control characters.

### 2. Memory Safety & Back‑Pressure

- The producer–consumer queue is explicitly bounded (`maxsize=2048`).  
- If the queue is full, new packets are dropped, and a warning is emitted at most once every 5 seconds, preventing unbounded memory growth under HEC or network failure scenarios.  
- The UDP receive buffer is increased to 1 MB to mitigate packet loss during transient bursts.

### 3. Credential Management & Transport

- HEC endpoint and token are sourced from environment variables; no real credentials are committed to source.  
- When the token placeholder is in use, Apex refuses to send events and surfaces a clear security log message.  
- In demo mode, `verify=False` is used to support self‑signed certificates; production deployments should supply a proper CA bundle and enable TLS verification.

### 4. Logging & Observability

- Structured logs include car ID and a periodic “SUCCESS → Splunk ingestion active (heartbeat 60s)” line.  
- Connection errors and token misconfigurations are logged with timestamps and throttled to avoid log floods.

---

## 📊 Splunk Mission Control Dashboard

The `apex_mission_control_dashboard.json` file defines a single‑tab Dashboard Studio layout titled:

> **Project Apex: Mission Control (MCL40)**  
> Description: _Real‑Time Physics Validation & Regulatory Compliance Engine — 2026 Post‑Melbourne Update_

Key elements:

- **Global time input (`input_GlobalTime`)** controlling all searches (default: last 30 s, real‑time).  
- **Single‑value KPIs**:
  - _Aero Platform Status_: current peak vertical energy, color‑coded by thresholds.  
  - _Integrity Severity (Active RED Alerts)_: count of CRITICAL events in the time window.  
  - _Car Mass — CAR1 (Dynamic)_: latest `dynamic_mass_kg` value with color ranges.  
- **Time series**:
  - _Live Speed Telemetry (Head‑to‑Head)_: timechart of average speed by `car_id`.  
  - _Fuel Load Over Time (CAR1: Norris | CAR81: Piastri)_: separate traces for fuel burn profiles.  
- **Scatter**:
  - _Transient Torque & Squat Correlation_: `engine_temp_c` vs `rear_rh_mm` to visualize high‑temp squat events.  
- **Event stream**:
  - Table of recent events with `_time`, `car_id`, `speed_kph`, `vertical_energy`, `dynamic_mass_kg`, `fuel_load_kg`, `engine_temp_c`, and `compliance_status`.  
  - Row background colors driven by a context mapping on `compliance_status` (CRITICAL / WARNING / VIOLATION_RISK / LEGAL).

The SPL and visualization configuration in the README are kept at a high level; the JSON file is the canonical, executable definition.

---

## 🚀 Running the Local Demo

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

`requirements.txt` includes `requests` for HEC transport and `splunk‑sdk` for future Splunk integrations.

### 2. Set Splunk HEC Environment Variables

```bash
export SPLUNK_HEC_URL="https://<your-splunk-host>:8088/services/collector/event"
export SPLUNK_TOKEN="<your_hec_token>"
# Optional overrides:
export LISTEN_IP="0.0.0.0"
export LISTEN_PORT="20777"
```

### 3. Start the Validator Service

```bash
python3 production_validator_service_prod_2.py
```

You should see logs similar to:

```text
Project Apex Validator v1.2 Active on 0.0.0.0:20777
Physics: DYNAMIC MASS | CAR_MIN=768.0kg + fuel_load_kg
Mass range: 768.0kg (empty) → 868.0kg (full fuel)
Packet size: 38 bytes | Format: <d10sfffff>
```

Once HEC is configured correctly and Splunk is reachable, you’ll also see periodic heartbeats:

```text
SUCCESS → Splunk ingestion active (heartbeat 60s) | Last car: CAR1
```

### 4. Start the ATLAS Bridge Simulator

In another terminal:

```bash
python3 production_atlas_bridge.py
```

You should see CAR1 and CAR81 fuel and mass traces printed every few seconds, with CAR1 occasionally entering a torque‑anomaly regime (high temp + squat + elevated vertical energy) that will drive RED events in the dashboard.

### 5. Import the Dashboard

- In Splunk Dashboard Studio, create a new JSON dashboard.  
- Paste the contents of `apex_mission_control_dashboard.json`.  
- Save and open the dashboard to see live speed, fuel, mass, thermal scatter, and the event stream.

---

## 📚 Additional Material

- **Architectural Specification & Operations Manual**: see the separate spec/Notion documentation referenced externally (not included in this repository).  
- **Conference Presentation**: `Project-Apex-Security-BSides-San-Diego-2026.pdf` (slide deck) demonstrates the original v1.x concept and can be used as background reading; the code in this repository represents the current v1.2 implementation.

---

## 👤 Author

**Timothy D. Harmon, CISSP**

Lead Enterprise Architect — Project Apex (Cyber‑Physical Telemetry & Safety)  
Motorsport official and FIA University graduate (race incident and safety management, event organisation, working under pressure, and related modules).

_Project Apex runs on top of your existing telemetry ecosystem and uses Splunk as its operational intelligence backbone, giving engineers a clear, physics‑grounded integrity view at race speed._
