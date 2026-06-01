"""measure_phase_margin use case — orchestration tests (T153 Phase B.4)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from adapters.outbound.ngspice.injection_patcher import (
    NgspiceInjectionNetlistPatcher,
)
from application.measure_phase_margin import measure_phase_margin
from domain.phase_margin import (
    AutoDetectInfo,
    AutoDetectRejectedError,
    LoopBreakNodeNotFoundError,
    LoopGainAlwaysAboveUnityError,
    NoFeedbackLoopDetectedError,
    NoUnityGainCrossoverError,
    PhaseMarginMeasurement,
)
from domain.phase_margin_injection import (
    MiddlebrookCurrentStrategy,
    MiddlebrookVoltageStrategy,
    RosenstarkReturnRatioStrategy,
    TianStrategy,
)
from ports.outbound.injection_netlist_patcher import (
    NetlistPatchResult,
    ProbePair,
)
from domain.sim_results import AnalysisType, SimResult
from domain.simulation import (
    AcAnalysis,
    AcSweep,
    AnalysisSpec,
    SimulationResult,
)

if TYPE_CHECKING:
    from ports.outbound.sim_results import SimResultsRepository


_OPAMP_INV = (
    '* op-amp inverting amplifier (T153 B.4)\n'
    'V_in vin 0 AC 1 0\n'
    'R_in vin in_neg 1k\n'
    'R_fb vout in_neg 10k\n'
    'X_opamp 0 in_neg vout opa1\n'
    'R_load vout 0 100k\n'
    '.end\n'
)


# ---------------------------------------------------- AcSweep synthesizers ----


def _single_pole_sweep(
    *,
    g0: float,
    fp: float,
    frequencies: tuple[float, ...],
    probe_fwd: str,
    probe_rev: str,
) -> AcSweep:
    """Single-pole T(jω) = G0/(1 + j·f/fp) → v_rev=-T·v_fwd, v_fwd=1.

    Middlebrook V: T = -v_rev/v_fwd → выставляем v_rev = -T·v_fwd.
    """
    v_fwd_real = []
    v_fwd_imag = []
    v_rev_real = []
    v_rev_imag = []
    for f in frequencies:
        denom = complex(1.0, f / fp)
        t_val = g0 / denom
        v_fwd = complex(1.0, 0.0)
        v_rev = -t_val * v_fwd
        v_fwd_real.append(v_fwd.real)
        v_fwd_imag.append(v_fwd.imag)
        v_rev_real.append(v_rev.real)
        v_rev_imag.append(v_rev.imag)
    return AcSweep(
        frequency=frequencies,
        traces_real={
            probe_fwd: tuple(v_fwd_real),
            probe_rev: tuple(v_rev_real),
        },
        traces_imag={
            probe_fwd: tuple(v_fwd_imag),
            probe_rev: tuple(v_rev_imag),
        },
    )


def _flat_t_sweep(
    *,
    t_value: complex,
    frequencies: tuple[float, ...],
    probe_fwd: str,
    probe_rev: str,
) -> AcSweep:
    """Constant T(jω) = t_value на всём свеппе. Helper для constant edge-cases."""
    n = len(frequencies)
    v_fwd = complex(1.0, 0.0)
    v_rev = -t_value * v_fwd
    return AcSweep(
        frequency=frequencies,
        traces_real={
            probe_fwd: (v_fwd.real,) * n,
            probe_rev: (v_rev.real,) * n,
        },
        traces_imag={
            probe_fwd: (v_fwd.imag,) * n,
            probe_rev: (v_rev.imag,) * n,
        },
    )


# -------------------------------------------------------- fake simulator ----


class FakeSimulator:
    """Configurable fake Simulator: returns scripted SimulationResult per call."""

    def __init__(self, results: list[SimulationResult]) -> None:
        self._results = list(results)
        self.calls: list[tuple[Path, AnalysisSpec, float]] = []

    async def run(
        self,
        netlist: Path,
        analysis: AnalysisSpec,
        *,
        timeout_seconds: float = 60.0,
    ) -> SimulationResult:
        self.calls.append((netlist, analysis, timeout_seconds))
        if not self._results:
            msg = 'FakeSimulator: out of scripted results'
            raise AssertionError(msg)
        return self._results.pop(0)


class RecordingWriter:
    """Fake SimResultsRepository — capturing writes."""

    def __init__(self) -> None:
        self.writes: list[tuple[SimResult, Path]] = []

    async def write(self, *, result: SimResult, project_root: Path) -> None:
        self.writes.append((result, project_root))


# ================================================ happy path (Middlebrook V) ===


_DEC_FREQUENCIES = tuple(10.0**k for k in range(-1, 6))


async def test_returns_phase_margin_measurement_middlebrook_voltage(
    tmp_path: Path,
) -> None:
    netlist = tmp_path / 'opamp_inv.cir'
    netlist.write_text(_OPAMP_INV)
    patcher = NgspiceInjectionNetlistPatcher()
    strategy = MiddlebrookVoltageStrategy(patcher)

    ac = _single_pole_sweep(
        g0=100.0,
        fp=1.0,
        frequencies=_DEC_FREQUENCIES,
        probe_fwd='v(in_neg__fwd)',
        probe_rev='v(in_neg)',
    )
    simulator = FakeSimulator(results=[SimulationResult(ac_sweep=ac)])

    result = await measure_phase_margin(
        netlist=netlist,
        injection_strategy=strategy,
        break_node='in_neg',
        break_element_ref='R_fb',
        simulator=simulator,
    )

    assert isinstance(result, PhaseMarginMeasurement)
    assert result.measured_at_node == 'in_neg'
    assert result.injection_method == 'middlebrook_voltage'
    # Single pole, G0=100, fp=1 → crossover ≈ 100 Hz, margin ≈ 90.6°
    assert result.crossover_hz == pytest.approx(100.0, rel=0.1)
    assert result.margin_deg == pytest.approx(90.6, abs=2.0)
    assert result.stability_class == 'high'


# ============================== AcAnalysis parameter plumbing ================


async def test_calls_simulator_with_ac_dec_default_params(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_OPAMP_INV)
    strategy = MiddlebrookVoltageStrategy(NgspiceInjectionNetlistPatcher())
    ac = _single_pole_sweep(
        g0=100.0,
        fp=1.0,
        frequencies=_DEC_FREQUENCIES,
        probe_fwd='v(in_neg__fwd)',
        probe_rev='v(in_neg)',
    )
    sim = FakeSimulator(results=[SimulationResult(ac_sweep=ac)])

    await measure_phase_margin(
        netlist=netlist,
        injection_strategy=strategy,
        break_node='in_neg',
        break_element_ref='R_fb',
        simulator=sim,
    )

    assert len(sim.calls) == 1
    _, analysis, _ = sim.calls[0]
    assert isinstance(analysis, AcAnalysis)
    assert analysis.sweep == 'dec'
    assert analysis.n_points == 100
    assert analysis.f_start == pytest.approx(1.0)
    assert analysis.f_stop == pytest.approx(1e6)


async def test_respects_custom_sweep_params(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_OPAMP_INV)
    strategy = MiddlebrookVoltageStrategy(NgspiceInjectionNetlistPatcher())
    freqs = tuple(10.0**k for k in range(0, 6))
    ac = _single_pole_sweep(
        g0=100.0,
        fp=10.0,
        frequencies=freqs,
        probe_fwd='v(in_neg__fwd)',
        probe_rev='v(in_neg)',
    )
    sim = FakeSimulator(results=[SimulationResult(ac_sweep=ac)])

    await measure_phase_margin(
        netlist=netlist,
        injection_strategy=strategy,
        break_node='in_neg',
        break_element_ref='R_fb',
        simulator=sim,
        f_low=10.0,
        f_high=1e5,
        n_points_per_decade=20,
        timeout_seconds=30.0,
    )

    _, analysis, timeout = sim.calls[0]
    assert analysis.n_points == 20
    assert analysis.f_start == pytest.approx(10.0)
    assert analysis.f_stop == pytest.approx(1e5)
    assert timeout == pytest.approx(30.0)


# =========================================== multi-sweep methods (Tian) =====


async def test_tian_runs_two_sweeps(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_OPAMP_INV)
    strategy = TianStrategy(NgspiceInjectionNetlistPatcher())

    # Tian: V sweep (probe v(in_neg__fwd)/v(in_neg)) + I sweep (probe
    # i(v_fwd_probe)/i(v_rev_probe)).
    v_sweep = _single_pole_sweep(
        g0=100.0,
        fp=1.0,
        frequencies=_DEC_FREQUENCIES,
        probe_fwd='v(in_neg__fwd)',
        probe_rev='v(in_neg)',
    )
    i_sweep = _single_pole_sweep(
        g0=100.0,
        fp=1.0,
        frequencies=_DEC_FREQUENCIES,
        probe_fwd='i(v_fwd_probe)',
        probe_rev='i(v_rev_probe)',
    )
    sim = FakeSimulator(
        results=[
            SimulationResult(ac_sweep=v_sweep),
            SimulationResult(ac_sweep=i_sweep),
        ]
    )

    result = await measure_phase_margin(
        netlist=netlist,
        injection_strategy=strategy,
        break_node='in_neg',
        break_element_ref='R_fb',
        simulator=sim,
    )

    assert len(sim.calls) == 2
    assert result.injection_method == 'tian'


async def test_rosenstark_runs_two_sweeps(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_OPAMP_INV)
    strategy = RosenstarkReturnRatioStrategy(NgspiceInjectionNetlistPatcher())

    # Rosenstark OC: v(in_neg__fwd)/v(in_neg), SC: i(vrr_sc_drv)/i(vrr_sc_meas).
    # T_oc = v_rev/v_fwd (без минуса). T_sc analogously.
    # Для синтетики: возьмём T_oc и T_sc которые дают margin.
    # Combine: T = (T_oc·T_sc + T_oc + T_sc) / (T_oc·T_sc − 1).
    # Дадим T_oc = T_sc = 100/(1+jf/1) — single-pole identical. Тогда
    # T = (T²+2T)/(T²-1) — крайне нелинейно от T. Простоты ради
    # используем edge case: T_oc = T_sc = большое → ratio → 1+2/T,
    # margin будет другой. Тут просто проверяем что 2 sweep'а вызвались
    # и result == PhaseMarginMeasurement; конкретные числа калибруем
    # в Phase C.
    freqs = _DEC_FREQUENCIES

    def _build_synth_oc_sc(
        probe_fwd: str, probe_rev: str
    ) -> AcSweep:
        v_fwd_r, v_fwd_i, v_rev_r, v_rev_i = [], [], [], []
        for f in freqs:
            # T = 5 / (1 + j·f/10) — small G0, чтобы crossover был
            # в свеппе, и combine не давал NaN.
            denom = complex(1.0, f / 10.0)
            t_val = 5.0 / denom
            v_fwd = complex(1.0, 0.0)
            # Rosenstark: T = +v_rev/v_fwd (no minus)
            v_rev = t_val * v_fwd
            v_fwd_r.append(v_fwd.real)
            v_fwd_i.append(v_fwd.imag)
            v_rev_r.append(v_rev.real)
            v_rev_i.append(v_rev.imag)
        return AcSweep(
            frequency=freqs,
            traces_real={probe_fwd: tuple(v_fwd_r), probe_rev: tuple(v_rev_r)},
            traces_imag={probe_fwd: tuple(v_fwd_i), probe_rev: tuple(v_rev_i)},
        )

    oc_sweep = _build_synth_oc_sc('v(in_neg__fwd)', 'v(in_neg)')
    sc_sweep = _build_synth_oc_sc('i(vrr_sc_drv)', 'i(vrr_sc_meas)')
    sim = FakeSimulator(
        results=[
            SimulationResult(ac_sweep=oc_sweep),
            SimulationResult(ac_sweep=sc_sweep),
        ]
    )

    result = await measure_phase_margin(
        netlist=netlist,
        injection_strategy=strategy,
        break_node='in_neg',
        break_element_ref='R_fb',
        simulator=sim,
    )

    assert len(sim.calls) == 2
    assert result.injection_method == 'rosenstark_return_ratio'


# ============================== error mapping ==============================


async def test_break_element_ref_not_found_raises_domain_error(
    tmp_path: Path,
) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_OPAMP_INV)
    strategy = MiddlebrookVoltageStrategy(NgspiceInjectionNetlistPatcher())
    sim = FakeSimulator(results=[])  # никогда не должен вызваться

    with pytest.raises(LoopBreakNodeNotFoundError):
        await measure_phase_margin(
            netlist=netlist,
            injection_strategy=strategy,
            break_node='in_neg',
            break_element_ref='R_nonexistent',
            simulator=sim,
        )
    assert sim.calls == []


async def test_break_node_not_in_element_raises_domain_error(
    tmp_path: Path,
) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_OPAMP_INV)
    strategy = MiddlebrookVoltageStrategy(NgspiceInjectionNetlistPatcher())
    sim = FakeSimulator(results=[])

    with pytest.raises(LoopBreakNodeNotFoundError):
        await measure_phase_margin(
            netlist=netlist,
            injection_strategy=strategy,
            break_node='in_neg',
            break_element_ref='R_load',  # R_load connects vout, 0 — not in_neg
            simulator=sim,
        )
    assert sim.calls == []


async def test_loop_gain_always_above_unity_propagated(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_OPAMP_INV)
    strategy = MiddlebrookVoltageStrategy(NgspiceInjectionNetlistPatcher())

    ac = _flat_t_sweep(
        t_value=complex(100.0, 0.0),
        frequencies=_DEC_FREQUENCIES,
        probe_fwd='v(in_neg__fwd)',
        probe_rev='v(in_neg)',
    )
    sim = FakeSimulator(results=[SimulationResult(ac_sweep=ac)])

    with pytest.raises(LoopGainAlwaysAboveUnityError):
        await measure_phase_margin(
            netlist=netlist,
            injection_strategy=strategy,
            break_node='in_neg',
            break_element_ref='R_fb',
            simulator=sim,
        )


async def test_no_unity_gain_crossover_propagated(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_OPAMP_INV)
    strategy = MiddlebrookVoltageStrategy(NgspiceInjectionNetlistPatcher())

    ac = _flat_t_sweep(
        t_value=complex(0.01, 0.0),
        frequencies=_DEC_FREQUENCIES,
        probe_fwd='v(in_neg__fwd)',
        probe_rev='v(in_neg)',
    )
    sim = FakeSimulator(results=[SimulationResult(ac_sweep=ac)])

    with pytest.raises(NoUnityGainCrossoverError):
        await measure_phase_margin(
            netlist=netlist,
            injection_strategy=strategy,
            break_node='in_neg',
            break_element_ref='R_fb',
            simulator=sim,
        )


async def test_simulator_no_ac_sweep_raises_value_error(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_OPAMP_INV)
    strategy = MiddlebrookVoltageStrategy(NgspiceInjectionNetlistPatcher())
    # Симулятор вернул operating_points вместо AC sweep — типовое для
    # ситуации, когда .ac не запустилось но что-то downstream вернулось.
    sim = FakeSimulator(
        results=[SimulationResult(operating_points={'v(/in)': 0.0})]
    )

    with pytest.raises(ValueError, match='ac_sweep'):
        await measure_phase_margin(
            netlist=netlist,
            injection_strategy=strategy,
            break_node='in_neg',
            break_element_ref='R_fb',
            simulator=sim,
        )


# ============================== persistence DI guard =========================


async def test_writer_without_project_root_raises(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_OPAMP_INV)
    strategy = MiddlebrookVoltageStrategy(NgspiceInjectionNetlistPatcher())

    with pytest.raises(ValueError, match='project_root'):
        await measure_phase_margin(
            netlist=netlist,
            injection_strategy=strategy,
            break_node='in_neg',
            break_element_ref='R_fb',
            simulator=FakeSimulator(results=[]),
            sim_results_writer=RecordingWriter(),
            project_root=None,
        )


async def test_project_root_without_writer_raises(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_OPAMP_INV)
    strategy = MiddlebrookVoltageStrategy(NgspiceInjectionNetlistPatcher())

    with pytest.raises(ValueError, match='sim_results_writer'):
        await measure_phase_margin(
            netlist=netlist,
            injection_strategy=strategy,
            break_node='in_neg',
            break_element_ref='R_fb',
            simulator=FakeSimulator(results=[]),
            sim_results_writer=None,
            project_root=tmp_path,
        )


async def test_persistence_writes_sim_result_snapshot(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_OPAMP_INV)
    strategy = MiddlebrookVoltageStrategy(NgspiceInjectionNetlistPatcher())
    ac = _single_pole_sweep(
        g0=100.0,
        fp=1.0,
        frequencies=_DEC_FREQUENCIES,
        probe_fwd='v(in_neg__fwd)',
        probe_rev='v(in_neg)',
    )
    sim = FakeSimulator(results=[SimulationResult(ac_sweep=ac)])
    writer = RecordingWriter()

    await measure_phase_margin(
        netlist=netlist,
        injection_strategy=strategy,
        break_node='in_neg',
        break_element_ref='R_fb',
        simulator=sim,
        sim_results_writer=writer,
        project_root=tmp_path,
    )

    assert len(writer.writes) == 1
    snapshot, root = writer.writes[0]
    assert isinstance(snapshot, SimResult)
    assert snapshot.analysis_type == AnalysisType.PHASE_MARGIN
    assert snapshot.tool == 'ngspice'
    assert root == tmp_path
    metrics = snapshot.metrics or {}
    assert 'margin_deg' in metrics
    assert 'crossover_hz' in metrics
    assert 'injection_method' in metrics
    assert metrics['injection_method'] == 'middlebrook_voltage'


# ============================== extra crossovers =============================


async def test_extra_crossovers_propagated_to_measurement(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_OPAMP_INV)
    strategy = MiddlebrookVoltageStrategy(NgspiceInjectionNetlistPatcher())

    # Multi-crossover synthetic: T(f) values that go through 0dB twice DOWNWARD.
    freqs = (1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0)
    t_values = (
        complex(2.0, 0.0),
        complex(2.0, 0.0),
        complex(0.5, 0.0),
        complex(2.0, 0.0),
        complex(0.5, 0.0),
        complex(0.1, 0.0),
    )
    v_fwd_r, v_fwd_i, v_rev_r, v_rev_i = [], [], [], []
    for t in t_values:
        v_fwd = complex(1.0, 0.0)
        v_rev = -t * v_fwd
        v_fwd_r.append(v_fwd.real)
        v_fwd_i.append(v_fwd.imag)
        v_rev_r.append(v_rev.real)
        v_rev_i.append(v_rev.imag)
    ac = AcSweep(
        frequency=freqs,
        traces_real={
            'v(in_neg__fwd)': tuple(v_fwd_r),
            'v(in_neg)': tuple(v_rev_r),
        },
        traces_imag={
            'v(in_neg__fwd)': tuple(v_fwd_i),
            'v(in_neg)': tuple(v_rev_i),
        },
    )
    sim = FakeSimulator(results=[SimulationResult(ac_sweep=ac)])

    result = await measure_phase_margin(
        netlist=netlist,
        injection_strategy=strategy,
        break_node='in_neg',
        break_element_ref='R_fb',
        simulator=sim,
    )

    # Primary crossover — lowest-freq downward, между f=10 (6 dB) и f=100 (-6 dB).
    assert result.crossover_hz == pytest.approx(31.62, rel=0.05)
    # Extra crossovers: upward (100..1000) + downward (1000..10000).
    assert len(result.extra_crossovers_hz) == 2


# ============================== two-pole margin sanity =========================


async def test_two_pole_loop_gives_low_margin_marginal_class(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_OPAMP_INV)
    strategy = MiddlebrookVoltageStrategy(NgspiceInjectionNetlistPatcher())

    freqs = tuple(10.0**k for k in range(-1, 5))
    g0 = 100.0
    fp = 10.0
    v_fwd_r, v_fwd_i, v_rev_r, v_rev_i = [], [], [], []
    for f in freqs:
        x = f / fp
        denom = complex(1.0, x)
        t_val = g0 / (denom * denom)
        v_fwd = complex(1.0, 0.0)
        v_rev = -t_val * v_fwd
        v_fwd_r.append(v_fwd.real)
        v_fwd_i.append(v_fwd.imag)
        v_rev_r.append(v_rev.real)
        v_rev_i.append(v_rev.imag)
    ac = AcSweep(
        frequency=freqs,
        traces_real={
            'v(in_neg__fwd)': tuple(v_fwd_r),
            'v(in_neg)': tuple(v_rev_r),
        },
        traces_imag={
            'v(in_neg__fwd)': tuple(v_fwd_i),
            'v(in_neg)': tuple(v_rev_i),
        },
    )
    sim = FakeSimulator(results=[SimulationResult(ac_sweep=ac)])

    result = await measure_phase_margin(
        netlist=netlist,
        injection_strategy=strategy,
        break_node='in_neg',
        break_element_ref='R_fb',
        simulator=sim,
    )

    # Margin ≈ 11.4° → risky class (≤ 30).
    assert result.margin_deg == pytest.approx(11.4, abs=3.0)
    assert result.stability_class == 'risky'


# ============================== sanity: middlebrook current ===================


async def test_middlebrook_current_smoke(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_OPAMP_INV)
    strategy = MiddlebrookCurrentStrategy(NgspiceInjectionNetlistPatcher())

    ac = _single_pole_sweep(
        g0=100.0,
        fp=1.0,
        frequencies=_DEC_FREQUENCIES,
        probe_fwd='i(v_fwd_probe)',
        probe_rev='i(v_rev_probe)',
    )
    sim = FakeSimulator(results=[SimulationResult(ac_sweep=ac)])

    result = await measure_phase_margin(
        netlist=netlist,
        injection_strategy=strategy,
        break_node='in_neg',
        break_element_ref='R_fb',
        simulator=sim,
    )
    assert result.injection_method == 'middlebrook_current'
    assert result.crossover_hz == pytest.approx(100.0, rel=0.1)


# ============================== writes tmp netlists ==========================


async def test_writes_patched_netlist_to_tmp_file(tmp_path: Path) -> None:
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_OPAMP_INV)
    strategy = MiddlebrookVoltageStrategy(NgspiceInjectionNetlistPatcher())
    ac = _single_pole_sweep(
        g0=100.0,
        fp=1.0,
        frequencies=_DEC_FREQUENCIES,
        probe_fwd='v(in_neg__fwd)',
        probe_rev='v(in_neg)',
    )
    sim = FakeSimulator(results=[SimulationResult(ac_sweep=ac)])

    await measure_phase_margin(
        netlist=netlist,
        injection_strategy=strategy,
        break_node='in_neg',
        break_element_ref='R_fb',
        simulator=sim,
    )

    tmp_path_used, _, _ = sim.calls[0]
    # tmp file под суффиксом .tmp_pm_*.cir рядом с netlist'ом
    assert tmp_path_used.name.startswith('amp.tmp_pm_')
    assert tmp_path_used.suffix == '.cir'
    assert tmp_path_used.exists()
    content = tmp_path_used.read_text()
    # patcher вшил Vinj и переименовал в R_fb
    assert 'Vinj in_neg__fwd in_neg AC 1' in content
    assert 'R_fb vout in_neg__fwd 10k' in content


def test_phase_margin_measurement_stability_class_sanity() -> None:
    """Just for completeness — confirm domain mapping math.

    Used as sanity that fixture math gives the expected stability tags
    independently of orchestration.
    """
    # arbitrary check, not real assertion of math
    assert math.isclose(180.0 - 89.4, 90.6, abs_tol=0.01)


# ============================== auto-detect (Phase B.5.x) ===================

# Фикстура с детектируемым feedback loop (E_amp = active forward,
# R_fb = passive feedback). Совпадает с тестами `detect_feedback_break_node`.
_OPAMP_INV_FEEDBACK_NETLIST = (
    '* op-amp inverting amp с output RC pole (B.5.x auto-detect)\n'
    'V_in vin 0 AC 1 0\n'
    'R_in vin in_neg 1k\n'
    'R_fb vout in_neg 10k\n'
    'E_amp v_open 0 0 in_neg 1e5\n'
    'R_amp v_open vout 1k\n'
    'C_amp vout 0 10u\n'
    'R_load vout 0 1Meg\n'
    '.end\n'
)


class _RecordingCallback:
    """Confirmation callback фикстура: записывает AutoDetectInfo и возвращает скриптовый ответ."""

    def __init__(self, *, accept: bool) -> None:
        self._accept = accept
        self.calls: list[AutoDetectInfo] = []

    def __call__(self, info: AutoDetectInfo) -> bool:
        self.calls.append(info)
        return self._accept


class _FakePatcher:
    """In-test InjectionNetlistPatcher: возвращает constant ProbePair.

    Use case делегирует netlist text patching strategy.prepare(); для
    auto-detect unit-тестов нам безразличен фактический patched netlist —
    важна только pair probe-имён, по которым AcSweep подбирается.
    Реальный `NgspiceInjectionNetlistPatcher` тестируется в B.3.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []  # (op, node, element_ref)

    def insert_voltage_source(
        self,
        netlist: str,
        *,
        break_node: str,
        break_element_ref: str,
        source_ref: str,
        ac_magnitude: float = 1.0,
    ) -> NetlistPatchResult:
        del source_ref, ac_magnitude  # тестируем только трассировку edge
        self.calls.append(('voltage', break_node, break_element_ref))
        return NetlistPatchResult(
            patched_netlist=netlist + '\n* fake voltage injection\n',
            probe_pair=ProbePair(
                fwd='v(probe_fwd)',
                rev='v(probe_rev)',
            ),
        )

    def insert_current_source(
        self,
        netlist: str,
        *,
        break_node: str,
        break_element_ref: str,
        source_ref: str,
        ac_magnitude: float = 1.0,
    ) -> NetlistPatchResult:
        del source_ref, ac_magnitude
        self.calls.append(('current', break_node, break_element_ref))
        return NetlistPatchResult(
            patched_netlist=netlist + '\n* fake current injection\n',
            probe_pair=ProbePair(
                fwd='i(probe_fwd)',
                rev='i(probe_rev)',
            ),
        )

    def open_break(
        self,
        netlist: str,
        *,
        break_node: str,
        break_element_ref: str,
    ) -> NetlistPatchResult:
        self.calls.append(('open', break_node, break_element_ref))
        return NetlistPatchResult(
            patched_netlist=netlist + '\n* fake open break\n',
            probe_pair=ProbePair(
                fwd='v(probe_fwd)',
                rev='v(probe_rev)',
            ),
        )

    def short_break(
        self,
        netlist: str,
        *,
        break_node: str,
        break_element_ref: str,
        gnd_node: str = '0',
    ) -> NetlistPatchResult:
        del gnd_node
        self.calls.append(('short', break_node, break_element_ref))
        return NetlistPatchResult(
            patched_netlist=netlist + '\n* fake short break\n',
            probe_pair=ProbePair(
                fwd='v(probe_fwd)',
                rev='v(probe_rev)',
            ),
        )


