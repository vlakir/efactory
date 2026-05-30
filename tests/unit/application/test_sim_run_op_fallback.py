"""Unit tests для T145: sim_run OP-via-TRAN fallback.

Когда `enable_op_fallback=True` + `analysis = OpAnalysis()` —
sim_run **заменяет** `.OP` на `.TRAN ... uic=True`, ждёт settled
DC, и собирает synthetic operating_points из последних samples.
Полезно для tube/saturable circuits где `.OP` solver сходится к
trivial idle solution (V(plate)=0, tube не conducts).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from application.sim_run import (
    _extract_op_from_tran_tail,
    sim_run,
)
from domain.simulation import (
    OpAnalysis,
    SimulationResult,
    TimeSeries,
    TranAnalysis,
)

if TYPE_CHECKING:
    from domain.simulation import AnalysisSpec


# ────────── _extract_op_from_tran_tail ──────────


def test_extract_op_takes_average_over_settled_tail() -> None:
    """Settled signals: tail mean — реальный bias."""
    n = 100
    time = tuple(i * 1e-4 for i in range(n))
    # v(plate) settles at 230V, fluctuates ±1V over time.
    v_plate = tuple(230.0 + math.sin(i * 0.1) for i in range(n))
    # v(cathode) settles at 12V.
    v_cathode = tuple(12.0 + 0.5 * math.cos(i * 0.05) for i in range(n))
    ts = TimeSeries(time=time, traces={
        'v(plate)': v_plate,
        'v(cathode)': v_cathode,
    })

    op = _extract_op_from_tran_tail(ts, fraction=0.1)

    # Average of last 10 samples ≈ steady-state.
    assert op['v(plate)'] == pytest.approx(230.0, abs=2.0)
    assert op['v(cathode)'] == pytest.approx(12.0, abs=2.0)


def test_extract_op_default_fraction_is_10_percent() -> None:
    n = 100
    time = tuple(i * 1e-4 for i in range(n))
    # Ramp from 0 to 100, settle at 100.
    values = tuple(100.0 if i >= 90 else float(i) for i in range(n))
    ts = TimeSeries(time=time, traces={'v(x)': values})

    op = _extract_op_from_tran_tail(ts)

    # Default fraction=0.1 → last 10 samples = [100.0]*10 → 100.
    assert op['v(x)'] == pytest.approx(100.0)


def test_extract_op_handles_single_sample() -> None:
    ts = TimeSeries(time=(0.1,), traces={'v(x)': (42.0,)})
    op = _extract_op_from_tran_tail(ts)
    assert op['v(x)'] == pytest.approx(42.0)


def test_extract_op_clamps_fraction_to_at_least_one_sample() -> None:
    """fraction=0.01 on 10-sample series → take at least 1."""
    ts = TimeSeries(time=tuple(range(10)), traces={'v(x)': tuple(range(10))})
    op = _extract_op_from_tran_tail(ts, fraction=0.01)
    # Last 1 sample = 9.0.
    assert op['v(x)'] == pytest.approx(9.0)


# ────────── sim_run with fallback ──────────


class _RecordingSimulator:
    """Simulator double — records calls, returns scripted результат per call."""

    def __init__(self) -> None:
        self.calls: list[tuple[Path, AnalysisSpec, float]] = []
        self._responses: list[SimulationResult] = []

    def queue(self, result: SimulationResult) -> None:
        self._responses.append(result)

    async def run(
        self,
        netlist: Path,
        analysis: AnalysisSpec,
        *,
        timeout_seconds: float = 60.0,
    ) -> SimulationResult:
        self.calls.append((netlist, analysis, timeout_seconds))
        return self._responses.pop(0)


def _settled_tran_result() -> SimulationResult:
    """TRAN с явным settled bias (plate=230, cathode=12)."""
    n = 50
    time = tuple(i * 1e-3 for i in range(n))
    traces = {
        'v(plate)': tuple(230.0 for _ in range(n)),
        'v(cathode)': tuple(12.0 for _ in range(n)),
        'i(v1)': tuple(-0.045 for _ in range(n)),
    }
    return SimulationResult(time_series=TimeSeries(time=time, traces=traces))


async def test_sim_run_default_does_not_use_fallback(tmp_path: Path) -> None:
    """enable_op_fallback=False (default) → normal OP path."""
    netlist = tmp_path / 'net.cir'
    netlist.write_text('* test\n')
    sim = _RecordingSimulator()
    sim.queue(SimulationResult(operating_points={'v(x)': 1.0}))

    result = await sim_run(
        netlist=netlist,
        analysis=OpAnalysis(),
        simulator=sim,
    )

    assert len(sim.calls) == 1
    # Verified called with OpAnalysis, not TranAnalysis.
    _, analysis_call, _ = sim.calls[0]
    assert isinstance(analysis_call, OpAnalysis)
    assert result.operating_points == {'v(x)': 1.0}


async def test_sim_run_with_fallback_uses_tran(tmp_path: Path) -> None:
    """enable_op_fallback=True + OpAnalysis → simulator получает
    TranAnalysis(uic=True), не OpAnalysis."""
    netlist = tmp_path / 'net.cir'
    netlist.write_text('* test\n')
    sim = _RecordingSimulator()
    sim.queue(_settled_tran_result())

    result = await sim_run(
        netlist=netlist,
        analysis=OpAnalysis(),
        simulator=sim,
        enable_op_fallback=True,
    )

    assert len(sim.calls) == 1
    _, analysis_call, _ = sim.calls[0]
    assert isinstance(analysis_call, TranAnalysis), (
        f'expected TranAnalysis, got {type(analysis_call).__name__}'
    )
    assert analysis_call.uic is True
    # Result has synthetic operating_points (not time_series).
    assert result.operating_points is not None
    assert result.time_series is None
    assert result.operating_points['v(plate)'] == pytest.approx(230.0)
    assert result.operating_points['v(cathode)'] == pytest.approx(12.0)


async def test_sim_run_fallback_rejects_non_op_analysis(
    tmp_path: Path,
) -> None:
    """enable_op_fallback=True + AcAnalysis → ValueError (только для OP)."""
    netlist = tmp_path / 'net.cir'
    netlist.write_text('* test\n')
    sim = _RecordingSimulator()

    with pytest.raises(ValueError, match='enable_op_fallback'):
        await sim_run(
            netlist=netlist,
            analysis=TranAnalysis(t_step=1e-6, t_stop=1e-3),
            simulator=sim,
            enable_op_fallback=True,
        )


async def test_sim_run_fallback_uses_default_tran_params(
    tmp_path: Path,
) -> None:
    """Default TRAN params для fallback: t_step=1e-6, t_stop=100e-3, uic=True."""
    netlist = tmp_path / 'net.cir'
    netlist.write_text('* test\n')
    sim = _RecordingSimulator()
    sim.queue(_settled_tran_result())

    await sim_run(
        netlist=netlist,
        analysis=OpAnalysis(),
        simulator=sim,
        enable_op_fallback=True,
    )

    _, analysis_call, _ = sim.calls[0]
    assert isinstance(analysis_call, TranAnalysis)
    assert analysis_call.t_step == pytest.approx(1e-6)
    assert analysis_call.t_stop == pytest.approx(100e-3)
    assert analysis_call.uic is True


async def test_sim_run_fallback_custom_tran_params(tmp_path: Path) -> None:
    """Caller может override t_stop через op_fallback_t_stop."""
    netlist = tmp_path / 'net.cir'
    netlist.write_text('* test\n')
    sim = _RecordingSimulator()
    sim.queue(_settled_tran_result())

    await sim_run(
        netlist=netlist,
        analysis=OpAnalysis(),
        simulator=sim,
        enable_op_fallback=True,
        op_fallback_t_stop=50e-3,
    )

    _, analysis_call, _ = sim.calls[0]
    assert isinstance(analysis_call, TranAnalysis)
    assert analysis_call.t_stop == pytest.approx(50e-3)


async def test_sim_run_fallback_raises_if_tran_returns_no_time_series(
    tmp_path: Path,
) -> None:
    """Если TRAN внутри fallback вернул не-tran результат — ошибка."""
    netlist = tmp_path / 'net.cir'
    netlist.write_text('* test\n')
    sim = _RecordingSimulator()
    sim.queue(SimulationResult(operating_points={'v(x)': 1.0}))  # вместо TRAN

    with pytest.raises(ValueError, match='time_series'):
        await sim_run(
            netlist=netlist,
            analysis=OpAnalysis(),
            simulator=sim,
            enable_op_fallback=True,
        )
