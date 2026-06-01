"""
edit_and_resim_with_delta — orchestration «baseline → edit → after → delta» (T021).

Sequence:

1. Export baseline `.cir` из текущей `.kicad_sch`.
2. Снять baseline-измерения по каждой метрике из `config.metrics`
   (dispatch на `measure_{gain,bandwidth,thd}`). Любой failure baseline —
   `BaselineFailedError`, edit'ы не применяются.
3. Применить batch edits через `SchematicSnapshot` + `edit_component_value`.
   На failure любого edit'а — Snapshot rollback'ит `.kicad_sch` к baseline-
   состоянию, исходный exception re-raise'ится.
4. Export after `.cir` из изменённой `.kicad_sch`. На failure export'а —
   каждая after-метрика помечается `failed_reason='export failed: ...'`.
5. Снять after-измерения. Любой failure отдельной метрики помечается
   `failed_reason`; остальные собираются нормально (Q-E → a: schematic
   уже изменён, rollback не делается).
6. Собрать `EditAndResimReport` с per-metric `*Delta` VO.

Use case намеренно НЕ делает caching netlist'ов / fusion измерений —
каждый measure запускает свой ngspice subprocess (Analyze A1: accepted
cost ради простоты, parallel параметризация — отдельным backlog'ом).
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal, Self, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from application.edit_component_value import edit_component_value
from application.measure_bandwidth import measure_bandwidth
from application.measure_gain import measure_gain
from application.measure_phase_margin import measure_phase_margin
from application.measure_thd import measure_thd
from application.schematic_snapshot import SchematicSnapshot
from domain.measurement import (
    BandwidthMeasurement,
    GainMeasurement,
    ThdMeasurement,
)
from domain.measurement_delta import (
    BandwidthDelta,
    GainDelta,
    ThdDelta,
)
from domain.phase_margin import (
    PhaseMarginDelta,
    PhaseMarginMeasurement,
)
from ports.outbound.schematic_exporter import SchematicExportError
from ports.outbound.simulator import SimulationFailedError

if TYPE_CHECKING:
    from domain.phase_margin import ConfirmationCallback
    from domain.phase_margin_injection import InjectionStrategy
    from ports.outbound.netlist_editor import NetlistEditor
    from ports.outbound.schematic_exporter import SchematicExporter
    from ports.outbound.simulator import Simulator


Metric = Literal['gain', 'bandwidth', 'thd', 'phase_margin']
GainMode = Literal['small', 'large']

# Soft warn-порог: типичный one-shot edit'ит 1–5 компонентов; при
# 10+ имеет смысл разбивать на серию шагов (W5).
SOFT_WARN_EDITS = 10


class BaselineFailedError(Exception):
    """Baseline-измерение упало; edit'ы не применены."""

    def __init__(self, metric: Metric, cause: Exception) -> None:
        super().__init__(
            f'baseline {metric} measurement failed: {cause}. '
            f'Edits NOT applied; schematic unchanged.',
        )
        self.metric = metric
        self.__cause__ = cause


class EditAndResimConfig(BaseModel):
    """
    Параметры measure-dispatch'а для `edit_and_resim_with_delta`.

    Один config — на baseline и after; required-поля проверяются
    относительно выбранных метрик. Дубликаты в `metrics` silently
    дедуплицируются с сохранением порядка (UX: Typer-повторяемый
    `--measure` может случайно дать `[gain, gain]`).
    """

    model_config = ConfigDict(frozen=True, extra='forbid')

    metrics: list[Metric]
    frequency_hz: float | None = None
    v_in_peak: float | None = None
    f_low_hz: float = Field(default=1.0, gt=0.0)
    f_high_hz: float = Field(default=1e6, gt=0.0)
    mode: GainMode = 'small'
    output_signal: str = 'v(load)'
    input_signal: str | None = None
    input_source: str | None = None
    n_harmonics: int = Field(default=10, ge=3, le=20)
    load_ohm: float = Field(default=8.0, gt=0.0)
    # Phase-margin specific (T153 Phase B.7): edge-pair либо оба заданы,
    # либо ни одного (последнее → auto-detect через callback).
    loop_break_node: str | None = None
    break_element_ref: str | None = None
    pm_n_points_per_decade: int = Field(default=100, ge=10, le=10_000)

    @model_validator(mode='after')
    def _dedupe_and_validate(self) -> Self:
        deduped: list[Metric] = list(dict.fromkeys(self.metrics))
        object.__setattr__(self, 'metrics', deduped)
        if not deduped:
            msg = (
                'metrics: at least one metric required '
                '(gain/bandwidth/thd/phase_margin)'
            )
            raise ValueError(msg)
        if 'gain' in deduped and self.frequency_hz is None:
            msg = 'frequency_hz required when metric=gain is selected'
            raise ValueError(msg)
        if 'thd' in deduped:
            if self.frequency_hz is None:
                msg = 'frequency_hz required when metric=thd is selected'
                raise ValueError(msg)
            if self.v_in_peak is None:
                msg = 'v_in_peak required when metric=thd is selected'
                raise ValueError(msg)
        if 'gain' in deduped and self.mode == 'large' and self.v_in_peak is None:
            msg = 'v_in_peak required when metric=gain and mode=large'
            raise ValueError(msg)
        if self.f_high_hz <= self.f_low_hz:
            msg = (
                f'f_high_hz ({self.f_high_hz}) must be greater than '
                f'f_low_hz ({self.f_low_hz})'
            )
            raise ValueError(msg)
        # Edge-pair fail-fast (ADR-T153d): half-explicit запрещён.
        half_explicit = (self.loop_break_node is None) != (
            self.break_element_ref is None
        )
        if half_explicit:
            msg = (
                'loop_break_node и break_element_ref должны быть переданы '
                'парой (оба или ни одного — последнее активирует auto-detect).'
            )
            raise ValueError(msg)
        return self


