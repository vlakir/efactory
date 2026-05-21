"""
Unit: AnalyticalLeakage adapter (T132 Phase C).

Tests с FakePyOM stub + FakeMagneticAnalytics (для L_self injection).
"""

from __future__ import annotations

from typing import Any

import pytest

from adapters.outbound.leakage_inductance_analytical.adapter import (
    AnalyticalLeakage,
)
from domain.magnetic import (
    Core,
    InterleavingPattern,
    IsolationSide,
    LeakageInductanceResult,
    MagneticComponent,
    OperatingPoint,
    Winding,
    WindingSection,
)
from ports.outbound.leakage_inductance_analyzer import (
    LeakageInductanceAnalyzerFailedError,
)


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class FakePyOM:
    def __init__(self, core_full: dict[str, Any], wires: dict[str, dict[str, Any]]) -> None:
        self._core_full = core_full
        self._wires = wires

    def calculate_core_data(self, _c: Any, _p: bool) -> dict[str, Any]:  # noqa: FBT001
        return self._core_full

    def find_wire_by_name(self, name: str) -> dict[str, Any]:
        return self._wires[name]


class FakeInductance:
    """Stub `MagneticAnalytics`: возвращает заданное self-inductance."""

    def __init__(self, l_self_h: float) -> None:
        self._l = l_self_h
        self.calls: int = 0

    async def calculate_inductance(self, _component: MagneticComponent) -> float:
        self.calls += 1
        return self._l


def _e42_15_core_full() -> dict[str, Any]:
    return {
        'functionalDescription': {
            'shape': {
                'name': 'E 42/21/15',
                'dimensions': {
                    'F': {'minimum': 0.0117, 'maximum': 0.0122, 'nominal': None},
                },
            },
        },
        'processedDescription': {
            'depth': 0.01495,
            'width': 0.04215,
            'height': 0.042,
            'windingWindows': [{'height': 0.0273, 'width': 0.0074}],
        },
    }


def _wires() -> dict[str, dict[str, Any]]:
    return {
        'Round 0.224 - Grade 1': {
            'outerDiameter': {'nominal': 0.000252},
        },
        'Round 0.5 - Grade 1': {
            'outerDiameter': {'nominal': 0.000548},
        },
    }


def _component(layout: InterleavingPattern | None) -> MagneticComponent:
    return MagneticComponent(
        name='OPT pilot',
        core=Core(
            shape_name='E 42/21/15',
            material_name='3C95',
            bobbin_name='Bobbin E42/15',
            gap_length_m=0.0001,
        ),
        windings=(
            Winding(
                name='primary', number_turns=200,
                isolation_side=IsolationSide.PRIMARY,
                wire_name='Round 0.224 - Grade 1',
            ),
            Winding(
                name='secondary', number_turns=20,
                isolation_side=IsolationSide.SECONDARY,
                wire_name='Round 0.5 - Grade 1',
            ),
        ),
        operating_point=OperatingPoint(
            frequency_hz=1000.0, primary_peak_voltage_v=250.0,
        ),
        section_layout=layout,
    )