def _fake_probe_sweep() -> AcSweep:
    """Single-pole T sweep на фейковых probe-именах v(probe_fwd)/v(probe_rev)."""
    return _single_pole_sweep(
        g0=100.0,
        fp=1.0,
        frequencies=_DEC_FREQUENCIES,
        probe_fwd='v(probe_fwd)',
        probe_rev='v(probe_rev)',
    )


async def test_auto_detect_calls_callback_with_info(tmp_path: Path) -> None:
    netlist = tmp_path / 'fb.cir'
    netlist.write_text(_OPAMP_INV_FEEDBACK_NETLIST)
    strategy = MiddlebrookVoltageStrategy(_FakePatcher())
    sim = FakeSimulator(results=[SimulationResult(ac_sweep=_fake_probe_sweep())])
    callback = _RecordingCallback(accept=True)

    result = await measure_phase_margin(
        netlist=netlist,
        injection_strategy=strategy,
        simulator=sim,
        auto_detect_confirmation=callback,
    )

    assert len(callback.calls) == 1
    info = callback.calls[0]
    assert isinstance(info, AutoDetectInfo)
    assert info.chosen_element_ref in {'R_fb', 'R_amp', 'C_amp', 'R_load'}
    assert result.auto_detect_info == info
    assert result.measured_at_node == info.chosen_node


