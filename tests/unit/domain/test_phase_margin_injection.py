"""Domain: InjectionStrategy ABC + 4 impl (T153 Phase B.2)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import pytest
from pydantic import ValidationError

from domain.phase_margin_injection import (
    InjectionSetup,
    InjectionStrategy,
    LoopGain,
    MiddlebrookCurrentStrategy,
    MiddlebrookVoltageStrategy,
    RosenstarkReturnRatioStrategy,
    TianStrategy,
)
from domain.simulation import AcSweep
from ports.outbound.injection_netlist_patcher import (
    NetlistPatchResult,
    ProbePair,
)


# ---------------------------------------------------------- Fake patcher ----


@dataclass
class _FakePatcherCall:
    op: str
    netlist: str
    break_node: str
    extra: dict[str, object]


@dataclass
class FakePatcher:
    """Конфигурируемый fake `InjectionNetlistPatcher` для unit-тестов."""

    voltage_result: NetlistPatchResult = field(
        default_factory=lambda: NetlistPatchResult(
            patched_netlist='* voltage-patched',
            probe_pair=ProbePair(fwd='v(/fb_left)', rev='v(/fb_right)'),
        )
    )
    current_result: NetlistPatchResult = field(
        default_factory=lambda: NetlistPatchResult(
            patched_netlist='* current-patched',
            probe_pair=ProbePair(fwd='i(R_fwd)', rev='i(R_rev)'),
        )
    )
    open_result: NetlistPatchResult = field(
        default_factory=lambda: NetlistPatchResult(
            patched_netlist='* open-patched',
            probe_pair=ProbePair(fwd='v(/in)', rev='v(/fb_oc)'),
        )
    )
    short_result: NetlistPatchResult = field(
        default_factory=lambda: NetlistPatchResult(
            patched_netlist='* short-patched',
            probe_pair=ProbePair(fwd='v(/in)', rev='v(/fb_sc)'),
        )
    )
    calls: list[_FakePatcherCall] = field(default_factory=list)

    def insert_voltage_source(
        self,
        netlist: str,
        *,
        break_node: str,
        source_ref: str,
        ac_magnitude: float = 1.0,
    ) -> NetlistPatchResult:
        self.calls.append(
            _FakePatcherCall(
                op='insert_voltage_source',
                netlist=netlist,
                break_node=break_node,
                extra={'source_ref': source_ref, 'ac_magnitude': ac_magnitude},
            )
        )
        return self.voltage_result

    def insert_current_source(
        self,
        netlist: str,
        *,
        break_node: str,
        source_ref: str,
        ac_magnitude: float = 1.0,
    ) -> NetlistPatchResult:
        self.calls.append(
            _FakePatcherCall(
                op='insert_current_source',
                netlist=netlist,
                break_node=break_node,
                extra={'source_ref': source_ref, 'ac_magnitude': ac_magnitude},
            )
        )
        return self.current_result

    def open_break(
        self, netlist: str, *, break_node: str
    ) -> NetlistPatchResult:
        self.calls.append(
            _FakePatcherCall(
                op='open_break',
                netlist=netlist,
                break_node=break_node,
                extra={},
            )
        )
        return self.open_result

    def short_break(
        self,
        netlist: str,
        *,
        break_node: str,
        gnd_node: str = '0',
    ) -> NetlistPatchResult:
        self.calls.append(
            _FakePatcherCall(
                op='short_break',
                netlist=netlist,
                break_node=break_node,
                extra={'gnd_node': gnd_node},
            )
        )
        return self.short_result


# ---------------------------------------------------------- sweep helpers ----


def _ac(
    frequency: tuple[float, ...],
    traces: dict[str, tuple[complex, ...]],
) -> AcSweep:
    return AcSweep(
        frequency=frequency,
        traces_real={k: tuple(c.real for c in v) for k, v in traces.items()},
        traces_imag={k: tuple(c.imag for c in v) for k, v in traces.items()},
    )


# ============================================================= ProbePair ====


def test_probe_pair_happy() -> None:
    p = ProbePair(fwd='v(/a)', rev='v(/b)')
    assert p.fwd == 'v(/a)'
    assert p.rev == 'v(/b)'


def test_probe_pair_empty_fwd_rejected() -> None:
    with pytest.raises(ValidationError, match='fwd'):
        ProbePair(fwd='', rev='v(/b)')


def test_probe_pair_empty_rev_rejected() -> None:
    with pytest.raises(ValidationError, match='rev'):
        ProbePair(fwd='v(/a)', rev='')


def test_probe_pair_is_frozen() -> None:
    p = ProbePair(fwd='v(/a)', rev='v(/b)')
    with pytest.raises(ValidationError):
        p.fwd = 'v(/c)'  # type: ignore[misc]


# ================================================== NetlistPatchResult ====


def test_netlist_patch_result_happy() -> None:
    r = NetlistPatchResult(
        patched_netlist='* test',
        probe_pair=ProbePair(fwd='v(/a)', rev='v(/b)'),
    )
    assert r.patched_netlist == '* test'
    assert r.probe_pair.fwd == 'v(/a)'


def test_netlist_patch_result_empty_netlist_rejected() -> None:
    with pytest.raises(ValidationError, match='patched_netlist'):
        NetlistPatchResult(
            patched_netlist='',
            probe_pair=ProbePair(fwd='v(/a)', rev='v(/b)'),
        )


# ===================================================== InjectionSetup ====


def test_injection_setup_happy_single() -> None:
    result = NetlistPatchResult(
        patched_netlist='* p',
        probe_pair=ProbePair(fwd='v(/a)', rev='v(/b)'),
    )
    setup = InjectionSetup(patches=(result,))
    assert len(setup.patches) == 1


def test_injection_setup_happy_two() -> None:
    r1 = NetlistPatchResult(
        patched_netlist='* p1',
        probe_pair=ProbePair(fwd='v(/a)', rev='v(/b)'),
    )
    r2 = NetlistPatchResult(
        patched_netlist='* p2',
        probe_pair=ProbePair(fwd='v(/c)', rev='v(/d)'),
    )
    setup = InjectionSetup(patches=(r1, r2))
    assert len(setup.patches) == 2


def test_injection_setup_empty_patches_rejected() -> None:
    with pytest.raises(ValidationError, match='patches'):
        InjectionSetup(patches=())


def test_injection_setup_is_frozen() -> None:
    r = NetlistPatchResult(
        patched_netlist='* p',
        probe_pair=ProbePair(fwd='v(/a)', rev='v(/b)'),
    )
    setup = InjectionSetup(patches=(r,))
    with pytest.raises(ValidationError):
        setup.patches = ()  # type: ignore[misc]


# ============================================================ LoopGain ====


def test_loop_gain_happy() -> None:
    lg = LoopGain(
        frequency=(1.0, 10.0, 100.0),
        real=(1.0, 0.5, 0.0),
        imag=(0.0, -0.5, -1.0),
    )
    assert lg.frequency == (1.0, 10.0, 100.0)


def test_loop_gain_length_mismatch_rejected() -> None:
    with pytest.raises(ValidationError, match='length'):
        LoopGain(
            frequency=(1.0, 10.0),
            real=(1.0, 0.5, 0.0),
            imag=(0.0, -0.5, -1.0),
        )


def test_loop_gain_empty_rejected() -> None:
    with pytest.raises(ValidationError):
        LoopGain(frequency=(), real=(), imag=())


def test_loop_gain_non_monotonic_frequency_rejected() -> None:
    with pytest.raises(ValidationError, match='frequency'):
        LoopGain(
            frequency=(10.0, 5.0, 100.0),
            real=(1.0, 1.0, 1.0),
            imag=(0.0, 0.0, 0.0),
        )


def test_loop_gain_non_positive_frequency_rejected() -> None:
    with pytest.raises(ValidationError, match='frequency'):
        LoopGain(
            frequency=(0.0, 1.0),
            real=(1.0, 1.0),
            imag=(0.0, 0.0),
        )


def test_loop_gain_nan_real_rejected() -> None:
    with pytest.raises(ValidationError, match='real'):
        LoopGain(
            frequency=(1.0, 10.0),
            real=(1.0, math.nan),
            imag=(0.0, 0.0),
        )


def test_loop_gain_inf_real_rejected() -> None:
    with pytest.raises(ValidationError, match='real'):
        LoopGain(
            frequency=(1.0, 10.0),
            real=(1.0, math.inf),
            imag=(0.0, 0.0),
        )


def test_loop_gain_neg_inf_imag_rejected() -> None:
    with pytest.raises(ValidationError, match='imag'):
        LoopGain(
            frequency=(1.0, 10.0),
            real=(1.0, 1.0),
            imag=(0.0, -math.inf),
        )


def test_loop_gain_nan_imag_rejected() -> None:
    with pytest.raises(ValidationError, match='imag'):
        LoopGain(
            frequency=(1.0, 10.0),
            real=(1.0, 1.0),
            imag=(0.0, math.nan),
        )


def test_loop_gain_is_frozen() -> None:
    lg = LoopGain(
        frequency=(1.0,),
        real=(1.0,),
        imag=(0.0,),
    )
    with pytest.raises(ValidationError):
        lg.frequency = (2.0,)  # type: ignore[misc]


# =========================================== InjectionStrategy ABC ====


def test_injection_strategy_is_abstract() -> None:
    with pytest.raises(TypeError, match='abstract'):
        InjectionStrategy()  # type: ignore[abstract]


# ============================== MiddlebrookVoltageStrategy ====


def test_middlebrook_voltage_method_name() -> None:
    assert MiddlebrookVoltageStrategy.method_name == 'middlebrook_voltage'


def test_middlebrook_voltage_prepare_delegates_to_patcher() -> None:
    patcher = FakePatcher()
    strategy = MiddlebrookVoltageStrategy(patcher)
    setup = strategy.prepare('* netlist', break_node='/fb')
    assert len(patcher.calls) == 1
    call = patcher.calls[0]
    assert call.op == 'insert_voltage_source'
    assert call.netlist == '* netlist'
    assert call.break_node == '/fb'
    assert call.extra == {'source_ref': 'Vinj', 'ac_magnitude': 1.0}
    assert setup.patches == (patcher.voltage_result,)


def test_middlebrook_voltage_combine_math_single_freq() -> None:
    patcher = FakePatcher()
    strategy = MiddlebrookVoltageStrategy(patcher)
    setup = strategy.prepare('* netlist', break_node='/fb')
    # T = -V(rev)/V(fwd) = -((-0.5+0j))/(1+0j) = 0.5+0j
    sweep = _ac(
        frequency=(1_000.0,),
        traces={
            'v(/fb_left)': (1.0 + 0.0j,),
            'v(/fb_right)': (-0.5 + 0.0j,),
        },
    )
    lg = strategy.combine((sweep,), setup)
    assert lg.frequency == (1_000.0,)
    assert lg.real[0] == pytest.approx(0.5)
    assert lg.imag[0] == pytest.approx(0.0)


def test_middlebrook_voltage_combine_math_complex_division() -> None:
    patcher = FakePatcher()
    strategy = MiddlebrookVoltageStrategy(patcher)
    setup = strategy.prepare('* netlist', break_node='/fb')
    # T = -(0+1j)/(1+1j) = -(0+1j)*(1-1j)/2 = -(1+1j)/2 = -0.5 - 0.5j
    sweep = _ac(
        frequency=(1_000.0,),
        traces={
            'v(/fb_left)': (1.0 + 1.0j,),
            'v(/fb_right)': (0.0 + 1.0j,),
        },
    )
    lg = strategy.combine((sweep,), setup)
    assert lg.real[0] == pytest.approx(-0.5)
    assert lg.imag[0] == pytest.approx(-0.5)


def test_middlebrook_voltage_combine_multi_freq() -> None:
    patcher = FakePatcher()
    strategy = MiddlebrookVoltageStrategy(patcher)
    setup = strategy.prepare('* netlist', break_node='/fb')
    sweep = _ac(
        frequency=(10.0, 100.0, 1_000.0),
        traces={
            'v(/fb_left)': (1.0 + 0.0j, 1.0 + 0.0j, 1.0 + 0.0j),
            'v(/fb_right)': (-1.0 + 0j, -0.5 + 0j, -0.1 + 0j),
        },
    )
    lg = strategy.combine((sweep,), setup)
    assert lg.real == pytest.approx((1.0, 0.5, 0.1))


def test_middlebrook_voltage_combine_wrong_sweep_count_rejected() -> None:
    patcher = FakePatcher()
    strategy = MiddlebrookVoltageStrategy(patcher)
    setup = strategy.prepare('* netlist', break_node='/fb')
    sweep = _ac(
        frequency=(1_000.0,),
        traces={'v(/fb_left)': (1.0 + 0j,), 'v(/fb_right)': (0.0 + 0j,)},
    )
    with pytest.raises(ValueError, match='expected 1 sweep'):
        strategy.combine((sweep, sweep), setup)


def test_middlebrook_voltage_combine_missing_probe_trace() -> None:
    patcher = FakePatcher()
    strategy = MiddlebrookVoltageStrategy(patcher)
    setup = strategy.prepare('* netlist', break_node='/fb')
    sweep = _ac(
        frequency=(1_000.0,),
        traces={'v(/other)': (1.0 + 0j,)},
    )
    with pytest.raises(ValueError, match='[Tt]race'):
        strategy.combine((sweep,), setup)


# ============================== MiddlebrookCurrentStrategy ====


def test_middlebrook_current_method_name() -> None:
    assert MiddlebrookCurrentStrategy.method_name == 'middlebrook_current'


def test_middlebrook_current_prepare_delegates_to_patcher() -> None:
    patcher = FakePatcher()
    strategy = MiddlebrookCurrentStrategy(patcher)
    setup = strategy.prepare('* netlist', break_node='/fb')
    assert len(patcher.calls) == 1
    call = patcher.calls[0]
    assert call.op == 'insert_current_source'
    assert call.extra == {'source_ref': 'Iinj', 'ac_magnitude': 1.0}
    assert setup.patches == (patcher.current_result,)


def test_middlebrook_current_combine_math() -> None:
    patcher = FakePatcher()
    strategy = MiddlebrookCurrentStrategy(patcher)
    setup = strategy.prepare('* netlist', break_node='/fb')
    sweep = _ac(
        frequency=(1_000.0,),
        traces={
            'i(R_fwd)': (1.0 + 0.0j,),
            'i(R_rev)': (-0.25 + 0.0j,),
        },
    )
    lg = strategy.combine((sweep,), setup)
    assert lg.real[0] == pytest.approx(0.25)
    assert lg.imag[0] == pytest.approx(0.0)


# ======================================================== TianStrategy ====


def test_tian_method_name() -> None:
    assert TianStrategy.method_name == 'tian'


def test_tian_prepare_calls_both_v_and_i_patches() -> None:
    patcher = FakePatcher()
    strategy = TianStrategy(patcher)
    setup = strategy.prepare('* netlist', break_node='/fb')
    assert [c.op for c in patcher.calls] == [
        'insert_voltage_source',
        'insert_current_source',
    ]
    assert setup.patches == (patcher.voltage_result, patcher.current_result)


def test_tian_combine_math_real_values() -> None:
    """T_v = 2, T_i = 3 → T = (6-1)/(2+3+2) = 5/7."""
    patcher = FakePatcher()
    strategy = TianStrategy(patcher)
    setup = strategy.prepare('* netlist', break_node='/fb')
    # T_v = -rev/fwd = -(-2)/1 = 2
    v_sweep = _ac(
        frequency=(1_000.0,),
        traces={
            'v(/fb_left)': (1.0 + 0j,),
            'v(/fb_right)': (-2.0 + 0j,),
        },
    )
    # T_i = -rev/fwd = -(-3)/1 = 3
    i_sweep = _ac(
        frequency=(1_000.0,),
        traces={
            'i(R_fwd)': (1.0 + 0j,),
            'i(R_rev)': (-3.0 + 0j,),
        },
    )
    lg = strategy.combine((v_sweep, i_sweep), setup)
    # T = (2·3 - 1) / (2+3+2) = 5/7
    assert lg.real[0] == pytest.approx(5.0 / 7.0)
    assert lg.imag[0] == pytest.approx(0.0)


def test_tian_combine_math_complex_values() -> None:
    """T_v = 2j, T_i = -1j → T = (2j·-1j - 1)/(2j - 1j + 2) = 1/(2+j) = (2-j)/5."""
    patcher = FakePatcher()
    strategy = TianStrategy(patcher)
    setup = strategy.prepare('* netlist', break_node='/fb')
    # T_v = -rev/fwd = -(0-2j)/1 = 2j
    v_sweep = _ac(
        frequency=(1_000.0,),
        traces={
            'v(/fb_left)': (1.0 + 0j,),
            'v(/fb_right)': (-2j,),
        },
    )
    # T_i = -rev/fwd = -(0+1j)/1 = -1j
    i_sweep = _ac(
        frequency=(1_000.0,),
        traces={
            'i(R_fwd)': (1.0 + 0j,),
            'i(R_rev)': (1j,),
        },
    )
    lg = strategy.combine((v_sweep, i_sweep), setup)
    # expected: (2 - j)/5 = 0.4 - 0.2j
    assert lg.real[0] == pytest.approx(0.4)
    assert lg.imag[0] == pytest.approx(-0.2)


def test_tian_combine_wrong_sweep_count_rejected() -> None:
    patcher = FakePatcher()
    strategy = TianStrategy(patcher)
    setup = strategy.prepare('* netlist', break_node='/fb')
    v_sweep = _ac(
        frequency=(1_000.0,),
        traces={
            'v(/fb_left)': (1.0 + 0j,),
            'v(/fb_right)': (-2.0 + 0j,),
        },
    )
    with pytest.raises(ValueError, match='expected 2 sweep'):
        strategy.combine((v_sweep,), setup)


def test_tian_combine_frequency_mismatch_rejected() -> None:
    patcher = FakePatcher()
    strategy = TianStrategy(patcher)
    setup = strategy.prepare('* netlist', break_node='/fb')
    v_sweep = _ac(
        frequency=(1_000.0,),
        traces={
            'v(/fb_left)': (1.0 + 0j,),
            'v(/fb_right)': (-2.0 + 0j,),
        },
    )
    i_sweep = _ac(
        frequency=(2_000.0,),
        traces={
            'i(R_fwd)': (1.0 + 0j,),
            'i(R_rev)': (-3.0 + 0j,),
        },
    )
    with pytest.raises(ValueError, match='frequency'):
        strategy.combine((v_sweep, i_sweep), setup)


# ============================== RosenstarkReturnRatioStrategy ====


def test_rosenstark_method_name() -> None:
    assert (
        RosenstarkReturnRatioStrategy.method_name == 'rosenstark_return_ratio'
    )


def test_rosenstark_prepare_calls_open_and_short() -> None:
    patcher = FakePatcher()
    strategy = RosenstarkReturnRatioStrategy(patcher)
    setup = strategy.prepare('* netlist', break_node='/fb')
    assert [c.op for c in patcher.calls] == ['open_break', 'short_break']
    assert setup.patches == (patcher.open_result, patcher.short_result)


def test_rosenstark_combine_math_real_values() -> None:
    """T_oc = 2, T_sc = 3 → T = (6+2+3)/(6-1) = 11/5."""
    patcher = FakePatcher()
    strategy = RosenstarkReturnRatioStrategy(patcher)
    setup = strategy.prepare('* netlist', break_node='/fb')
    # T_oc = rev/fwd = 2/1 = 2 (no minus sign — no inserted source)
    oc_sweep = _ac(
        frequency=(1_000.0,),
        traces={
            'v(/in)': (1.0 + 0j,),
            'v(/fb_oc)': (2.0 + 0j,),
        },
    )
    # T_sc = rev/fwd = 3/1 = 3
    sc_sweep = _ac(
        frequency=(1_000.0,),
        traces={
            'v(/in)': (1.0 + 0j,),
            'v(/fb_sc)': (3.0 + 0j,),
        },
    )
    lg = strategy.combine((oc_sweep, sc_sweep), setup)
    # expected 11/5 = 2.2
    assert lg.real[0] == pytest.approx(11.0 / 5.0)
    assert lg.imag[0] == pytest.approx(0.0)


def test_rosenstark_combine_wrong_sweep_count_rejected() -> None:
    patcher = FakePatcher()
    strategy = RosenstarkReturnRatioStrategy(patcher)
    setup = strategy.prepare('* netlist', break_node='/fb')
    oc_sweep = _ac(
        frequency=(1_000.0,),
        traces={'v(/in)': (1.0 + 0j,), 'v(/fb_oc)': (2.0 + 0j,)},
    )
    with pytest.raises(ValueError, match='expected 2 sweep'):
        strategy.combine((oc_sweep,), setup)


def test_rosenstark_combine_frequency_mismatch_rejected() -> None:
    patcher = FakePatcher()
    strategy = RosenstarkReturnRatioStrategy(patcher)
    setup = strategy.prepare('* netlist', break_node='/fb')
    oc_sweep = _ac(
        frequency=(1_000.0,),
        traces={'v(/in)': (1.0 + 0j,), 'v(/fb_oc)': (2.0 + 0j,)},
    )
    sc_sweep = _ac(
        frequency=(2_000.0,),
        traces={'v(/in)': (1.0 + 0j,), 'v(/fb_sc)': (3.0 + 0j,)},
    )
    with pytest.raises(ValueError, match='frequency'):
        strategy.combine((oc_sweep, sc_sweep), setup)
