import pytest

from src import production_validator_service_prod as validator


@pytest.mark.parametrize("fuel_kg", [0.0, validator.MAX_FUEL_LOAD_KG])
def test_calculate_vertical_energy_matches_dynamic_mass_formula(fuel_kg: float) -> None:
    vz = 0.5
    expected = 0.5 * (validator.CAR_MIN_MASS_KG + fuel_kg) * (vz ** 2)
    observed = validator.calculate_vertical_energy(vz=vz, fuel_load_kg=fuel_kg)
    assert observed == pytest.approx(expected)


def test_calculate_vertical_energy_full_fuel_is_higher_than_empty() -> None:
    vz = 0.5
    energy_empty = validator.calculate_vertical_energy(vz=vz, fuel_load_kg=0.0)
    energy_full = validator.calculate_vertical_energy(
        vz=vz,
        fuel_load_kg=validator.MAX_FUEL_LOAD_KG,
    )
    assert energy_full > energy_empty


@pytest.mark.parametrize(
    "name,inputs,expected",
    [
        (
            "green_low_energy_standard_temp",
            lambda m: dict(
                engine_temp=m.THERMAL_THRESHOLD_C - 0.1,
                energy_joules=m.ENERGY_LIMIT_J - 1.0,
                ride_height=m.AERO_STALL_RH_MM + 5.0,
            ),
            ("LEGAL", "GREEN", "STANDARD"),
        ),
        (
            "yellow_elevated_temp_only",
            lambda m: dict(
                engine_temp=m.THERMAL_THRESHOLD_C + 0.1,
                energy_joules=m.THERMAL_ENERGY_LIMIT_J - 0.1,
                ride_height=m.AERO_STALL_RH_MM + 5.0,
            ),
            ("WARNING: ELEVATED_TEMP", "YELLOW", "HIGH_COMPRESSION"),
        ),
        (
            "yellow_torque_unconfirmed",
            lambda m: dict(
                engine_temp=m.THERMAL_THRESHOLD_C + 0.1,
                energy_joules=m.THERMAL_ENERGY_LIMIT_J + 0.1,
                ride_height=m.AERO_STALL_RH_MM + 0.1,
            ),
            ("WARNING: TORQUE_ANOMALY_UNCONFIRMED", "YELLOW", "HIGH_COMPRESSION"),
        ),
        (
            "red_torque_confirmed",
            lambda m: dict(
                engine_temp=m.THERMAL_THRESHOLD_C + 0.1,
                energy_joules=m.THERMAL_ENERGY_LIMIT_J + 0.1,
                ride_height=m.AERO_STALL_RH_MM - 0.1,
            ),
            ("CRITICAL: TORQUE_ANOMALY_CONFIRMED", "RED", "HIGH_COMPRESSION"),
        ),
    ],
)
def test_classify_event_branches(name, inputs, expected) -> None:
    result = validator.classify_event(**inputs(validator))
    compliance_status, apex_severity, _apex_status, _apex_message, thermal_mode = result

    assert (compliance_status, apex_severity, thermal_mode) == expected, name