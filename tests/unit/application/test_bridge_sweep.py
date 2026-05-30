"""bridge_sweep generalised use case (T022 Phase B): metric dispatch."""

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from application import bridge_sweep as bs_module
from application.bridge_sweep import (
    MAX_COMBINATIONS_DEFAULT,
    SweepConfig,
    SweepRun,
    bridge_sweep,
)


@pytest.fixture(autouse=True)
def _disable_edit_component_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bridge_sweep unit-tests фокусируются на dispatch+flow; edit
    проверяется отдельно (test_edit_component_value)."""
    monkeypatch.setattr(
        bs_module, 'edit_component_value',
        lambda *args, **kwargs: None,  # noqa: ARG005
    )
from domain.simulation import (
    AcSweep,
    FourierResult,
    HarmonicSample,
    SimulationResult,
    TimeSeries,
)
from ports.outbound.schematic_exporter import SchematicExportError
from ports.outbound.simulator import SimulationFailedError

if TYPE_CHECKING:
    from collections.abc import Callable

    from domain.simulation import AnalysisSpec


# ────────── netlist fixtures ──────────


_NETLIST = (
    '* trivial divider\n'
    'V1 /in 0 dc=0 ac=1\n'
    'R1 /in /out 1k\n'
    'R2 /out 0 1k\n'
)


def _write_schematic(tmp_path: Path) -> Path:
    """Plain text-file masquerading as schematic — fake exporter копирует as-is."""
    sch = tmp_path / 'fake.kicad_sch'
    sch.write_text('* fake schematic\n')
    return sch


# ────────── port doubles ──────────


class FakeSchematicExporter:
    """Кладёт _NETLIST в указанный output path; не зовёт kicad-cli."""

    def __init__(self, content: str = _NETLIST) -> None:
        self._content = content
        self.calls: list[tuple[Path, Path]] = []

    async def export_spice_netlist(self, schematic: Path, output: Path) -> Path:
        self.calls.append((schematic, output))
        output.write_text(self._content)
        return output


class FailingExporter:
    def __init__(self, msg: str = 'kicad-cli failed') -> None:
        self._msg = msg

    async def export_spice_netlist(
        self, schematic: Path, output: Path,
    ) -> Path:
        raise SchematicExportError(self._msg)


class FakeSimulator:
    def __init__(
        self,
        result_factory: Callable[[AnalysisSpec], SimulationResult],
    ) -> None:
        self._factory = result_factory
        self.calls: list[tuple[Path, AnalysisSpec, float]] = []

    async def run(
        self,
        netlist: Path,
        analysis: AnalysisSpec,
        *,
        timeout_seconds: float = 60.0,
    ) -> SimulationResult:
        self.calls.append((netlist, analysis, timeout_seconds))
        return self._factory(analysis)


class FailingSimulator:
    def __init__(self, msg: str = 'singular matrix') -> None:
        self._msg = msg

    async def run(
        self,
        netlist: Path,
        analysis: AnalysisSpec,
        *,
        timeout_seconds: float = 60.0,
    ) -> SimulationResult:
        raise SimulationFailedError(self._msg)


class FakeNetlistEditor:
    """Min NetlistEditor double; identity-pass на substitution, fixed V_in."""

    def substitute_subckt_library(
        self, netlist_text: str,
        target_subckt_name: str,  # noqa: ARG002
        new_subckt_text: str,  # noqa: ARG002
    ) -> str:
        return netlist_text

    def set_sin_source_amplitude(
        self,
        netlist_text: str,
        *,
        source_ref: str,  # noqa: ARG002
        amplitude_peak: float,  # noqa: ARG002
        frequency_hz: float,  # noqa: ARG002
        offset: float = 0.0,  # noqa: ARG002
    ) -> str:
        return netlist_text

    def ensure_ac_modifier(
        self,
        netlist_text: str,
        *,
        source_ref: str,  # noqa: ARG002
        ac_magnitude: float = 1.0,  # noqa: ARG002
    ) -> str:
        return netlist_text

    def find_top_level_v_sources(self, netlist_text: str) -> tuple[str, ...]:  # noqa: ARG002
        return ('V1',)


# ────────── result factories ──────────


def _op_result(_: AnalysisSpec) -> SimulationResult:
    return SimulationResult(
        operating_points={'v(/in)': 0.0, 'v(/out)': 0.5, 'i(v1)': -0.0005},
    )


def _gain_small_factory(linear_gain: float) -> Callable[[AnalysisSpec], SimulationResult]:
    def factory(_: AnalysisSpec) -> SimulationResult:
        return SimulationResult(
            ac_sweep=AcSweep(
                frequency=(1000.0, 1000.1),
                traces_real={'v(load)': (linear_gain, linear_gain)},
                traces_imag={'v(load)': (0.0, 0.0)},
            ),
        )
    return factory


def _gain_large_factory(
    linear_gain: float, v_in_peak: float,
) -> Callable[[AnalysisSpec], SimulationResult]:
    def factory(_: AnalysisSpec) -> SimulationResult:
        n = 1000
        t_stop = 0.01
        time = tuple(i * t_stop / n for i in range(n))
        v_in = tuple(v_in_peak * math.sin(2 * math.pi * 1000.0 * t) for t in time)
        v_out = tuple(v * linear_gain for v in v_in)
        return SimulationResult(
            time_series=TimeSeries(
                time=time,
                traces={'V1': v_in, 'v(load)': v_out},
            ),
        )
    return factory


def _bandwidth_factory(
    midband_gain: float,
) -> Callable[[AnalysisSpec], SimulationResult]:
    """AC sweep с плоской АЧХ — endpoints = f_low/f_high (3dB не достигнут)."""
    def factory(_: AnalysisSpec) -> SimulationResult:
        freqs = (1.0, 100.0, 10000.0, 1e6)
        traces = {'v(load)': tuple([midband_gain] * len(freqs))}
        return SimulationResult(
            ac_sweep=AcSweep(
                frequency=freqs,
                traces_real=traces,
                traces_imag={'v(load)': tuple([0.0] * len(freqs))},
            ),
        )
    return factory


def _thd_factory(thd_percent: float) -> Callable[[AnalysisSpec], SimulationResult]:
    """ngspice fourier result (single-branch SimulationResult invariant)."""
    def factory(_: AnalysisSpec) -> SimulationResult:
        return SimulationResult(
            fourier_result=FourierResult(
                fundamental_hz=1000.0,
                thd_percent=thd_percent,
                harmonics=(
                    HarmonicSample(
                        n=1, frequency_hz=1000.0, magnitude=1.0,
                        phase_deg=0.0, normalized=1.0,
                    ),
                    HarmonicSample(
                        n=2, frequency_hz=2000.0,
                        magnitude=thd_percent / 100.0,
                        phase_deg=0.0, normalized=thd_percent / 100.0,
                    ),
                ),
            ),
        )
    return factory


# ────────── Happy paths per metric ──────────


async def test_op_metric_populates_values_from_operating_points(
    tmp_path: Path,
) -> None:
    sch = _write_schematic(tmp_path)
    cfg = SweepConfig(metric='op')

    runs = await bridge_sweep(
        schematic=sch,
        parameters={'R1': ['1k', '10k']},
        config=cfg,
        exporter=FakeSchematicExporter(),
        simulator=FakeSimulator(_op_result),
        netlist_editor=None,
    )

    assert len(runs) == 2
    for run in runs:
        assert run.error is None
        assert run.values is not None
        assert run.values['v(/in)'] == pytest.approx(0.0)
        assert run.values['v(/out)'] == pytest.approx(0.5)
        assert run.values['i(v1)'] == pytest.approx(-0.0005)


async def test_gain_small_metric_populates_gain_db_and_linear(
    tmp_path: Path,
) -> None:
    sch = _write_schematic(tmp_path)
    cfg = SweepConfig(metric='gain', mode='small', frequency_hz=1000.0)

    runs = await bridge_sweep(
        schematic=sch,
        parameters={'R1': ['1k', '2k']},
        config=cfg,
        exporter=FakeSchematicExporter(),
        simulator=FakeSimulator(_gain_small_factory(10.0)),
        netlist_editor=FakeNetlistEditor(),
    )

    assert len(runs) == 2
    for run in runs:
        assert run.values is not None
        assert run.values['gain_linear'] == pytest.approx(10.0)
        assert run.values['gain_db'] == pytest.approx(20.0)


async def test_gain_large_metric_populates_gain_columns(tmp_path: Path) -> None:
    sch = _write_schematic(tmp_path)
    cfg = SweepConfig(
        metric='gain', mode='large', frequency_hz=1000.0, v_in_peak=0.1,
        input_signal='V1',
    )

    runs = await bridge_sweep(
        schematic=sch,
        parameters={'R1': ['1k']},
        config=cfg,
        exporter=FakeSchematicExporter(),
        simulator=FakeSimulator(_gain_large_factory(5.0, v_in_peak=0.1)),
        netlist_editor=FakeNetlistEditor(),
    )

    assert len(runs) == 1
    assert runs[0].values is not None
    assert runs[0].values['gain_linear'] == pytest.approx(5.0, rel=0.05)


async def test_bandwidth_metric_populates_f_low_f_high_bandwidth(
    tmp_path: Path,
) -> None:
    sch = _write_schematic(tmp_path)
    cfg = SweepConfig(metric='bandwidth', f_low_hz=1.0, f_high_hz=1e6)

    runs = await bridge_sweep(
        schematic=sch,
        parameters={'R1': ['1k']},
        config=cfg,
        exporter=FakeSchematicExporter(),
        simulator=FakeSimulator(_bandwidth_factory(midband_gain=10.0)),
        netlist_editor=FakeNetlistEditor(),
    )

    assert len(runs) == 1
    assert runs[0].values is not None
    # Плоская АЧХ → endpoints = f_low/f_high.
    assert runs[0].values['f_low_hz'] == pytest.approx(1.0)
    assert runs[0].values['f_high_hz'] == pytest.approx(1e6)
    assert runs[0].values['bandwidth_hz'] == pytest.approx(1e6 - 1.0)


async def test_thd_metric_populates_thd_columns(tmp_path: Path) -> None:
    sch = _write_schematic(tmp_path)
    cfg = SweepConfig(
        metric='thd', frequency_hz=1000.0, v_in_peak=0.1,
    )

    runs = await bridge_sweep(
        schematic=sch,
        parameters={'R1': ['1k']},
        config=cfg,
        exporter=FakeSchematicExporter(),
        simulator=FakeSimulator(_thd_factory(thd_percent=5.0)),
        netlist_editor=FakeNetlistEditor(),
    )

    assert len(runs) == 1
    assert runs[0].values is not None
    assert runs[0].values['thd_percent'] == pytest.approx(5.0)
    assert runs[0].values['dominant_harmonic_n'] == 2
    assert runs[0].values['dominant_harmonic_percent'] == pytest.approx(5.0)


# ────────── Failure modes (Q-D → a: continue on failure) ──────────


async def test_export_failure_records_error_continues_sweep(tmp_path: Path) -> None:
    sch = _write_schematic(tmp_path)
    cfg = SweepConfig(metric='op')

    runs = await bridge_sweep(
        schematic=sch,
        parameters={'R1': ['1k', '2k']},
        config=cfg,
        exporter=FailingExporter('export blew up'),
        simulator=FakeSimulator(_op_result),
        netlist_editor=None,
    )

    assert len(runs) == 2
    for run in runs:
        assert run.error is not None
        assert 'export' in run.error
        assert run.result is None
        # T022 A4: values=None для failed combination.
        assert run.values is None


async def test_sim_failure_records_error_continues_sweep(tmp_path: Path) -> None:
    sch = _write_schematic(tmp_path)
    cfg = SweepConfig(metric='op')

    runs = await bridge_sweep(
        schematic=sch,
        parameters={'R1': ['1k', '2k']},
        config=cfg,
        exporter=FakeSchematicExporter(),
        simulator=FailingSimulator('singular matrix'),
        netlist_editor=None,
    )

    assert len(runs) == 2
    for run in runs:
        assert run.error is not None
        assert 'sim' in run.error.lower() or 'singular' in run.error.lower()
        assert run.values is None


# ────────── max_combinations hard cap ──────────


async def test_n_over_hard_cap_raises_value_error(tmp_path: Path) -> None:
    sch = _write_schematic(tmp_path)
    cfg = SweepConfig(metric='op')

    # default cap = MAX_COMBINATIONS_DEFAULT (100). 11×10 = 110 > 100.
    parameters = {
        'R1': [f'{i}k' for i in range(1, 12)],   # 11 values
        'C1': [f'{i}n' for i in range(1, 11)],   # 10 values
    }
    assert len(parameters['R1']) * len(parameters['C1']) > MAX_COMBINATIONS_DEFAULT

    with pytest.raises(ValueError, match='combinations'):
        await bridge_sweep(
            schematic=sch,
            parameters=parameters,
            config=cfg,
            exporter=FakeSchematicExporter(),
            simulator=FakeSimulator(_op_result),
            netlist_editor=None,
        )


async def test_n_over_default_cap_allowed_with_override(tmp_path: Path) -> None:
    sch = _write_schematic(tmp_path)
    cfg = SweepConfig(metric='op')
    parameters = {
        'R1': [f'{i}k' for i in range(1, 12)],
        'C1': [f'{i}n' for i in range(1, 11)],
    }

    runs = await bridge_sweep(
        schematic=sch,
        parameters=parameters,
        config=cfg,
        exporter=FakeSchematicExporter(),
        simulator=FakeSimulator(_op_result),
        netlist_editor=None,
        max_combinations=200,
    )
    assert len(runs) == 110


# ────────── return type still SweepRun (A4 backward-compat) ──────────


async def test_op_metric_returns_sweep_run_with_result_and_values(
    tmp_path: Path,
) -> None:
    """A4: result остаётся (legacy) + values добавлен."""
    sch = _write_schematic(tmp_path)
    cfg = SweepConfig(metric='op')

    runs = await bridge_sweep(
        schematic=sch,
        parameters={'R1': ['1k']},
        config=cfg,
        exporter=FakeSchematicExporter(),
        simulator=FakeSimulator(_op_result),
        netlist_editor=None,
    )

    assert isinstance(runs[0], SweepRun)
    assert runs[0].result is not None  # legacy path: result заполнен.
    assert runs[0].values is not None  # new path: values заполнен.