class EditAndResimReport(BaseModel):
    """
    Итог `edit_and_resim_with_delta` — для CLI renderer'а (text/JSON).

    `deltas` — discriminated union по `metric_field`: `value_db` →
    `GainDelta`, `bandwidth_hz` → `BandwidthDelta`, `thd_percent` →
    `ThdDelta`.
    """

    model_config = ConfigDict(frozen=True, extra='forbid')

    schematic: str
    edits: list[tuple[str, str]]
    deltas: list[
        Annotated[
            GainDelta | BandwidthDelta | ThdDelta | PhaseMarginDelta,
            Field(discriminator='metric_field'),
        ]
    ]
    project: str | None = None


# Точка входа — async use case.


async def edit_and_resim_with_delta(
    *,
    schematic: Path,
    edits: list[tuple[str, str]],
    config: EditAndResimConfig,
    exporter: SchematicExporter,
    simulator: Simulator,
    netlist_editor: NetlistEditor,
    netlist_dir: Path | None = None,
    timeout_seconds: float = 60.0,
    project: str | None = None,
    injection_strategy: InjectionStrategy | None = None,
    auto_detect_confirmation: ConfirmationCallback | None = None,
) -> EditAndResimReport:
    """
    Применить `edits` к `schematic`, снять `config.metrics` до/после, вернуть отчёт.

    Args:
        schematic: путь к `.kicad_sch` (mutated по месту через
            `edit_component_value`; защищён `SchematicSnapshot`).
        edits: упорядоченный список `(reference, new_value)`. Empty list →
            `ValueError`. Список длиннее `SOFT_WARN_EDITS` (10) — soft
            warning в stderr.
        config: параметры measure-dispatch'а (см. `EditAndResimConfig`).
        exporter: outbound port (`SchematicExporter`) — вызывается дважды
            (baseline и after).
        simulator: outbound port (ngspice).
        netlist_editor: outbound port — нужен `measure_*` для
            `ensure_ac_modifier` / `set_sin_source_amplitude` /
            `find_top_level_v_sources`.
        netlist_dir: опциональная директория для debug-копий netlist'ов
            (baseline.cir / after.cir). Если None — netlist'ы живут в
            tempdir и удаляются по выходу.
        timeout_seconds: единый лимит на каждый ngspice run.
        project: имя проекта (заполняется CLI слоем) — для report metadata.
        injection_strategy: domain strategy для phase-margin injection
            (composition root собирает через `_INJECTION_STRATEGY_BUILDERS`).
            Обязателен, если `'phase_margin' in config.metrics`.
        auto_detect_confirmation: callback `(AutoDetectInfo) -> bool` для
            phase-margin auto-detect ветки (`config.loop_break_node` /
            `config.break_element_ref` оба None). Обязателен в auto-detect
            ветке; CLI собирает из `typer.confirm` / threshold-policy.

    Returns:
        `EditAndResimReport` с deltas, edits, schematic-ref, project.

    Raises:
        ValueError: пустой `edits`.
        BaselineFailedError: любой baseline-measure упал.
        ComponentNotFoundError / MultipleMatchesError / SchematicExportError:
            edit или baseline-export упал — schematic откачен Snapshot'ом
            (если edit был в процессе), exception пробрасывается.

    """
    if not edits:
        msg = 'edits: at least one (ref, value) pair required'
        raise ValueError(msg)
    # Soft-warn про большие batch'и выпускает CLI-слой (см. T022 паттерн);
    # use case экспортит `SOFT_WARN_EDITS` константу для CLI-сравнения.

    metrics: list[Metric] = list(config.metrics)

    if 'phase_margin' in metrics and injection_strategy is None:
        msg = (
            'edit_and_resim_with_delta: injection_strategy обязателен '
            'когда metric=phase_margin (composition root должен собрать '
            'InjectionStrategy через _INJECTION_STRATEGY_BUILDERS).'
        )
        raise ValueError(msg)

    if netlist_dir is not None:
        await asyncio.to_thread(
            netlist_dir.mkdir,
            parents=True,
            exist_ok=True,
        )

    with tempfile.TemporaryDirectory(prefix='efactory-resim-') as tmp:
        tmp_dir = Path(tmp)

        baseline_netlist = tmp_dir / f'{schematic.stem}.baseline.cir'
        await exporter.export_spice_netlist(schematic, baseline_netlist)
        if netlist_dir is not None:
            await _copy_netlist(baseline_netlist, netlist_dir / 'baseline.cir')

        # 2. Baseline measurements (strict — first failure aborts).
        baseline: dict[Metric, _BaselineValue] = {}
        for metric in metrics:
            try:
                baseline[metric] = await _measure_one(
                    metric=metric,
                    netlist=baseline_netlist,
                    config=config,
                    simulator=simulator,
                    netlist_editor=netlist_editor,
                    timeout_seconds=timeout_seconds,
                    injection_strategy=injection_strategy,
                    auto_detect_confirmation=auto_detect_confirmation,
                )
            except (SimulationFailedError, ValueError) as exc:
                raise BaselineFailedError(metric, exc) from exc

        # 3. Apply batch edits под SchematicSnapshot (W4 / A2).
        with SchematicSnapshot(schematic) as snap:
            for ref, value in edits:
                edit_component_value(schematic, ref, value)
            snap.commit()

        # 4. Export after netlist; failure → all metrics failed.
        after_netlist = tmp_dir / f'{schematic.stem}.after.cir'
        export_failure: str | None = None
        try:
            await exporter.export_spice_netlist(schematic, after_netlist)
            if netlist_dir is not None:
                await _copy_netlist(after_netlist, netlist_dir / 'after.cir')
        except SchematicExportError as exc:
            export_failure = f'export failed: {exc}'

        # 5. After measurements (per-metric continue-on-failure).
        after: dict[Metric, _AfterOutcome] = {}
        for metric in metrics:
            if export_failure is not None:
                after[metric] = export_failure
                continue
            try:
                after[metric] = await _measure_one(
                    metric=metric,
                    netlist=after_netlist,
                    config=config,
                    simulator=simulator,
                    netlist_editor=netlist_editor,
                    timeout_seconds=timeout_seconds,
                    injection_strategy=injection_strategy,
                    auto_detect_confirmation=auto_detect_confirmation,
                )
            except (SimulationFailedError, ValueError) as exc:
                after[metric] = f'{type(exc).__name__}: {exc}'

    # 6. Assemble deltas.
    deltas: list[GainDelta | BandwidthDelta | ThdDelta | PhaseMarginDelta] = []
    for metric in metrics:
        before_value = baseline[metric]
        after_value = after[metric]
        deltas.append(_make_delta(metric, before_value, after_value))

    return EditAndResimReport(
        schematic=str(schematic),
        edits=list(edits),
        deltas=deltas,
        project=project,
    )


