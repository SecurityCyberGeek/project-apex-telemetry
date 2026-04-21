# Project Apex – Agent Guidance

## Project purpose
Project Apex is an independent, security-focused telemetry and compliance validation platform for the 2026 FIA Formula 1 Technical Regulations. It ingests race telemetry, computes physics-based features (e.g., vertical energy in joules, engine temperature, ride height), and classifies events as GREEN, YELLOW, or RED for safety and compliance analysis.

On April 20, 2026, the FIA, all Team Principals, CEOs of Power Unit Manufacturers, and FOM unanimously agreed regulatory refinements effective from the Miami Grand Prix (Round 4, 2026). These introduce the following official FIA threshold values that Project Apex v1.2 must reflect:

- ERS peak MGU-K deployment: 350 kW (qualifying and race acceleration zones)
- ERS non-acceleration zone limit: 250 kW
- Race Boost cap: +150 kW (or current power level at activation, whichever is higher)
- Maximum permitted recharge per lap: 7 MJ (reduced from 8 MJ)
- Superclip duration target: approximately 2–4 seconds per lap

Core files:
- `production_validator_service_prod_2.py` – main validation and classification logic.
- `production_atlas_bridge.py` – telemetry bridge / event generator.
- `apex_mission_control_dashboard.json` – Splunk dashboard definition for Mission Control.

## Tech stack

- Python 3.x for validator and tooling.
- Splunk / SPL for dashboards and searches.

## How to run tests

Currently no automated tests. We will use pytest in this repo.

- Test command (once tests exist): `pytest`

## Coding standards

- Prefer small, pure functions with clear inputs/outputs.
- Do NOT add side effects (network calls, file writes) inside classification logic.
- Use type hints for new or refactored functions.
- Add structured logging where we emit anomaly classifications.
- Preserve existing behavior unless explicitly instructed otherwise.
- All regulatory threshold constants must include an inline comment citing their FIA source (regulation name, effective date).

## Roadmap focus for Codex

1. Add a pytest test suite for `production_validator_service_prod.py`.
2. Add a GitHub Actions CI workflow to run tests on push/PR.
3. Extend the validator to support an optional ERS state using the April 20, 2026 FIA regulatory values as named constants. ERS fields must be optional; v1.1 behavior must be preserved when they are absent.
4. Refactor for clarity: type hints, docstrings, logging.
5. Generate helper scripts / docs for Splunk dashboards.

## ERS constants to add in v1.2 (source: FIA April 20, 2026 regulatory refinements)

```python
# FIA 2026 Regulatory Refinements – effective Miami GP, April 20 2026 agreement
ERS_PEAK_DEPLOY_KW: float = 350.0      # Max MGU-K in quali + race accel zones
ERS_NON_ACCEL_DEPLOY_KW: float = 250.0 # MGU-K limit outside accel zones
ERS_BOOST_CAP_KW: float = 150.0        # Max Boost delta in race
ERS_MAX_RECHARGE_MJ: float = 7.0       # Max energy recharge per lap
ERS_SUPERCLIP_MAX_DURATION_S: float = 4.0  # Target max superclip seconds per lap
```