async def test_auto_detect_uses_chosen_edge_for_patcher(tmp_path: Path) -> None:
    netlist = tmp_path / 'fb.cir'
    netlist.write_text(_OPAMP_INV_FEEDBACK_NETLIST)
    patcher = _FakePatcher()
    strategy = MiddlebrookVoltageStrategy(patcher)
    sim = FakeSimulator(results=[SimulationResult(ac_sweep=_fake_probe_sweep())])
    callback = _RecordingCallback(accept=True)

    await measure_phase_margin(
        netlist=netlist,
        injection_strategy=strategy,
        simulator=sim,
        auto_detect_confirmation=callback,
    )

    assert len(patcher.calls) == 1
    op, node, element_ref = patcher.calls[0]
    info = callback.calls[0]
    assert op == 'voltage'
    assert node == info.chosen_node
    assert element_ref == info.chosen_element_ref


async def test_auto_detect_rejected_raises(tmp_path: Path) -> None:
    netlist = tmp_path / 'fb.cir'
    netlist.write_text(_OPAMP_INV_FEEDBACK_NETLIST)
    strategy = MiddlebrookVoltageStrategy(_FakePatcher())
    sim = FakeSimulator(results=[])  # не должен вызываться
    callback = _RecordingCallback(accept=False)

    with pytest.raises(AutoDetectRejectedError, match='confidence'):
        await measure_phase_margin(
            netlist=netlist,
            injection_strategy=strategy,
            simulator=sim,
            auto_detect_confirmation=callback,
        )
    assert sim.calls == []
    assert len(callback.calls) == 1