def _layout(*names: str) -> InterleavingPattern:
    return InterleavingPattern(
        sections=tuple(WindingSection(winding_name=n) for n in names),
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adapter_p_s_pilot_returns_physical_lσ() -> None:
    """P-S pilot: Lσ_primary returned, ratio Lσ/L_self consistent с k."""
    adapter = AnalyticalLeakage(
        FakePyOM(_e42_15_core_full(), _wires()),
        FakeInductance(l_self_h=5.0),  # 5 H primary self-inductance
    )
    layout = _layout('primary', 'secondary')
    result = await adapter.calculate_leakage_inductance(_component(layout))

    assert isinstance(result, LeakageInductanceResult)
    assert result.source_winding == 'primary'
    assert set(result.leakage_to.keys()) == {'secondary'}
    lσ = result.leakage_to['secondary']
    # Sanity: 200 turns @ E 42/15 P-S → 1-100 µH range
    assert 1e-7 < lσ < 1e-3
    # k near 1 (Lσ << L_self)
    assert 0.999 < result.coupling_factor <= 1.0


@pytest.mark.asyncio
async def test_adapter_monotonicity_across_three_patterns() -> None:
    """Spec Q7 gate: Lσ decreases с увеличением sections."""
    pyom = FakePyOM(_e42_15_core_full(), _wires())
    indu = FakeInductance(l_self_h=5.0)
    adapter = AnalyticalLeakage(pyom, indu)

    l_2 = await adapter.calculate_leakage_inductance(
        _component(_layout('primary', 'secondary')),
    )
    l_3 = await adapter.calculate_leakage_inductance(
        _component(_layout('primary', 'secondary', 'primary')),
    )
    l_5 = await adapter.calculate_leakage_inductance(
        _component(_layout('primary', 'secondary',
                          'primary', 'secondary', 'primary')),
    )

    σ_2 = l_2.leakage_to['secondary']
    σ_3 = l_3.leakage_to['secondary']
    σ_5 = l_5.leakage_to['secondary']
    assert σ_2 > σ_3 > σ_5


# ---------------------------------------------------------------------------
# Fail-loud
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adapter_no_layout_raises() -> None:
    adapter = AnalyticalLeakage(
        FakePyOM(_e42_15_core_full(), _wires()),
        FakeInductance(l_self_h=5.0),
    )
    with pytest.raises(
        LeakageInductanceAnalyzerFailedError,
        match='section_layout',
    ):
        await adapter.calculate_leakage_inductance(_component(layout=None))


@pytest.mark.asyncio
async def test_adapter_unknown_source_winding_raises() -> None:
    adapter = AnalyticalLeakage(
        FakePyOM(_e42_15_core_full(), _wires()),
        FakeInductance(l_self_h=5.0),
    )
    layout = _layout('primary', 'secondary')
    with pytest.raises(
        LeakageInductanceAnalyzerFailedError,
        match='source_winding',
    ):
        await adapter.calculate_leakage_inductance(
            _component(layout),
            source_winding='ghost',
        )


@pytest.mark.asyncio
async def test_adapter_default_source_is_primary() -> None:
    adapter = AnalyticalLeakage(
        FakePyOM(_e42_15_core_full(), _wires()),
        FakeInductance(l_self_h=5.0),
    )
    layout = _layout('primary', 'secondary')

    r_default = await adapter.calculate_leakage_inductance(_component(layout))
    r_explicit = await adapter.calculate_leakage_inductance(
        _component(layout), source_winding='primary',
    )
    assert r_default.source_winding == r_explicit.source_winding == 'primary'
    assert r_default.leakage_to == pytest.approx(r_explicit.leakage_to)


@pytest.mark.asyncio
async def test_adapter_winding_without_wire_name_raises() -> None:
    adapter = AnalyticalLeakage(
        FakePyOM(_e42_15_core_full(), _wires()),
        FakeInductance(l_self_h=5.0),
    )
    # Build a component where primary has wire_name=None
    bad_component = MagneticComponent(
        name='no-wire',
        core=Core(
            shape_name='E 42/21/15', material_name='3C95',
            bobbin_name='Bobbin E42/15', gap_length_m=0.0001,
        ),
        windings=(
            Winding(name='primary', number_turns=200,
                   isolation_side=IsolationSide.PRIMARY,
                   wire_name=None),
            Winding(name='secondary', number_turns=20,
                   isolation_side=IsolationSide.SECONDARY,
                   wire_name='Round 0.5 - Grade 1'),
        ),
        operating_point=OperatingPoint(
            frequency_hz=1000.0, primary_peak_voltage_v=250.0,
        ),
        section_layout=_layout('primary', 'secondary'),
    )
    with pytest.raises(
        LeakageInductanceAnalyzerFailedError,
        match='wire_name',
    ):
        await adapter.calculate_leakage_inductance(bad_component)


@pytest.mark.asyncio
async def test_adapter_coupling_factor_clamps_to_unit_interval() -> None:
    """Если Lσ > L_self (патологический fixture), k clamps на 0."""
    adapter = AnalyticalLeakage(
        FakePyOM(_e42_15_core_full(), _wires()),
        FakeInductance(l_self_h=1e-9),  # absurdly small L_self
    )
    layout = _layout('primary', 'secondary')
    result = await adapter.calculate_leakage_inductance(_component(layout))
    assert result.coupling_factor == 0.0


@pytest.mark.asyncio
async def test_adapter_invokes_inductance_port_for_coupling_factor() -> None:
    """k = √(1 - Lσ/L_self) requires self-inductance call."""
    indu = FakeInductance(l_self_h=5.0)
    adapter = AnalyticalLeakage(
        FakePyOM(_e42_15_core_full(), _wires()),
        indu,
    )
    layout = _layout('primary', 'secondary')
    await adapter.calculate_leakage_inductance(_component(layout))
    assert indu.calls == 1
