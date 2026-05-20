"""
Integration: PyOpenMagneticsAnalytics через реальный PyOM wheel (T113 Phase 2B).

Адаптер должен воспроизвести pilot baseline на OPT 6П14П SE fixture:
ZHANG model = 6.9564 H (см. `tests/fixtures/magnetic/opt-6p14p-se/
expected.json`, генерируется `scripts/pilot/build_fixture.py`).
"""

from __future__ import annotations

import pytest

from adapters.outbound.magnetic_analytics_pyopenmagnetics import (
    PyOpenMagneticsAnalytics,
    load_pyopenmagnetics,
)
from domain.magnetic import (
    Core,
    GapType,
    IsolationSide,
    MagneticComponent,
    OperatingPoint,
    Winding,
)
from ports.outbound.magnetic_analytics import (
    MagneticAnalyticsFailedError,
)

# Pilot baseline: tests/fixtures/magnetic/opt-6p14p-se/expected.json
PILOT_LP_ZHANG_H = 6.956400080747171
PILOT_LP_REL_TOLERANCE = 1e-3  # adapter mas-construction должна matchить pilot


@pytest.fixture(scope='module')
def pyom():  # noqa: ANN201  - PyOM module is Any-typed
    return load_pyopenmagnetics()


def _opt_6p14p_se() -> MagneticComponent:
    """Pilot OPT 6П14П SE fixture — той же spec что в pilot build_fixture."""
    return MagneticComponent(
        name='OPT 6П14П SE',
        core=Core(
            shape_name='E 42/21/15',
            material_name='Nanoperm 8000',
            bobbin_name='Bobbin E42/15',
            gap_length_m=0.0001,  # 0.1 mm
            gap_type=GapType.SUBTRACTIVE,
        ),
        windings=(
            Winding(
                name='primary',
                number_turns=2500,
                isolation_side=IsolationSide.PRIMARY,
                wire_name='Round 0.212 - Grade 1',
            ),
            Winding(
                name='secondary',
                number_turns=100,
                isolation_side=IsolationSide.SECONDARY,
                wire_name='Round 0.90 - Grade 1',
            ),
        ),
        operating_point=OperatingPoint(
            name='1 kHz mid-band',
            frequency_hz=1000.0,
            primary_peak_voltage_v=250.0,
            primary_dc_bias_a=0.05,
            primary_ac_peak_a=0.01,
        ),
    )


@pytest.mark.asyncio
async def test_pyom_analytics_matches_pilot_baseline(pyom) -> None:  # noqa: ANN001
    """ZHANG inductance совпадает с pilot expected.json (1e-3 tolerance)."""
    adapter = PyOpenMagneticsAnalytics(pyom)  # default reluctance=ZHANG
    component = _opt_6p14p_se()

    lp = await adapter.calculate_inductance(component)

    assert lp == pytest.approx(PILOT_LP_ZHANG_H, rel=PILOT_LP_REL_TOLERANCE)


@pytest.mark.asyncio
async def test_pyom_analytics_other_reluctance_models(pyom) -> None:  # noqa: ANN001
    """Альтернативные модели (MUEHLETHALER) дают разные но близкие Lp."""
    adapter_muehl = PyOpenMagneticsAnalytics(pyom, reluctance_model='MUEHLETHALER')
    component = _opt_6p14p_se()

    lp = await adapter_muehl.calculate_inductance(component)

    # MUEHLETHALER pilot baseline: 7.0197 H — в пределах ±10% от ZHANG
    assert lp == pytest.approx(7.019701903253783, rel=1e-3)


@pytest.mark.asyncio
async def test_pyom_analytics_unknown_bobbin_fails(pyom) -> None:  # noqa: ANN001
    """Несуществующий bobbin → MagneticAnalyticsFailedError с понятным msg."""
    adapter = PyOpenMagneticsAnalytics(pyom)
    bad_component = MagneticComponent(
        name='bad-bobbin-test',
        core=Core(
            shape_name='E 42/21/15',
            material_name='Nanoperm 8000',
            bobbin_name='NONEXISTENT BOBBIN',
            gap_length_m=0.0001,
        ),
        windings=(
            Winding(
                name='primary',
                number_turns=100,
                isolation_side=IsolationSide.PRIMARY,
            ),
        ),
        operating_point=OperatingPoint(
            frequency_hz=1000.0,
            primary_peak_voltage_v=10.0,
        ),
    )

    with pytest.raises(MagneticAnalyticsFailedError, match='bobbin'):
        await adapter.calculate_inductance(bad_component)


@pytest.mark.asyncio
async def test_pyom_analytics_missing_bobbin_fails(pyom) -> None:  # noqa: ANN001
    """Core.bobbin_name = None → MagneticAnalyticsFailedError при анализе."""
    adapter = PyOpenMagneticsAnalytics(pyom)
    no_bobbin = MagneticComponent(
        name='no-bobbin-test',
        core=Core(
            shape_name='E 42/21/15',
            material_name='Nanoperm 8000',
            gap_length_m=0.0001,
        ),
        windings=(
            Winding(
                name='primary',
                number_turns=100,
                isolation_side=IsolationSide.PRIMARY,
            ),
        ),
        operating_point=OperatingPoint(
            frequency_hz=1000.0,
            primary_peak_voltage_v=10.0,
        ),
    )

    with pytest.raises(MagneticAnalyticsFailedError, match='требует bobbin'):
        await adapter.calculate_inductance(no_bobbin)
