"""analyze_distortion_spectrum use case (T131 Phase C)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from adapters.outbound.fem_solver_getdp.material import FrohlichBHCurve
from application.analyze_distortion_spectrum import analyze_distortion_spectrum
from domain.magnetic import (
    Core,
    IsolationSide,
    MagneticComponent,
    OperatingPoint,
    Winding,
)
from domain.simulation import (
    FourierResult,
    HarmonicSample,
    SimulationResult,
)
from domain.thd import ThdSweepSpec
from ports.outbound.simulator import SimulationFailedError

if TYPE_CHECKING:
    from domain.simulation import AnalysisSpec


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


_BASE_NETLIST = (
    '* tube SE amp\n'
    'V_in /in 0 SIN(0 0 1000)\n'
    'X_TUBE /plate B+ /in K1 6P14P\n'
    'X_OPT /plate B+ /load 0 OPT_SE_5K_8\n'
    '.include /home/v/models/OPT_SE_5K_8.lib\n'
    'R_load /load 0 8\n'
    '.end\n'
)


def _make_spec(**overrides: object) -> ThdSweepSpec:
    defaults: dict[str, object] = {
        'component': _make_component(),
        'bh_curve': FrohlichBHCurve.from_pyom_material(mu_initial=8000.0, b_sat=1.2),
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


def _make_fourier_result(
    *,
    fundamental_magnitude: float = 4.0,  # peak; 4 V_peak → 2.83 V_rms → 1 W on 8Ω
    thd_percent: float = 2.5,
    fundamental_hz: float = 1000.0,
    n_harmonics: int = 10,
    h2_normalized: float = 0.025,
    h3_normalized: float = 0.012,
) -> FourierResult:
    samples = [
        HarmonicSample(n=0, frequency_hz=0.0, magnitude=0.0, phase_deg=0.0, normalized=0.0),
        HarmonicSample(
            n=1,
            frequency_hz=fundamental_hz,
            magnitude=fundamental_magnitude,
            phase_deg=0.0,
            normalized=1.0,
        ),
        HarmonicSample(
            n=2,
            frequency_hz=2 * fundamental_hz,
            magnitude=fundamental_magnitude * h2_normalized,
            phase_deg=0.0,
            normalized=h2_normalized,
        ),
        HarmonicSample(
            n=3,
            frequency_hz=3 * fundamental_hz,
            magnitude=fundamental_magnitude * h3_normalized,
            phase_deg=0.0,
            normalized=h3_normalized,
        ),
    ]
    # fill remaining with tiny noise
    for n in range(4, n_harmonics):
        samples.append(
            HarmonicSample(
                n=n,
                frequency_hz=n * fundamental_hz,
                magnitude=1e-6,
                phase_deg=0.0,
                normalized=1e-6,
            ),
        )
    return FourierResult(
        fundamental_hz=fundamental_hz,
        thd_percent=thd_percent,
        harmonics=tuple(samples),
    )


class FakeSimulator:
    """Simulator double — записывает вызовы, возвращает canned результаты."""

    def __init__(
        self,
        *,
        result_factory: object | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._result_factory = result_factory
        self._raises = raises
        self.calls: list[tuple[Path, AnalysisSpec, float]] = []

    async def run(
        self,
        netlist: Path,
        analysis: AnalysisSpec,
        *,
        timeout_seconds: float = 60.0,
    ) -> SimulationResult:
        self.calls.append((netlist, analysis, timeout_seconds))
        if self._raises is not None:
            raise self._raises
        # factory может зависеть от анализа (например, разные fundamental_hz)
        result_factory = self._result_factory
        if callable(result_factory):
            return result_factory(analysis)  # type: ignore[no-any-return]
        if isinstance(result_factory, SimulationResult):
            return result_factory
        msg = 'FakeSimulator: result_factory not configured'
        raise RuntimeError(msg)


def _write_netlist(tmp_path: Path) -> Path:
    netlist = tmp_path / 'base.cir'
    netlist.write_text(_BASE_NETLIST)
    return netlist


async def test_use_case_calls_simulator_per_matrix_cell(tmp_path: Path) -> None:
    base = _write_netlist(tmp_path)
    workdir = tmp_path / 'work'
    spec = _make_spec(
        frequencies_hz=(100.0, 1000.0, 10000.0),
        output_powers_w=(0.25, 1.0, 3.0),
    )
    sim = FakeSimulator(
        result_factory=lambda analysis: SimulationResult(
            fourier_result=_make_fourier_result(
                fundamental_hz=analysis.fundamental_hz,
            ),
        ),
    )

    spectrum = await analyze_distortion_spectrum(
        base_netlist=base,
        spec=spec,
        simulator=sim,
        workdir=workdir,
    )

    assert len(sim.calls) == 9
    assert len(spectrum.points) == 9
    assert spectrum.component_name == 'OPT_test'


async def test_use_case_computes_measured_power_from_fundamental(
    tmp_path: Path,
) -> None:
    base = _write_netlist(tmp_path)
    workdir = tmp_path / 'work'
    spec = _make_spec(load_ohm=8.0)
    # 4 V peak → 2.828 V rms → P = 2.828² / 8 = 1.0 W exactly
    sim = FakeSimulator(
        result_factory=lambda _: SimulationResult(
            fourier_result=_make_fourier_result(fundamental_magnitude=4.0),
        ),
    )

    spectrum = await analyze_distortion_spectrum(
        base_netlist=base,
        spec=spec,
        simulator=sim,
        workdir=workdir,
    )

    assert spectrum.points[0].measured_power_w == pytest.approx(1.0, abs=1e-9)
    assert spectrum.points[0].thd_percent == pytest.approx(2.5)


async def test_use_case_dominant_harmonic_selected_from_n_ge_two(
    tmp_path: Path,
) -> None:
    base = _write_netlist(tmp_path)
    workdir = tmp_path / 'work'
    spec = _make_spec()
    # h2 > h3 in normalized → dominant = 2
    sim = FakeSimulator(
        result_factory=lambda _: SimulationResult(
            fourier_result=_make_fourier_result(
                h2_normalized=0.08,
                h3_normalized=0.02,
            ),
        ),
    )

    spectrum = await analyze_distortion_spectrum(
        base_netlist=base,
        spec=spec,
        simulator=sim,
        workdir=workdir,
    )
    assert spectrum.points[0].dominant_harmonic_n == 2


async def test_use_case_dominant_harmonic_third_when_largest(
    tmp_path: Path,
) -> None:
    base = _write_netlist(tmp_path)
    workdir = tmp_path / 'work'
    spec = _make_spec()
    # h3 > h2 → dominant = 3
    sim = FakeSimulator(
        result_factory=lambda _: SimulationResult(
            fourier_result=_make_fourier_result(
                h2_normalized=0.02,
                h3_normalized=0.10,
            ),
        ),
    )

    spectrum = await analyze_distortion_spectrum(
        base_netlist=base,
        spec=spec,
        simulator=sim,
        workdir=workdir,
    )
    assert spectrum.points[0].dominant_harmonic_n == 3


async def test_use_case_voltage_calibration_uses_root_power_constant(
    tmp_path: Path,
) -> None:
    base = _write_netlist(tmp_path)
    workdir = tmp_path / 'work'
    # voltage_per_root_power=10 → at P=0.25 W: V_in = 10·√0.25 = 5
    spec = _make_spec(voltage_per_root_power=10.0, output_powers_w=(0.25,))
    sim = FakeSimulator(
        result_factory=lambda _: SimulationResult(
            fourier_result=_make_fourier_result(),
        ),
    )

    await analyze_distortion_spectrum(
        base_netlist=base,
        spec=spec,
        simulator=sim,
        workdir=workdir,
    )

    cell_files = list(workdir.glob('cell_*.cir'))
    assert len(cell_files) == 1
    text = cell_files[0].read_text()
    assert 'SIN(0 5 1000)' in text


async def test_use_case_writes_one_netlist_per_cell(tmp_path: Path) -> None:
    base = _write_netlist(tmp_path)
    workdir = tmp_path / 'work'
    spec = _make_spec(
        frequencies_hz=(50.0, 1000.0),
        output_powers_w=(0.5, 2.0),
    )
    sim = FakeSimulator(
        result_factory=lambda _: SimulationResult(
            fourier_result=_make_fourier_result(),
        ),
    )

    await analyze_distortion_spectrum(
        base_netlist=base,
        spec=spec,
        simulator=sim,
        workdir=workdir,
    )

    cells = sorted(p.name for p in workdir.glob('cell_*.cir'))
    assert len(cells) == 4
    # все имена различны и descriptive
    assert len(set(cells)) == 4


async def test_use_case_raises_on_simulator_failure(tmp_path: Path) -> None:
    base = _write_netlist(tmp_path)
    workdir = tmp_path / 'work'
    spec = _make_spec()
    sim = FakeSimulator(raises=SimulationFailedError('no convergence'))

    with pytest.raises(SimulationFailedError, match='no convergence'):
        await analyze_distortion_spectrum(
            base_netlist=base,
            spec=spec,
            simulator=sim,
            workdir=workdir,
        )


async def test_use_case_raises_when_fourier_result_missing(tmp_path: Path) -> None:
    base = _write_netlist(tmp_path)
    workdir = tmp_path / 'work'
    spec = _make_spec()
    sim = FakeSimulator(
        result_factory=lambda _: SimulationResult(
            operating_points={'v(load)': 0.0},  # wrong branch
        ),
    )

    with pytest.raises(SimulationFailedError, match='no fourier_result'):
        await analyze_distortion_spectrum(
            base_netlist=base,
            spec=spec,
            simulator=sim,
            workdir=workdir,
        )


async def test_use_case_raises_when_target_subckt_not_in_netlist(
    tmp_path: Path,
) -> None:
    base = tmp_path / 'no_include.cir'
    base.write_text(
        '* missing include\n'
        'V_in /in 0 SIN(0 1 1000)\n'
        'R1 /in 0 1k\n',
    )
    workdir = tmp_path / 'work'
    spec = _make_spec()
    sim = FakeSimulator(
        result_factory=lambda _: SimulationResult(
            fourier_result=_make_fourier_result(),
        ),
    )

    with pytest.raises(ValueError, match='OPT_SE_5K_8'):
        await analyze_distortion_spectrum(
            base_netlist=base,
            spec=spec,
            simulator=sim,
            workdir=workdir,
        )


async def test_use_case_raises_when_source_ref_missing(tmp_path: Path) -> None:
    base = tmp_path / 'no_source.cir'
    base.write_text(
        '* no sine source\n'
        '.include /home/v/OPT_SE_5K_8.lib\n'
        'X_OPT P1 P2 S1 S2 OPT_SE_5K_8\n'
        'R_load S1 S2 8\n',
    )
    workdir = tmp_path / 'work'
    spec = _make_spec()
    sim = FakeSimulator(
        result_factory=lambda _: SimulationResult(
            fourier_result=_make_fourier_result(),
        ),
    )

    with pytest.raises(ValueError, match='V_in'):
        await analyze_distortion_spectrum(
            base_netlist=base,
            spec=spec,
            simulator=sim,
            workdir=workdir,
        )


async def test_use_case_tran_parameters_derived_from_frequency(
    tmp_path: Path,
) -> None:
    base = _write_netlist(tmp_path)
    workdir = tmp_path / 'work'
    # 10 periods @ 1 kHz, 100 samples per period — стандартный default
    spec = _make_spec(
        frequencies_hz=(1000.0,),
        output_powers_w=(1.0,),
        periods_per_run=10,
        samples_per_period=100,
    )
    sim = FakeSimulator(
        result_factory=lambda _: SimulationResult(
            fourier_result=_make_fourier_result(),
        ),
    )

    await analyze_distortion_spectrum(
        base_netlist=base,
        spec=spec,
        simulator=sim,
        workdir=workdir,
    )

    netlist_arg, analysis_arg, _ = sim.calls[0]
    assert netlist_arg.name == 'cell_1000Hz_1000mW.cir'
    # FourierAnalysis branch с правильно derived tran
    assert analysis_arg.fundamental_hz == 1000.0
    assert math.isclose(analysis_arg.tran.t_stop, 10.0 / 1000.0, rel_tol=1e-9)
    assert math.isclose(
        analysis_arg.tran.t_step,
        (1.0 / 1000.0) / 100.0,
        rel_tol=1e-9,
    )


async def test_use_case_propagates_custom_timeout(tmp_path: Path) -> None:
    base = _write_netlist(tmp_path)
    workdir = tmp_path / 'work'
    spec = _make_spec()
    sim = FakeSimulator(
        result_factory=lambda _: SimulationResult(
            fourier_result=_make_fourier_result(),
        ),
    )

    await analyze_distortion_spectrum(
        base_netlist=base,
        spec=spec,
        simulator=sim,
        workdir=workdir,
        timeout_per_cell_seconds=10.0,
    )

    _, _, timeout = sim.calls[0]
    assert timeout == 10.0
