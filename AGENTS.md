# Project Apex – Agent Guidance

## Project purpose

Project Apex is an independent, security-focused telemetry and compliance validation platform for the 2026 FIA Formula 1 regulations. It ingests race telemetry, computes physics-based features (e.g., vertical energy in joules, engine temperature, ride height, ERS deployment), and classifies events as GREEN, YELLOW, or RED for safety and compliance analysis.

Project Apex is designed to stay aligned with FIA/F1 regulatory refinements, including the April 20, 2026 updates to energy management, Boost, MGU-K limits, low-power starts, and ERS deployment in wet conditions. [web:1708][web:1709][web:1713]

## Core files

- `production_validator_service_prod_2.py` – main validation and classification logic.
- `production_atlas_bridge.py` – telemetry bridge/event generator.
- `apex_mission_control_dashboard.json` – Splunk dashboard definition for Mission Control.

## Tech stack

- Python 3.x for validator and tooling.
- Splunk / SPL for dashboards and searches.

## How to run tests

Currently, no automated tests are committed. The project will use `pytest`.

Once tests exist:

```bash
pip install -r requirements.txt
pip install pytest
pytest
```

## Coding standards

- Prefer small, pure functions with clear inputs/outputs.
- Do NOT add side effects (network calls, file writes) inside classification logic.
- Use type hints for new or refactored functions.
- Add structured logging where we emit anomaly classifications.
- Preserve existing behavior unless explicitly instructed otherwise.
- All FIA regulatory constants must be named and sourced with a comment citing the April 20, 2026 FIA/F1 refinement announcement.

## FIA regulatory constants (agreed April 20, 2026 – effective Miami GP)

Source: FIA and F1 stakeholder statement on refinements to the 2026 regulations, published April 19–20, 2026. [web:1708][web:1709][web:1713]

| Constant Name                     | Value | Unit | Regulatory basis                                   |
|-----------------------------------|-------|------|----------------------------------------------------|
| ERS_MAX_RECHARGE_MJ              | 7.0   | MJ   | Reduced max permitted recharge (from 8 MJ)         |
| ERS_DEPLOY_ACCEL_KW              | 350   | kW   | Peak MGU-K in key acceleration/overtaking zones    |
| ERS_DEPLOY_NON_ACCEL_KW          | 250   | kW   | MGU-K limit in other parts of the lap              |
| ERS_BOOST_CAP_KW                 | 150   | kW   | Max extra race Boost power (or car’s current power)|
| ERS_SUPERCLIP_MAX_DURATION_S     | 4.0   | s    | Target maximum superclip duration per lap          |

These constants are used by the validator for ERS compliance checks where ERS data is available. When ERS telemetry is absent, Apex falls back to v1.1 behavior.

## Existing v1.1 physics constants (do not change unless explicitly requested)

These constants encode the v1.1 safety thresholds used prior to the April 20, 2026 ERS refinements. [file:1444]

| Constant Name          | Value | Unit | Purpose                                        |
|------------------------|-------|------|------------------------------------------------|
| THERMAL_THRESHOLD_C    | 130.0 | °C   | Engine temperature RED trigger                 |
| ENERGY_LIMIT_J         | 100.0 | J    | Vertical energy YELLOW threshold               |
| THERMAL_ENERGY_LIMIT_J | 80.0  | J    | Vertical energy RED threshold (with high temp) |
| AERO_STALL_RH_MM       | 28.0  | mm   | Rear ride height squat RED threshold           |

## Roadmap focus for Codex

Short-term priorities for Codex and other agents working in this repo:

1. **Tests and CI**
   - Add a `pytest` test suite for `production_validator_service_prod_2.py`, covering all GREEN/YELLOW/RED branches and ERS compliance cases.
   - Add a GitHub Actions CI workflow that runs tests on push/PR.

2. **ERS support (backward-compatible)**
   - Extend the validator to support optional ERS telemetry fields (`ers_deploy_kw`, `ers_recharge_mj`, `ers_superclip_duration_s`, `in_acceleration_zone`) without breaking current behavior.
   - Use the FIA ERS constants above for compliance checks.

3. **Refinement and logging**
   - Refactor for clarity: type hints, docstrings, structured logging.
   - Ensure anomaly classifications are logged with sufficient context (key inputs, thresholds crossed, and result).

4. **Splunk integration**
   - Generate helper scripts and documentation for Splunk dashboards, explaining how Apex fields (e.g., `apex_severity`, `ers_compliance`) map to panels and alerts.
