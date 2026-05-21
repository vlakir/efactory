"""Domain: ThdSweepSpec, ThdMeasurementPoint, ThdSpectrum (T131 Phase C)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from adapters.outbound.fem_solver_getdp.material import FrohlichBHCurve
from domain.magnetic import Core, IsolationSide, MagneticComponent, OperatingPoint, Winding
from domain.simulation import HarmonicSample
from domain.thd import ThdMeasurementPoint, ThdSpectrum, ThdSweepSpec


def _make_component() -> MagneticComponent:
    return MagneticComponent(
        name='OPT_test',
        core=Core(
            shape_name='E42/15',
            material_name='Nanoperm 8000',
            gap_length_m=0.3e-3,
        ),
        windings=(
            Winding(name='pri', number_turns=1000, isolation_side=IsolationSide.PRIMARY),
            Winding(name='sec', number_turns=40, isolation_side=IsolationSide.SECONDARY),
        ),
        operating_point=OperatingPoint(
            frequency_hz=1000.0,
            primary_peak_voltage_v=100.0,
        ),
    )


def _make_bh_curve() -> FrohlichBHCurve:
    return FrohlichBHCurve.from_pyom_material(mu_initial=8000.0, b_sat=1.2)


def _make_harmonics(n_harmonics: int, fundamental_hz: float) -> tuple[HarmonicSample, ...]:
    return tuple(
        HarmonicSample(
            n=i,
            frequency_hz=i * fundamental_hz,
            magnitude=1.0 / (i + 1),
            phase_deg=0.0,
            normalized=1.0 / (i + 1),
        )
        for i in range(n_harmonics)
    )


def _make_minimal_spec(**overrides: object) -> ThdSweepSpec:
    defaults: dict[str, object] = {
        'component': _make_component(),
        'bh_curve': _make_bh_curve(),
        'a_core_m2': 2.5e-4,
        'l_path_m': 0.1,
        'r_primary_ohm': 200.0,
        'r_secondary_ohm': 0.3,
        'target_subckt_name': 'OPT_SE_5K_8',
        'input_source_ref': 'V_in',
        'voltage_per_root_power': 4.0,
        'frequencies_hz': (1000.0,),
        'output_powers_w': (1.0,),
    }
    defaults.update(overrides)
    return ThdSweepSpec(**defaults)  # type: ignore[arg-type]


def test_thd_sweep_spec_minimum_fields() -> None:
    spec = _make_minimal_spec()
    assert spec.frequencies_hz == (1000.0,)
    assert spec.output_powers_w == (1.0,)
    assert spec.load_ohm == 8.0
    assert spec.signal_node == 'v(load)'
    assert spec.n_harmonics == 10
    assert spec.cell_count == 1


def test_thd_sweep_spec_cell_count_matches_matrix() -> None:
    spec = _make_minimal_spec(
        frequencies_hz=(50.0, 1000.0, 10000.0),
        output_powers_w=(0.25, 1.0, 3.0),
    )
    assert spec.cell_count == 9


def test_thd_sweep_spec_rejects_empty_frequencies() -> None:
    with pytest.raises(ValidationError):
        _make_minimal_spec(frequencies_hz=())


def test_thd_sweep_spec_rejects_empty_powers() -> None:
    with pytest.raises(ValidationError):
        _make_minimal_spec(output_powers_w=())


def test_thd_sweep_spec_rejects_non_positive_frequency() -> None:
    with pytest.raises(ValidationError):
        _make_minimal_spec(frequencies_hz=(1000.0, 0.0))


def test_thd_sweep_spec_rejects_non_positive_power() -> None:
    with pytest.raises(ValidationError):
        _make_minimal_spec(output_powers_w=(1.0, -0.5))


def test_thd_sweep_spec_rejects_non_positive_geometry() -> None:
    with pytest.raises(ValidationError):
        _make_minimal_spec(a_core_m2=0.0)
    with pytest.raises(ValidationError):
        _make_minimal_spec(l_path_m=-0.1)


def test_thd_sweep_spec_rejects_empty_target_subckt_name() -> None:
    with pytest.raises(ValidationError):
        _make_minimal_spec(target_subckt_name='')


def test_thd_sweep_spec_rejects_n_harmonics_out_of_range() -> None:
    with pytest.raises(ValidationError):
        _make_minimal_spec(n_harmonics=2)  # < 3: dominant n>=2 не well-defined
    with pytest.raises(ValidationError):
        _make_minimal_spec(n_harmonics=21)


def test_thd_sweep_spec_is_frozen() -> None:
    spec = _make_minimal_spec()
    with pytest.raises(ValidationError):
        spec.load_ohm = 4.0  # type: ignore[misc]


def test_thd_measurement_point_construction() -> None:
    point = ThdMeasurementPoint(
        frequency_hz=1000.0,
        target_power_w=1.0,
        measured_power_w=0.95,
        thd_percent=2.5,
        dominant_harmonic_n=2,
        harmonics=_make_harmonics(10, 1000.0),
    )
    assert point.dominant_harmonic_n == 2
    assert len(point.harmonics) == 10


def test_thd_measurement_point_rejects_dominant_below_two() -> None:
    with pytest.raises(ValidationError):
        ThdMeasurementPoint(
            frequency_hz=1000.0,
            target_power_w=1.0,
            measured_power_w=1.0,
            thd_percent=2.0,
            dominant_harmonic_n=1,
            harmonics=_make_harmonics(10, 1000.0),
        )


def test_thd_measurement_point_rejects_negative_thd() -> None:
    with pytest.raises(ValidationError):
        ThdMeasurementPoint(
            frequency_hz=1000.0,
            target_power_w=1.0,
            measured_power_w=1.0,
            thd_percent=-1.0,
            dominant_harmonic_n=2,
            harmonics=_make_harmonics(10, 1000.0),
        )


def test_thd_spectrum_construction() -> None:
    points = (
        ThdMeasurementPoint(
            frequency_hz=1000.0,
            target_power_w=1.0,
            measured_power_w=1.0,
            thd_percent=2.5,
            dominant_harmonic_n=2,
            harmonics=_make_harmonics(10, 1000.0),
        ),
    )
    spectrum = ThdSpectrum(
        component_name='OPT_SE_5K_8',
        points=points,
        runtime_seconds=12.3,
    )
    assert spectrum.runtime_seconds == 12.3


def test_thd_spectrum_rejects_empty_points() -> None:
    with pytest.raises(ValidationError):
        ThdSpectrum(component_name='x', points=(), runtime_seconds=0.0)


def test_thd_spectrum_find_closest_within_tolerance() -> None:
    p_low = ThdMeasurementPoint(
        frequency_hz=1000.0,
        target_power_w=1.0,
        measured_power_w=0.95,
        thd_percent=2.0,
        dominant_harmonic_n=2,
        harmonics=_make_harmonics(10, 1000.0),
    )
    p_high = ThdMeasurementPoint(
        frequency_hz=1000.0,
        target_power_w=1.0,
        measured_power_w=1.15,
        thd_percent=3.0,
        dominant_harmonic_n=2,
        harmonics=_make_harmonics(10, 1000.0),
    )
    spectrum = ThdSpectrum(
        component_name='OPT',
        points=(p_low, p_high),
        runtime_seconds=10.0,
    )
    found = spectrum.find_closest(frequency_hz=1000.0, target_power_w=1.0)
    # |0.95-1.0|=0.05 ближе чем |1.15-1.0|=0.15
    assert found is p_low


def test_thd_spectrum_find_closest_raises_when_out_of_tolerance() -> None:
    point = ThdMeasurementPoint(
        frequency_hz=1000.0,
        target_power_w=1.0,
        measured_power_w=2.0,  # +100% от target
        thd_percent=2.0,
        dominant_harmonic_n=2,
        harmonics=_make_harmonics(10, 1000.0),
    )
    spectrum = ThdSpectrum(
        component_name='OPT',
        points=(point,),
        runtime_seconds=1.0,
    )
    with pytest.raises(ValueError, match='no measurement point'):
        spectrum.find_closest(
            frequency_hz=1000.0,
            target_power_w=1.0,
            power_tolerance=0.20,
        )
