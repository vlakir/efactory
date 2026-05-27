"""
bridge_sweep — параметрический run симуляций (T022 generalised).

Алгоритм: Cartesian product over parameter value lists → для каждой
комбинации копия schematic → apply edits → design_to_sim ИЛИ
measure_* → собираем `values` dict per A5 mapping.

Metric dispatch (T022 A1):
* `op`     → existing `sim_run(OpAnalysis)`, values = operating_points.
* `gain`   → `measure_gain` use case → `{gain_db, gain_linear}`.
* `bandwidth` → `measure_bandwidth` → `{f_low_hz, f_high_hz, bandwidth_hz}`.
* `thd`    → `measure_thd` → `{thd_percent, dominant_harmonic_n,
            dominant_harmonic_percent}`.
"""

from __future__ import annotations

import asyncio
import itertools
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from application.edit_component_value import edit_component_value
from application.measure_bandwidth import measure_bandwidth
from application.measure_gain import measure_gain
from application.measure_thd import measure_thd
from application.sim_run import sim_run
from domain.simulation import OpAnalysis, SimulationResult
from ports.outbound.schematic_exporter import SchematicExportError
from ports.outbound.simulator import SimulationFailedError

if TYPE_CHECKING:
    from ports.outbound.netlist_editor import NetlistEditor
    from ports.outbound.schematic_exporter import SchematicExporter
    from ports.outbound.simulator import Simulator


# T022 H: hard cap для N combinations. Override через `--max-combinations` CLI.
MAX_COMBINATIONS_DEFAULT = 100
# Soft warn threshold (Phase C: warning в stderr).
SOFT_WARN_COMBINATIONS = 20


MetricKind = Literal['op', 'gain', 'bandwidth', 'thd']
AnalysisKind = Literal['op', 'tran', 'ac']
GainMode = Literal['small', 'large']


# T022 Analyze A1: строгий список валидных (metric, analysis, mode) пар.
# Любая другая комбинация → ValidationError 'incompatible'.
_REQUIRED_ANALYSIS: dict[tuple[MetricKind, GainMode | None], AnalysisKind] = {
    ('op', None): 'op',
    ('gain', 'small'): 'ac',
    ('gain', 'large'): 'tran',
    ('bandwidth', None): 'ac',
    ('thd', None): 'tran',
}


class SweepConfig(BaseModel):
    """
    Конфиг одного `bridge_sweep` запуска (T022, Analyze A1).

    Combo `(metric, analysis, mode)` валидируется по строгому списку
    `_REQUIRED_ANALYSIS`. Если `analysis` не указан явно — выводится
    из `(metric, mode)`. Required-поля per metric проверяются
    отдельно (frequency_hz, v_in_peak, f_low/f_high).
    """

    model_config = ConfigDict(frozen=True, extra='forbid')

    metric: MetricKind = 'op'
    analysis: AnalysisKind | None = None
    mode: GainMode | None = None
    frequency_hz: float | None = None
    v_in_peak: float | None = None
    f_low_hz: float = Field(default=1.0)
    f_high_hz: float = Field(default=1e6)
    output_signal: str = 'v(load)'
    # Optional input signal — нужен для `--metric gain --mode large`
    # (measure_gain требует явный trace name для RMS-computation).
    input_signal: str | None = None
    # Optional V-source ref — нужен на multi-V netlist'ах (se-amp с B+
    # и input source); без него measure_* auto-detect падает ambiguity'ем.
    input_source: str | None = None

    @model_validator(mode='after')
    def _validate_compat_and_required(self) -> Self:
        # Auto-fill mode для metric='gain' (default small).
        if self.metric == 'gain' and self.mode is None:
            object.__setattr__(self, 'mode', 'small')

        # Auto-clear mode для non-gain.
        if self.metric != 'gain' and self.mode is not None:
            msg = (
                f'incompatible: --mode применим только к --metric=gain, '
                f'получен metric={self.metric!r}'
            )
            raise ValueError(msg)

        # Auto-mapping analysis из metric (+ mode для gain).
        mode_key: GainMode | None = self.mode if self.metric == 'gain' else None
        expected = _REQUIRED_ANALYSIS[(self.metric, mode_key)]
        if self.analysis is None:
            object.__setattr__(self, 'analysis', expected)
        elif self.analysis != expected:
            msg = (
                f'incompatible combination: --metric={self.metric}'
                f'{f" --mode={self.mode}" if self.mode else ""} '
                f'--analysis={self.analysis}; expected --analysis={expected}'
            )
            raise ValueError(msg)

        # Required fields per metric.
        if self.metric in ('gain', 'thd') and self.frequency_hz is None:
            msg = f'frequency_hz обязателен для --metric={self.metric}'
            raise ValueError(msg)
        if self.metric == 'thd' and self.v_in_peak is None:
            msg = 'v_in_peak обязателен для --metric=thd'
            raise ValueError(msg)
        if self.metric == 'gain' and self.mode == 'large' and self.v_in_peak is None:
            msg = 'v_in_peak обязателен для --metric=gain --mode=large'
            raise ValueError(msg)
        return self