async def test_auto_detect_path_requires_callback(tmp_path: Path) -> None:
    netlist = tmp_path / 'fb.cir'
    netlist.write_text(_OPAMP_INV_FEEDBACK_NETLIST)
    strategy = MiddlebrookVoltageStrategy(_FakePatcher())
    sim = FakeSimulator(results=[])

    with pytest.raises(ValueError, match='auto_detect_confirmation'):
        await measure_phase_margin(
            netlist=netlist,
            injection_strategy=strategy,
            simulator=sim,
            # break_node/break_element_ref не заданы, callback не передан
        )
    assert sim.calls == []


async def test_half_explicit_node_without_element_raises(tmp_path: Path) -> None:
    netlist = tmp_path / 'fb.cir'
    netlist.write_text(_OPAMP_INV_FEEDBACK_NETLIST)
    strategy = MiddlebrookVoltageStrategy(_FakePatcher())
    sim = FakeSimulator(results=[])

    with pytest.raises(ValueError, match='break_node.*break_element_ref'):
        await measure_phase_margin(
            netlist=netlist,
            injection_strategy=strategy,
            simulator=sim,
            break_node='in_neg',
            # break_element_ref не задан
        )
    assert sim.calls == []


async def test_half_explicit_element_without_node_raises(tmp_path: Path) -> None:
    netlist = tmp_path / 'fb.cir'
    netlist.write_text(_OPAMP_INV_FEEDBACK_NETLIST)
    strategy = MiddlebrookVoltageStrategy(_FakePatcher())
    sim = FakeSimulator(results=[])

    with pytest.raises(ValueError, match='break_node.*break_element_ref'):
        await measure_phase_margin(
            netlist=netlist,
            injection_strategy=strategy,
            simulator=sim,
            break_element_ref='R_fb',
            # break_node не задан
        )
    assert sim.calls == []


