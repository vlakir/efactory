"""
measure_phase_margin — loop-gain → PhaseMarginMeasurement (T153 Phase B.4 + B.5.x).

Phase B.4 baseline: explicit edge-pair `(break_node, break_element_ref)`.
Phase B.5.x: оба аргумента стали optional — при их отсутствии use case
вызывает `detect_feedback_break_node` под капотом и делегирует решение
callback'у `auto_detect_confirmation` (W7 lean: callable-type alias,
не Protocol/ABC — threshold policy живёт в callback'е, который
собирается composition root'ом CLI).

Pipeline:

1. Validate args: либо оба explicit, либо ни одного (+ callback при
   auto-detect).
2. Read netlist text.
3. Auto-detect path (если break edge не задан): `detect_feedback_break_node`
   (threshold=0.0 — callback владеет policy) → `AutoDetectInfo` →
   callback(info) → True/False. False → `AutoDetectRejectedError`.
   `NoFeedbackLoopDetectedError` пробрасывается caller'у.
4. `setup = strategy.prepare(text, break_node, break_element_ref)` —
   1-2 patched netlist'а в `setup.patches`. `ValueError` от patcher'а
   (element_ref не найден / break_node не в pin'ах) → re-raise как
   `LoopBreakNodeNotFoundError`.
5. Для каждого `patch`: write tmp `.cir` рядом с исходным netlist'ом
   (суффикс `.tmp_pm_<idx>.cir`), run `Simulator.run(path,
   AcAnalysis(sweep='dec', n_points=…))`. Собрать `AcSweep`-объекты.
6. `loop_gain = strategy.combine(sweeps_tuple, setup)` — комплексная
   контурная передача `T(jω)`.
7. `crossover = find_unity_crossover(loop_gain)` — primary downward
   crossing + interpolated phase + extras. Raise'ит `NoUnityGainCrossoverError`
   / `LoopGainAlwaysAboveUnityError` напрямую — не оборачиваем.
8. `margin_deg = 180 + crossover.phase_at_crossover_deg`. Guard на
   `[-180, 360]` (см. validator `PhaseMarginMeasurement.margin_deg`).
9. `stability_class` derived через domain-helper consistent с margin.
10. Build `PhaseMarginMeasurement` (`measured_at_node = break_node`,
    `injection_method = strategy.method_name`, `auto_detect_info`
    из шага 3 если был auto-detect).
11. Optional persistence через `SimResultsRepository.write` —
    `analysis_type = AnalysisType.PHASE_MARGIN`.

Не делает: gain margin computation (флаг `with_gain_margin` reserved,
импла отложена на B.6), TTY confirmation prompt construction (это
ответственность CLI в B.6 — собирает callback из `typer.confirm` /
non-TTY policy и инжектит сюда).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from application.detect_feedback_break_node import detect_feedback_break_node
from domain.phase_margin import (
    AutoDetectRejectedError,
    LoopBreakNodeNotFoundError,
    PhaseMarginMeasurement,
    _expected_stability_class,
)
from domain.phase_margin_crossover import find_unity_crossover
from domain.sim_results import AnalysisType, SimResult
from domain.simulation import AcAnalysis

if TYPE_CHECKING:
    from pathlib import Path

    from domain.phase_margin import AutoDetectInfo, ConfirmationCallback
    from domain.phase_margin_injection import InjectionStrategy
    from domain.simulation import AcSweep
    from ports.outbound.sim_results import SimResultsRepository
    from ports.outbound.simulator import Simulator


_DEFAULT_F_LOW = 1.0
_DEFAULT_F_HIGH = 1e6
_DEFAULT_N_POINTS_PER_DECADE = 100
_DEFAULT_TIMEOUT_SECONDS = 60.0
_MIN_MARGIN_DEG = -180.0
_MAX_MARGIN_DEG = 360.0


async def measure_phase_margin(
    *,
    netlist: Path,
    injection_strategy: InjectionStrategy,
    break_node: str | None = None,
    break_element_ref: str | None = None,
    auto_detect_confirmation: ConfirmationCallback | None = None,
    simulator: Simulator,
    f_low: float = _DEFAULT_F_LOW,
    f_high: float = _DEFAULT_F_HIGH,
    n_points_per_decade: int = _DEFAULT_N_POINTS_PER_DECADE,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    sim_results_writer: SimResultsRepository | None = None,
    project_root: Path | None = None,
    tool: str = 'ngspice',
) -> PhaseMarginMeasurement:
    """
    Измерить phase margin для замкнутой петли (explicit edge-pair или auto-detect).

    Args:
        netlist: путь к SPICE-netlist'у замкнутой системы.
        injection_strategy: domain-strategy с инжектированным
            `InjectionNetlistPatcher` (composition root собирает).
        break_node: имя нета, в котором режется петля. Optional: если
            не задан, активируется auto-detect ветка. Должен идти в
            паре с `break_element_ref` (оба или ни одного).
        break_element_ref: ref элемента, чья ссылка на `break_node`
            будет переименована в `<break_node>__fwd`. Edge-pair
            (ADR-T153d).
        auto_detect_confirmation: callback `(AutoDetectInfo) -> bool`,
            обязателен в auto-detect ветке. Решает, принять ли
            предложенный analyzer'ом edge. CLI (B.6) собирает callback
            из `typer.confirm` / non-TTY threshold-policy.
        simulator: outbound port (ngspice).
        f_low: нижняя граница AC sweep'а (Hz, default 1).
        f_high: верхняя граница AC sweep'а (Hz, default 1e6).
        n_points_per_decade: разрешение sweep'а.
        timeout_seconds: лимит на каждый `simulator.run`.
        sim_results_writer: optional outbound port для persistence
            результата в `.efactory/sim-results/`.
        project_root: обязателен парно с `sim_results_writer`.
        tool: имя инструмента для SimResult snapshot.

    Returns:
        `PhaseMarginMeasurement` с margin_deg, crossover_hz,
        stability_class и метаданными. `auto_detect_info` set если
        была auto-detect ветка, иначе None.

    Raises:
        ValueError: half-explicit edge-pair (один из break_node /
            break_element_ref задан, другой None); auto-detect без
            callback; partial persistence DI (writer без root или
            наоборот); simulator вернул нет ac_sweep; computed margin
            outside [-180, 360].
        LoopBreakNodeNotFoundError: explicit edge не найден.
        NoFeedbackLoopDetectedError: auto-detect не нашёл feedback loop.
        AutoDetectRejectedError: callback отклонил предложенный edge.
        NoUnityGainCrossoverError: нет downward 0 dB crossing'а.
        LoopGainAlwaysAboveUnityError: |T| > 1 во всём свеппе.
        SimulatorUnavailableError / SimulationFailedError: forward'аются.

    """
    if (sim_results_writer is None) != (project_root is None):
        msg = (
            'measure_phase_margin: sim_results_writer и project_root '
            'должны быть переданы пара (оба или ни одного).'
        )
        raise ValueError(msg)

    base_text = await asyncio.to_thread(netlist.read_text)

    resolved_node, resolved_element_ref, auto_detect_info = _resolve_break_edge(
        netlist_text=base_text,
        break_node=break_node,
        break_element_ref=break_element_ref,
        auto_detect_confirmation=auto_detect_confirmation,
    )

    try:
        setup = injection_strategy.prepare(
            base_text,
            break_node=resolved_node,
            break_element_ref=resolved_element_ref,
        )
    except ValueError as exc:
        raise LoopBreakNodeNotFoundError(str(exc)) from exc

    analysis = AcAnalysis(
        sweep='dec',
        n_points=n_points_per_decade,
        f_start=f_low,
        f_stop=f_high,
    )
    sweeps: list[AcSweep] = []
    for idx, patch in enumerate(setup.patches):
        tmp_netlist = netlist.with_suffix(f'.tmp_pm_{idx}.cir')
        await asyncio.to_thread(tmp_netlist.write_text, patch.patched_netlist)
        sim_result = await simulator.run(
            tmp_netlist,
            analysis,
            timeout_seconds=timeout_seconds,
        )
        if sim_result.ac_sweep is None:
            msg = (
                f'measure_phase_margin: simulator returned no ac_sweep for patch {idx}'
            )
            raise ValueError(msg)
        sweeps.append(sim_result.ac_sweep)

    loop_gain = injection_strategy.combine(tuple(sweeps), setup)
    crossover = find_unity_crossover(loop_gain)

    margin_deg = 180.0 + crossover.phase_at_crossover_deg
    if not (_MIN_MARGIN_DEG <= margin_deg <= _MAX_MARGIN_DEG):
        msg = (
            f'measure_phase_margin: computed margin_deg {margin_deg!r} '
            f'outside valid range [{_MIN_MARGIN_DEG}, {_MAX_MARGIN_DEG}]; '
            f'phase unwrap or fixture issue'
        )
        raise ValueError(msg)
    stability_class = _expected_stability_class(margin_deg)

    measurement = PhaseMarginMeasurement(
        margin_deg=margin_deg,
        crossover_hz=crossover.crossover_hz,
        measured_at_node=resolved_node,
        injection_method=injection_strategy.method_name,
        stability_class=stability_class,
        extra_crossovers_hz=crossover.extra_crossovers_hz,
        auto_detect_info=auto_detect_info,
    )

    if sim_results_writer is not None and project_root is not None:
        snapshot = _build_snapshot(
            measurement=measurement,
            netlist=netlist,
            project_root=project_root,
            tool=tool,
        )
        await sim_results_writer.write(
            result=snapshot,
            project_root=project_root,
        )

    return measurement


def _resolve_break_edge(
    *,
    netlist_text: str,
    break_node: str | None,
    break_element_ref: str | None,
    auto_detect_confirmation: ConfirmationCallback | None,
) -> tuple[str, str, AutoDetectInfo | None]:
    """
    Validate edge-pair args + (если auto-detect) запустить detect + callback.

    Возвращает `(node, element_ref, auto_detect_info)`. Explicit path:
    `auto_detect_info=None`. Half-explicit и auto-detect-без-callback —
    `ValueError`. Callback вернул False — `AutoDetectRejectedError`.
    """
    if break_node is not None and break_element_ref is not None:
        return break_node, break_element_ref, None
    if break_node is None and break_element_ref is None:
        if auto_detect_confirmation is None:
            msg = (
                'measure_phase_margin: auto_detect_confirmation callback '
                'обязателен когда break_node / break_element_ref не заданы '
                '(auto-detect ветка не имеет дефолтной policy).'
            )
            raise ValueError(msg)
        # callback владеет threshold policy (W7, ADR-T153e) — передаём 0.0.
        info = detect_feedback_break_node(
            netlist_text=netlist_text,
            confidence_threshold=0.0,
        )
        if not auto_detect_confirmation(info):
            msg = (
                f'auto-detect rejected: chosen edge '
                f'(node={info.chosen_node!r}, '
                f'element={info.chosen_element_ref!r}) '
                f'confidence {info.confidence:.3f} not accepted by caller'
            )
            raise AutoDetectRejectedError(msg)
        return info.chosen_node, info.chosen_element_ref, info
    msg = (
        'measure_phase_margin: break_node и break_element_ref должны быть '
        'переданы пара (оба или ни одного — последнее активирует auto-detect).'
    )
    raise ValueError(msg)


def _build_snapshot(
    *,
    measurement: PhaseMarginMeasurement,
    netlist: Path,
    project_root: Path,
    tool: str,
) -> SimResult:
    try:
        source_file = str(netlist.resolve().relative_to(project_root.resolve()))
    except ValueError:
        source_file = netlist.name
    timestamp = datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
    summary = (
        f'PM: {measurement.margin_deg:.1f}° @ '
        f'{measurement.crossover_hz:.1f} Hz '
        f'({measurement.stability_class}, '
        f'{measurement.injection_method})'
    )
    return SimResult(
        timestamp=timestamp,
        analysis_type=AnalysisType.PHASE_MARGIN,
        source_file=source_file,
        tool=tool,
        duration_seconds=0.0,
        summary=summary,
        metrics={
            'margin_deg': measurement.margin_deg,
            'crossover_hz': measurement.crossover_hz,
            'measured_at_node': measurement.measured_at_node,
            'injection_method': measurement.injection_method,
            'stability_class': measurement.stability_class,
            'extra_crossovers_hz': list(measurement.extra_crossovers_hz),
        },
    )


__all__ = ['measure_phase_margin']