class SweepRun(BaseModel):
    """Один прогон sweep'а: фиксированные параметры + результат симуляции."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    parameters: dict[str, str]
    result: SimulationResult | None  # None если симуляция failed
    # T022 A4: опциональное поле — derived от result (op) или Measurement VO
    # (gain/bandwidth/thd). None означает «values не собраны» (либо failure,
    # либо legacy call-path).
    values: dict[str, float | str | None] | None = None
    error: str | None = None  # сообщение об ошибке (если result=None)


async def bridge_sweep(
    *,
    schematic: Path,
    parameters: dict[str, list[str]],
    config: SweepConfig,
    exporter: SchematicExporter,
    simulator: Simulator,
    netlist_editor: NetlistEditor | None = None,
    netlist_dir: Path | None = None,
    timeout_seconds: float = 60.0,
    max_combinations: int = MAX_COMBINATIONS_DEFAULT,
) -> list[SweepRun]:
    """
    Прогнать sweep по Cartesian product `parameters`.

    `parameters` — dict[ref → list_of_values]. Например,
    `{'R1': ['1k', '10k'], 'C1': ['100n', '1u']}` даёт 4 combinations.

    Для каждой combination: копия schematic → apply edits → export netlist
    → measure (per `config.metric` dispatch). На failure (export / sim /
    metric extract) — SweepRun с `error='...'` (Q-D → a, sweep не аборт).

    `netlist_editor` — обязателен для metric ∈ {gain, bandwidth, thd}
    (measure_* use cases требуют). Для `op` — игнорируется.

    `max_combinations` — hard cap; N > cap → ValueError (без запуска).
    """
    refs = list(parameters)
    value_lists = [parameters[r] for r in refs]
    n_combinations = 1
    for vlist in value_lists:
        n_combinations *= len(vlist)
    if n_combinations > max_combinations:
        msg = (
            f'sweep would produce {n_combinations} combinations '
            f'(over hard cap {max_combinations}); pass max_combinations '
            f'override or narrow --param ranges'
        )
        raise ValueError(msg)

    if config.metric != 'op' and netlist_editor is None:
        msg = (
            f'netlist_editor обязателен для --metric={config.metric} '
            f'(measure_* use cases требуют)'
        )
        raise ValueError(msg)

    runs: list[SweepRun] = []

    if netlist_dir is not None:
        # Mkdir один раз вне sweep-loop. Wrap'нут в asyncio.to_thread
        # т.к. async context (sync I/O нельзя в event loop).
        await asyncio.to_thread(
            netlist_dir.mkdir,
            parents=True,
            exist_ok=True,
        )

    for combo in itertools.product(*value_lists):
        params_dict = dict(zip(refs, combo, strict=True))

        with tempfile.TemporaryDirectory(prefix='efactory-sweep-') as tmp_dir:
            tmp_dir_path = Path(tmp_dir)
            tmp_sch = tmp_dir_path / schematic.name
            shutil.copy2(schematic, tmp_sch)
            for ref, value in params_dict.items():
                edit_component_value(tmp_sch, ref, value)

            tmp_netlist = tmp_dir_path / (schematic.stem + '.cir')
            try:
                netlist = await exporter.export_spice_netlist(
                    tmp_sch,
                    tmp_netlist,
                )
            except SchematicExportError as exc:
                runs.append(
                    SweepRun(
                        parameters=params_dict,
                        result=None,
                        error=f'export failed: {exc}',
                    ),
                )
                continue

            run = await _run_one_combination(
                params_dict=params_dict,
                netlist=netlist,
                config=config,
                simulator=simulator,
                netlist_editor=netlist_editor,
                timeout_seconds=timeout_seconds,
            )
            runs.append(run)

            # Save netlist для debug если netlist_dir задан.
            if netlist_dir is not None:
                params_slug = '_'.join(
                    f'{r}-{v}' for r, v in params_dict.items()
                ).replace('/', '_')
                shutil.copy2(
                    netlist,
                    netlist_dir / f'{schematic.stem}_{params_slug}.cir',
                )

    return runs


async def _run_one_combination(
    *,
    params_dict: dict[str, str],
    netlist: Path,
    config: SweepConfig,
    simulator: Simulator,
    netlist_editor: NetlistEditor | None,
    timeout_seconds: float,
) -> SweepRun:
    """
    Dispatch на metric. Failures wrap'аются в SweepRun(error=...) без
    re-raise (Q-D → a: continue on failure).
    """
    try:
        if config.metric == 'op':
            result = await sim_run(
                netlist=netlist,
                analysis=OpAnalysis(),
                simulator=simulator,
                timeout_seconds=timeout_seconds,
            )
            values = _op_values(result)
            return SweepRun(
                parameters=params_dict,
                result=result,
                values=values,
            )
        # Metric path: result=None, values из measure_* VO.
        if netlist_editor is None:  # pragma: no cover (caller-validated)
            msg = 'netlist_editor required for non-op metric'
            raise RuntimeError(msg)
        values = await _measure_values(
            netlist=netlist,
            config=config,
            simulator=simulator,
            netlist_editor=netlist_editor,
            timeout_seconds=timeout_seconds,
        )
        return SweepRun(
            parameters=params_dict,
            result=None,
            values=values,
        )
    except (SimulationFailedError, ValueError) as exc:
        return SweepRun(
            parameters=params_dict,
            result=None,
            values=None,
            error=f'sim failed: {exc}',
        )


def _op_values(result: SimulationResult) -> dict[str, float | str | None]:
    """A5 mapping для metric='op': raw operating_points (signal → value)."""
    if result.operating_points is None:
        return {}
    return dict(result.operating_points.items())


async def _measure_values(
    *,
    netlist: Path,
    config: SweepConfig,
    simulator: Simulator,
    netlist_editor: NetlistEditor,
    timeout_seconds: float,
) -> dict[str, float | str | None]:
    """Dispatch на metric — каждый measure_* возвращает свои VO-поля per A5."""
    if config.metric == 'gain':
        # SweepConfig validator гарантирует non-None — narrowing for mypy.
        if config.frequency_hz is None or config.mode is None:  # pragma: no cover
            msg = 'gain: frequency_hz/mode required (SweepConfig invariant)'
            raise RuntimeError(msg)
        gain = await measure_gain(
            netlist=netlist,
            frequency_hz=config.frequency_hz,
            mode=config.mode,
            simulator=simulator,
            netlist_editor=netlist_editor,
            output_signal=config.output_signal,
            input_signal=config.input_signal,
            input_source=config.input_source,
            v_in_peak=config.v_in_peak,
            timeout_seconds=timeout_seconds,
        )
        return {
            'gain_db': gain.value_db,
            'gain_linear': gain.value_linear,
        }
    if config.metric == 'bandwidth':
        bw = await measure_bandwidth(
            netlist=netlist,
            f_low=config.f_low_hz,
            f_high=config.f_high_hz,
            simulator=simulator,
            netlist_editor=netlist_editor,
            output_signal=config.output_signal,
            input_source=config.input_source,
            timeout_seconds=timeout_seconds,
        )
        return {
            'f_low_hz': bw.f_low_hz,
            'f_high_hz': bw.f_high_hz,
            'bandwidth_hz': bw.bandwidth_hz,
        }
    if config.metric == 'thd':
        if config.frequency_hz is None or config.v_in_peak is None:  # pragma: no cover
            msg = 'thd: frequency_hz/v_in_peak required (SweepConfig invariant)'
            raise RuntimeError(msg)
        thd = await measure_thd(
            netlist=netlist,
            frequency_hz=config.frequency_hz,
            v_in_peak=config.v_in_peak,
            simulator=simulator,
            netlist_editor=netlist_editor,
            signal=config.output_signal,
            input_source=config.input_source,
            timeout_seconds=timeout_seconds,
        )
        return {
            'thd_percent': thd.thd_percent,
            'dominant_harmonic_n': thd.dominant_harmonic_n,
            'dominant_harmonic_percent': thd.dominant_harmonic_percent,
        }
    msg = f'unsupported metric: {config.metric}'
    raise ValueError(msg)


__all__ = [
    'MAX_COMBINATIONS_DEFAULT',
    'SOFT_WARN_COMBINATIONS',
    'SweepConfig',
    'SweepRun',
    'bridge_sweep',
]