# --------------------------------------------------------------- Internal helpers ----


_BaselineValue = (
    GainMeasurement | BandwidthMeasurement | ThdMeasurement | PhaseMarginMeasurement
)
_AfterOutcome = _BaselineValue | str  # str = failed_reason


async def _measure_one(
    *,
    metric: Metric,
    netlist: Path,
    config: EditAndResimConfig,
    simulator: Simulator,
    netlist_editor: NetlistEditor,
    timeout_seconds: float,
    injection_strategy: InjectionStrategy | None,
    auto_detect_confirmation: ConfirmationCallback | None,
) -> _BaselineValue:
    if metric == 'gain':
        # Validator EditAndResimConfig гарантирует frequency_hz при metric=gain.
        return await measure_gain(
            netlist=netlist,
            frequency_hz=cast('float', config.frequency_hz),
            mode=config.mode,
            simulator=simulator,
            netlist_editor=netlist_editor,
            output_signal=config.output_signal,
            input_source=config.input_source,
            input_signal=config.input_signal,
            v_in_peak=config.v_in_peak,
            timeout_seconds=timeout_seconds,
        )
    if metric == 'bandwidth':
        return await measure_bandwidth(
            netlist=netlist,
            simulator=simulator,
            netlist_editor=netlist_editor,
            f_low=config.f_low_hz,
            f_high=config.f_high_hz,
            output_signal=config.output_signal,
            input_source=config.input_source,
            timeout_seconds=timeout_seconds,
        )
    if metric == 'thd':
        # Validator гарантирует frequency_hz + v_in_peak при metric=thd.
        return await measure_thd(
            netlist=netlist,
            frequency_hz=cast('float', config.frequency_hz),
            v_in_peak=cast('float', config.v_in_peak),
            simulator=simulator,
            netlist_editor=netlist_editor,
            signal=config.output_signal,
            input_source=config.input_source,
            load_ohm=config.load_ohm,
            n_harmonics=config.n_harmonics,
            timeout_seconds=timeout_seconds,
        )
    if metric == 'phase_margin':
        # Entry-validator гарантирует injection_strategy is not None
        # при наличии phase_margin в metrics.
        return await measure_phase_margin(
            netlist=netlist,
            injection_strategy=cast('InjectionStrategy', injection_strategy),
            break_node=config.loop_break_node,
            break_element_ref=config.break_element_ref,
            auto_detect_confirmation=auto_detect_confirmation,
            simulator=simulator,
            f_low=config.f_low_hz,
            f_high=config.f_high_hz,
            n_points_per_decade=config.pm_n_points_per_decade,
            timeout_seconds=timeout_seconds,
        )
    msg = f'unknown metric: {metric!r}'  # pragma: no cover (typed Literal)
    raise ValueError(msg)


