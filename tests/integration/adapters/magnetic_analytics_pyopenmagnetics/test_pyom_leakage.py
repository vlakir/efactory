"""
Integration: PyOpenMagneticsAnalytics.calculate_leakage_inductance (T132).

Тесты через реальный PyOM .so binding. Smoke pilot — minimal 200/20 turns
OPT (probe-proven fit для E 42/15 + Round 0.224 wire); полный
Hammond 1627A-class fixture с 3500 turns ставит вопрос wire fit
(см. T132 Analyze §A3, BACKLOG follow-up).

Monotonicity test (Lσ(2-section) > Lσ(3) > Lσ(5)) — в acceptance Phase C;
здесь только smoke + fail-loud для отсутствия layout.
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

# Probe-proven turn counts which physically fit в E 42/15 window
# с Round 0.224 / Round 0.5 wire combo. Acceptance Phase C может использовать
# другую fixture, более близкую к Hammond 1627A.
SMOKE_PRIMARY_TURNS = 200
SMOKE_SECONDARY_TURNS = 20
# Physical-plausible Lσ range для small-scale smoke fixture
# (200 turns primary → existing probe видел ~167 µH). Не attempt to
# match real-world OPT; bound широк для smoke gate.
LEAKAGE_PLAUSIBLE_LOWER_H = 1e-9
LEAKAGE_PLAUSIBLE_UPPER_H = 100e-3


def _probe_leakage_backend(pyom_mod) -> str | None:  # noqa: ANN001
    """
    Smoke-probe PyOM leakage backend: minimal P-S wind + leakage call.

    Возвращает причину skip'а либо None если backend полностью рабочий.
    На bare host (без полного PyOM-bundled FEM/mesh стека) leakage call
    возвращает `{'data': 'Exception: [CALCULATION_ERROR] Mesh
    generation failed: induced field data is empty'}` — Analyze §W1.
    """
    import math

    bobbin = next(
        b for b in pyom_mod.get_bobbins() if b.get('name') == 'Bobbin E42/15'
    )
    minimal_coil = {
        'functionalDescription': [
            {
                'name': 'primary',
                'numberTurns': 200,
                'numberParallels': 1,
                'isolationSide': 'primary',
                'wire': 'Round 0.224 - Grade 1',
            },
            {
                'name': 'secondary',
                'numberTurns': 20,
                'numberParallels': 1,
                'isolationSide': 'secondary',
                'wire': 'Round 0.5 - Grade 1',
            },
        ],
        'bobbin': bobbin,
    }
    try:
        wound = pyom_mod.wind(minimal_coil, 2, [1.0, 1.0], [0, 1], [[0.001, 0.001]])
    except Exception as exc:  # noqa: BLE001
        return f'pyom.wind raised: {exc}'
    if not isinstance(wound, dict):
        return f'pyom.wind returned non-dict: {str(wound)[:120]}'
    bb = wound.get('bobbin', bobbin)
    if isinstance(bb, dict):
        pd = bb.setdefault('processedDescription', {})
        if pd.get('columnWidth') is None:
            ww_list = bb.get('functionalDescription', {}).get('windingWindows', [{}])
            pd['columnWidth'] = ww_list[0].get('width', 0.0074)
        if not pd.get('columnDepth') or pd.get('columnDepth', 0) < 1e-6:
            pd['columnDepth'] = 0.015
    core_full = pyom_mod.calculate_core_data(
        {
            'functionalDescription': {
                'type': 'two-piece set',
                'material': 'Nanoperm 8000',
                'shape': 'E 42/21/15',
                'gapping': [{'type': 'subtractive', 'length': 0.0001}],
                'numberStacks': 1,
            },
        },
        True,  # noqa: FBT003
    )
    times = [i / 32000.0 for i in range(32)]
    excitations = [
        {
            'frequency': 1000.0,
            'voltage': {
                'waveform': {
                    'data': [
                        250.0 * math.sin(2 * math.pi * 1000 * t) for t in times
                    ],
                    'time': times,
                },
            },
            'current': {'waveform': {'data': [0.0] * 32, 'time': times}},
        }
        for _ in range(2)
    ]
    magnetic = {
        'core': core_full,
        'coil': wound,
        'operatingPoint': {
            'name': 'p',
            'conditions': {'ambientTemperature': 25.0},
            'excitationsPerWinding': excitations,
        },
    }
    try:
        result = pyom_mod.calculate_leakage_inductance(magnetic, 1000.0, 0)
    except Exception as exc:  # noqa: BLE001
        return f'pyom.calculate_leakage_inductance raised: {exc}'
    if isinstance(result, dict) and isinstance(result.get('data'), str):
        return f'pyom leakage backend unavailable: {result["data"][:160]}'
    if (
        not isinstance(result, dict)
        or not result.get('leakageInductancePerWinding')
    ):
        return f'pyom leakage returned empty payload: {str(result)[:120]}'
    return None


@pytest.fixture(scope='module')
def pyom():  # noqa: ANN201
    pyom_mod = load_pyopenmagnetics()
    reason = _probe_leakage_backend(pyom_mod)
    if reason is not None:
        pytest.skip(
            f'PyOM leakage backend not available on this host: {reason}. '
            f'Запустите в efactory:linux container '
            f'(`./efactory-up --headless -- uv run pytest tests/integration/'
            f'adapters/magnetic_analytics_pyopenmagnetics/test_pyom_leakage.py`).',
            allow_module_level=True,
        )
    return pyom_mod


def _smoke_opt_fixture(layout: InterleavingPattern | None) -> MagneticComponent:
    """Smoke OPT fixture (200/20 turns; fits в E 42/15 window per probe)."""
    return MagneticComponent(
        name='Smoke OPT (probe-proven turns)',
        core=Core(
            shape_name='E 42/21/15',
            material_name='Nanoperm 8000',
            bobbin_name='Bobbin E42/15',
            gap_length_m=0.0001,
            gap_type=GapType.SUBTRACTIVE,
        ),
        windings=(
            Winding(
                name='primary',
                number_turns=SMOKE_PRIMARY_TURNS,
                isolation_side=IsolationSide.PRIMARY,
                wire_name='Round 0.224 - Grade 1',
            ),
            Winding(
                name='secondary',
                number_turns=SMOKE_SECONDARY_TURNS,
                isolation_side=IsolationSide.SECONDARY,
                wire_name='Round 0.5 - Grade 1',
            ),
        ),
        operating_point=OperatingPoint(
            name='1 kHz mid-band',
            frequency_hz=1000.0,
            primary_peak_voltage_v=250.0,
            primary_dc_bias_a=0.05,
            primary_ac_peak_a=0.01,
        ),
        section_layout=layout,
    )


def _p_s_layout() -> InterleavingPattern:
    return InterleavingPattern(
        sections=(
            WindingSection(winding_name='primary'),
            WindingSection(winding_name='secondary'),
        ),
    )


@pytest.mark.asyncio
async def test_calculate_leakage_pilot_2_section_returns_plausible_result(
    pyom,  # noqa: ANN001
) -> None:
    """Smoke: P-S 2-section даёт Lσ > 0 в physical range, k близок к 1."""
    adapter = PyOpenMagneticsAnalytics(pyom)
    component = _smoke_opt_fixture(_p_s_layout())

    result = await adapter.calculate_leakage_inductance(component)

    assert isinstance(result, LeakageInductanceResult)
    assert result.source_winding == 'primary'
    assert set(result.leakage_to.keys()) == {'secondary'}
    leakage_h = result.leakage_to['secondary']
    assert LEAKAGE_PLAUSIBLE_LOWER_H < leakage_h < LEAKAGE_PLAUSIBLE_UPPER_H, (
        f'Lσ={leakage_h:.3e} H выходит из physical-plausible range '
        f'[{LEAKAGE_PLAUSIBLE_LOWER_H:.0e}, {LEAKAGE_PLAUSIBLE_UPPER_H:.0e}] H'
    )
    # k close to 1 для well-coupled OPT (Lσ << L_self)
    assert 0.9 <= result.coupling_factor <= 1.0


@pytest.mark.asyncio
async def test_calculate_leakage_fails_loud_without_section_layout(
    pyom,  # noqa: ANN001
) -> None:
    """`section_layout=None` → LeakageInductanceAnalyzerFailedError."""
    adapter = PyOpenMagneticsAnalytics(pyom)
    component = _smoke_opt_fixture(layout=None)

    with pytest.raises(
        LeakageInductanceAnalyzerFailedError,
        match='section_layout',
    ):
        await adapter.calculate_leakage_inductance(component)


@pytest.mark.asyncio
async def test_calculate_leakage_fails_loud_on_unknown_source_winding(
    pyom,  # noqa: ANN001
) -> None:
    """Указание несуществующей source winding → понятная ошибка."""
    adapter = PyOpenMagneticsAnalytics(pyom)
    component = _smoke_opt_fixture(_p_s_layout())

    with pytest.raises(
        LeakageInductanceAnalyzerFailedError,
        match='source_winding',
    ):
        await adapter.calculate_leakage_inductance(component, source_winding='ghost')


@pytest.mark.asyncio
async def test_calculate_leakage_default_source_is_primary(pyom) -> None:  # noqa: ANN001
    """`source_winding=None` → используется `primary_winding.name`."""
    adapter = PyOpenMagneticsAnalytics(pyom)
    component = _smoke_opt_fixture(_p_s_layout())

    result_default = await adapter.calculate_leakage_inductance(component)
    result_explicit = await adapter.calculate_leakage_inductance(
        component,
        source_winding='primary',
    )

    assert result_default.source_winding == result_explicit.source_winding
    assert result_default.leakage_to == pytest.approx(result_explicit.leakage_to)
