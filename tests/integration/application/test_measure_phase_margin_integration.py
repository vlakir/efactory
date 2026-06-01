"""
Integration: measure_phase_margin + real ngspice (T153 Phase B.4).

**Soft smoke level (Phase B.4 scope)**: проверяем что use case
orchestration корректно проходит через real ngspice — netlist
patcher выдаёт parsable .cir, ngspice .ac sweep выполняется,
strategy.combine возвращает LoopGain. **Не** asserting numeric margin
— физическая корректность формул Middlebrook V/I single-injection
(T_v ≠ T_loop в общем случае) калибруется в Phase C на reference
fixture'ах.

Acceptance: use case завершается БЕЗ ImportError / parse-fail /
TypeError / unexpected exception'ов. PhaseMarginMeasurement object
ИЛИ один из ожидаемых domain error'ов (NoUnityGainCrossover,
LoopGainAlwaysAboveUnity) — оба валидируют что pipeline дошёл до
crossover detection.

Op-amp inverting amp с single-pole rolloff (VCVS + RC-фильтр на
выходе): чистая fixture для проверки orchestration целостности
без зависимости от точной физической accuracy формул.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from adapters.outbound.ngspice.injection_patcher import (
    NgspiceInjectionNetlistPatcher,
)
from adapters.outbound.ngspice.simulator import NgspiceSimulator
from adapters.outbound.platform_native.platform_layer import (
    NativePlatformLayer,
)
from adapters.outbound.subprocess_apps.app_manager import SubprocessAppManager
from application.measure_phase_margin import measure_phase_margin
from domain.phase_margin import (
    AutoDetectInfo,
    LoopGainAlwaysAboveUnityError,
    NoUnityGainCrossoverError,
    PhaseMarginMeasurement,
)
from domain.phase_margin_injection import (
    MiddlebrookCurrentStrategy,
    MiddlebrookVoltageStrategy,
)

if TYPE_CHECKING:
    from pathlib import Path

_NGSPICE_AVAILABLE = shutil.which('ngspice') is not None
needs_ngspice = pytest.mark.skipif(
    not _NGSPICE_AVAILABLE,
    reason='ngspice not installed',
)

# Op-amp inverting amp с output RC rolloff:
# A(s) = 1e5 / (1 + s/(R·C)), R=1k, C=10µ → fp ≈ 15.9 Hz.
# β = 1/11. T(s) crossover ≈ 144.5 kHz, margin ≈ 90°.
_OPAMP_INV_WITH_POLE = (
    '* op-amp inverting amp with output RC rolloff (T153 B.4 integration)\n'
    '* V_in DC-only (AC=0); единственный AC source — это injected Vinj.\n'
    'V_in vin 0 DC 0\n'
    'R_in vin in_neg 1k\n'
    'R_fb vout in_neg 10k\n'
    'E_amp v_open 0 0 in_neg 1e5\n'
    'R_amp v_open vout 1k\n'
    'C_amp vout 0 10u\n'
    'R_load vout 0 1Meg\n'
    '.end\n'
)


def _make_simulator() -> NgspiceSimulator:
    return NgspiceSimulator(SubprocessAppManager(NativePlatformLayer()))


@needs_ngspice
async def test_middlebrook_voltage_orchestration_completes(
    tmp_path: Path,
) -> None:
    """Smoke: V-inject end-to-end через real ngspice.

    Acceptance — успешный pipeline (returns measurement) либо domain-
    correct error (NoUnityGainCrossover/LoopGainAlwaysAbove) из
    crossover detection. Оба — валидируют ngspice→adapter→strategy→
    crossover целостность. Physics correctness — Phase C.
    """
    netlist = tmp_path / 'opamp_pole.cir'
    netlist.write_text(_OPAMP_INV_WITH_POLE)
    strategy = MiddlebrookVoltageStrategy(NgspiceInjectionNetlistPatcher())

    try:
        result = await measure_phase_margin(
            netlist=netlist,
            injection_strategy=strategy,
            break_node='in_neg',
            break_element_ref='R_fb',
            simulator=_make_simulator(),
            f_low=1.0,
            f_high=1e7,
            n_points_per_decade=50,
        )
        assert isinstance(result, PhaseMarginMeasurement)
        assert result.injection_method == 'middlebrook_voltage'
        assert result.measured_at_node == 'in_neg'
    except (NoUnityGainCrossoverError, LoopGainAlwaysAboveUnityError):
        # OK для B.4: pipeline дошёл до crossover detection без parse-fail'ов.
        pass


@needs_ngspice
async def test_middlebrook_current_orchestration_completes(
    tmp_path: Path,
) -> None:
    """Smoke: I-inject end-to-end через real ngspice (см. V-test)."""
    netlist = tmp_path / 'opamp_pole.cir'
    netlist.write_text(_OPAMP_INV_WITH_POLE)
    strategy = MiddlebrookCurrentStrategy(NgspiceInjectionNetlistPatcher())

    try:
        result = await measure_phase_margin(
            netlist=netlist,
            injection_strategy=strategy,
            break_node='in_neg',
            break_element_ref='R_fb',
            simulator=_make_simulator(),
            f_low=1.0,
            f_high=1e7,
            n_points_per_decade=50,
        )
        assert isinstance(result, PhaseMarginMeasurement)
        assert result.injection_method == 'middlebrook_current'
    except (NoUnityGainCrossoverError, LoopGainAlwaysAboveUnityError):
        pass


@needs_ngspice
async def test_auto_detect_orchestration_completes(
    tmp_path: Path,
) -> None:
    """Smoke (Phase B.5.x): auto-detect ветка end-to-end через real ngspice.

    Acceptance — callback вызван с реальным `AutoDetectInfo`, pipeline
    выполнился до crossover detection (success ИЛИ domain error). Не
    проверяем точное содержимое measurement.auto_detect_info — это
    регрессирующая часть, юнит-тесты её покрывают.
    """
    netlist = tmp_path / 'opamp_pole.cir'
    netlist.write_text(_OPAMP_INV_WITH_POLE)
    strategy = MiddlebrookVoltageStrategy(NgspiceInjectionNetlistPatcher())
    captured: list[AutoDetectInfo] = []

    def accept_any(info: AutoDetectInfo) -> bool:
        captured.append(info)
        return True

    try:
        result = await measure_phase_margin(
            netlist=netlist,
            injection_strategy=strategy,
            auto_detect_confirmation=accept_any,
            simulator=_make_simulator(),
            f_low=1.0,
            f_high=1e7,
            n_points_per_decade=50,
        )
        assert isinstance(result, PhaseMarginMeasurement)
        assert result.auto_detect_info is not None
        assert result.measured_at_node == result.auto_detect_info.chosen_node
    except (NoUnityGainCrossoverError, LoopGainAlwaysAboveUnityError):
        pass

    # Callback должен был быть вызван даже если pipeline упал на crossover.
    assert len(captured) == 1
    assert captured[0].chosen_element_ref in {
        'R_fb',
        'R_amp',
        'C_amp',
        'R_load',
    }
