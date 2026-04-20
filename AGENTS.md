# Project Apex – Agent Guidance

## Project purpose

Project Apex is an independent, security-focused telemetry and compliance validation platform for the 2026 FIA Formula 1 regulations. It ingests race telemetry, computes physics-based features (e.g., vertical energy in joules, engine temperature, ride height), and classifies events as GREEN, YELLOW, or RED for safety and compliance analysis.

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

## Roadmap focus for Codex

1. Add a pytest test suite for `production_validator_service_prod_2.py`.
2. Add a GitHub Actions CI workflow to run tests on push/PR.
3. Extend the validator to support an optional ERS "active harvesting" state, without breaking current behavior.
4. Refactor for clarity: type hints, docstrings, logging.
5. Generate helper scripts / docs for Splunk dashboards.