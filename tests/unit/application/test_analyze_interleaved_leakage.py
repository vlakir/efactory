"""Unit: analyze_interleaved_leakage use case (T132 Phase C)."""

from __future__ import annotations

import pytest

from application.analyze_interleaved_leakage import analyze_interleaved_leakage
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


class StubLeakageAnalyzer:
    """Stub `LeakageInductanceAnalyzer`: returns canned result."""

    def __init__(self, result: LeakageInductanceResult) -> None:
        self._result = result
        self.invocations: list[tuple[str, str | None]] = []

    async def calculate_leakage_inductance(
        self,
        component: MagneticComponent,
        source_winding: str | None = None,
    ) -> LeakageInductanceResult:
        self.invocations.append((component.name, source_winding))
        return self._result


def _component_with_layout() -> MagneticComponent:
    return MagneticComponent(
        name='OPT pilot',
        core=Core(
            shape_name='E 42/21/15', material_name='3C95',
            bobbin_name='Bobbin E42/15', gap_length_m=0.0001,
        ),
        windings=(
            Winding(
                name='primary', number_turns=2500,
                isolation_side=IsolationSide.PRIMARY,
            ),
            Winding(
                name='secondary', number_turns=100,
                isolation_side=IsolationSide.SECONDARY,
            ),
        ),
        operating_point=OperatingPoint(
            frequency_hz=1000.0, primary_peak_voltage_v=250.0,
        ),
        section_layout=InterleavingPattern(
            sections=(
                WindingSection(winding_name='primary'),
                WindingSection(winding_name='secondary'),
                WindingSection(winding_name='primary'),
            ),
        ),
    )


@pytest.mark.asyncio
async def test_use_case_returns_analyzer_result() -> None:
    canned = LeakageInductanceResult(
        source_winding='primary',
        leakage_to={'secondary': 1.5e-4},
        coupling_factor=0.99,
    )
    analyzer = StubLeakageAnalyzer(canned)
    component = _component_with_layout()

    result = await analyze_interleaved_leakage(
        component=component, analyzer=analyzer,
    )
    assert result is canned
    assert analyzer.invocations == [('OPT pilot', None)]


@pytest.mark.asyncio
async def test_use_case_forwards_explicit_source_winding() -> None:
    canned = LeakageInductanceResult(
        source_winding='secondary',
        leakage_to={'primary': 1.5e-2},
        coupling_factor=0.95,
    )
    analyzer = StubLeakageAnalyzer(canned)
    component = _component_with_layout()

    result = await analyze_interleaved_leakage(
        component=component, analyzer=analyzer, source_winding='secondary',
    )
    assert result.source_winding == 'secondary'
    assert analyzer.invocations == [('OPT pilot', 'secondary')]


@pytest.mark.asyncio
async def test_use_case_rejects_component_without_layout() -> None:
    canned = LeakageInductanceResult(
        source_winding='primary',
        leakage_to={'secondary': 1e-4}, coupling_factor=0.99,
    )
    analyzer = StubLeakageAnalyzer(canned)
    component = _component_with_layout().model_copy(update={'section_layout': None})

    with pytest.raises(ValueError, match='section_layout'):
        await analyze_interleaved_leakage(
            component=component, analyzer=analyzer,
        )
    # analyzer не вызывался
    assert analyzer.invocations == []