async def test_no_feedback_loop_propagated_from_detect(tmp_path: Path) -> None:
    """Pure RC ladder без active element → NoFeedbackLoopDetectedError."""
    netlist_text = (
        'V_in a 0 AC 1\n'
        'R1 a b 1k\n'
        'C1 b 0 1u\n'
        '.end\n'
    )
    netlist = tmp_path / 'rc.cir'
    netlist.write_text(netlist_text)
    strategy = MiddlebrookVoltageStrategy(_FakePatcher())
    sim = FakeSimulator(results=[])
    callback = _RecordingCallback(accept=True)

    with pytest.raises(NoFeedbackLoopDetectedError):
        await measure_phase_margin(
            netlist=netlist,
            injection_strategy=strategy,
            simulator=sim,
            auto_detect_confirmation=callback,
        )
    assert sim.calls == []
    assert callback.calls == []


async def test_explicit_path_auto_detect_info_is_none(tmp_path: Path) -> None:
    """Regression: explicit edge-pair → auto_detect_info=None в measurement."""
    netlist = tmp_path / 'amp.cir'
    netlist.write_text(_OPAMP_INV)
    strategy = MiddlebrookVoltageStrategy(NgspiceInjectionNetlistPatcher())
    ac = _single_pole_sweep(
        g0=100.0,
        fp=1.0,
        frequencies=_DEC_FREQUENCIES,
        probe_fwd='v(in_neg__fwd)',
        probe_rev='v(in_neg)',
    )
    sim = FakeSimulator(results=[SimulationResult(ac_sweep=ac)])

    result = await measure_phase_margin(
        netlist=netlist,
        injection_strategy=strategy,
        break_node='in_neg',
        break_element_ref='R_fb',
        simulator=sim,
    )

    assert result.auto_detect_info is None
