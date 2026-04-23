# Project Apex – Agent Guidance

## Project overview

Project Apex v1.2 is an edge validator for 2026 Formula 1 telemetry. It ingests UDP telemetry, computes physics features with a **dynamic mass model** (`car mass = 768 kg + fuel load`), and classifies each event into **GREEN / YELLOW / RED** severity states for safety and compliance monitoring.

## Core files

- `src/production_validator_service_prod.py` – main dynamic-mass validator (v1.2).
- `src/simulation/production_atlas_bridge.py` – telemetry simulator / ATLAS-style bridge.
- `dashboards/apex_mission_control_dashboard.json` – Splunk Dashboard Studio definition.

## Validator model and thresholds (v1.2)

### Dynamic mass and vertical energy

The validator computes vertical energy using dynamic mass:

- `E = 0.5 * (CAR_MIN_MASS_KG + fuel_load_kg) * vz^2`
- `CAR_MIN_MASS_KG = 768.0`
- `MAX_FUEL_LOAD_KG = 100.0`
- `fuel_load_kg` is clamped to `[0, 100]`

### Classification thresholds

- `THERMAL_THRESHOLD_C = 130.0`
- `ENERGY_LIMIT_J = 100.0`
- `THERMAL_ENERGY_LIMIT_J = 80.0`
- `AERO_STALL_RH_MM = 28.0`

### Classification behavior

- **GREEN** by default (within spec).
- **YELLOW** for elevated thermal/energy risk states.
- **RED** when thermal + energy + squat conditions confirm anomaly risk.

## ERS constants (configuration only)

The following ERS constants are defined as configuration values and should be treated as **not yet wired into severity logic**:

- `ERS_MAX_RECHARGE_MJ = 7.0`
- `ERS_DEPLOY_ACCEL_KW = 350.0`
- `ERS_DEPLOY_NON_ACCEL_KW = 250.0`
- `ERS_BOOST_CAP_KW = 150.0`
- `ERS_SUPERCLIP_MAX_DURATION_S = 4.0`

These values reflect the April 2026 FIA/FOM ERS refinements and are intended for an optional ERS compliance layer. They must not change existing GREEN/YELLOW/RED behavior unless explicitly requested.

## Telemetry packet format expectations

### Validator packet format (v1.2)

Expected packet format:

- `PACKET_FORMAT = "<d10sfffff"` (38 bytes)

Field order:

1. `timestamp` (`d`)
2. `car_id` (`10s`)
3. `speed_kph` (`f`)
4. `ride_height_mm` (`f`)
5. `vert_vel_ms` (`f`)
6. `engine_temp_c` (`f`)
7. `fuel_load_kg` (`f`)

### Bridge alignment note

Both the validator and the bridge now use the v1.2 packet format `<d10sfffff` with `fuel_load_kg` included. Future changes to the packet format must be applied in both files and covered by tests.

## Coding standards for this repo

- Prefer small, pure functions with clear inputs/outputs.
- Do not add hidden side effects (network calls, file writes, mutable global surprises) inside classification logic.
- Use type hints for new or refactored code.
- Preserve current behavior unless explicitly instructed to change it.
- Keep logging structured and actionable when emitting anomaly/compliance events.

## Codex roadmap

1. **Packet alignment + coverage**
   - Align the bridge packet format with validator v1.2.
   - Add tests around dynamic-mass classification behavior.

2. **Unit tests (pytest)**
   - Add `pytest` tests for `classify_event` and vertical-energy computation.
   - Include realistic boundary cases around all key thresholds.

3. **CI automation**
   - Add a GitHub Actions workflow that runs `pytest` on push and pull requests.

4. **Optional ERS compliance layer**
   - Introduce ERS compliance evaluation using `ERS_*` constants.
   - Keep existing severity logic unchanged (ERS compliance reported separately).

5. **Logging/docs/dashboard validation**
   - Refine logging and developer documentation.
   - Validate that the Splunk dashboard only references fields actually emitted by the validator.