_BuiltDelta = GainDelta | BandwidthDelta | ThdDelta | PhaseMarginDelta


def _make_delta(
    metric: Metric,
    before_value: _BaselineValue,
    after_value: _AfterOutcome,
) -> _BuiltDelta:
    # `before_value` всегда соответствует `metric` (use case собирает их
    # в одной dispatch-петле); isinstance-проверки нужны mypy для
    # type-narrow перед передачей в `from_measurements`.
    result: _BuiltDelta | None = None
    if metric == 'gain' and isinstance(before_value, GainMeasurement):
        if isinstance(after_value, str):
            result = GainDelta.from_failed_after(
                before=before_value,
                reason=after_value,
            )
        elif isinstance(after_value, GainMeasurement):
            result = GainDelta.from_measurements(
                before=before_value,
                after=after_value,
            )
    elif metric == 'bandwidth' and isinstance(before_value, BandwidthMeasurement):
        if isinstance(after_value, str):
            result = BandwidthDelta.from_failed_after(
                before=before_value,
                reason=after_value,
            )
        elif isinstance(after_value, BandwidthMeasurement):
            result = BandwidthDelta.from_measurements(
                before=before_value,
                after=after_value,
            )
    elif metric == 'thd' and isinstance(before_value, ThdMeasurement):
        if isinstance(after_value, str):
            result = ThdDelta.from_failed_after(
                before=before_value,
                reason=after_value,
            )
        elif isinstance(after_value, ThdMeasurement):
            result = ThdDelta.from_measurements(
                before=before_value,
                after=after_value,
            )
    elif metric == 'phase_margin' and isinstance(before_value, PhaseMarginMeasurement):
        if isinstance(after_value, str):
            result = PhaseMarginDelta.from_failed_after(
                before=before_value,
                reason=after_value,
            )
        elif isinstance(after_value, PhaseMarginMeasurement):
            result = PhaseMarginDelta.from_measurements(
                before=before_value,
                after=after_value,
            )
    if result is None:
        # Defensive — type-narrow gate уже отработал; типы Literal +
        # один before/after type per metric не дают сюда добраться.
        msg = (  # pragma: no cover
            f'_make_delta: metric/before/after type mismatch: '
            f'metric={metric!r}, before={type(before_value).__name__}, '
            f'after={type(after_value).__name__}'
        )
        raise TypeError(msg)
    return result


async def _copy_netlist(src: Path, dst: Path) -> None:
    text = await asyncio.to_thread(src.read_text)
    await asyncio.to_thread(dst.write_text, text)


__all__ = [
    'BaselineFailedError',
    'EditAndResimConfig',
    'EditAndResimReport',
    'edit_and_resim_with_delta',
]
