"""
bridge_sweep — параметрический run симуляций (T004b Phase 1).

Алгоритм: Cartesian product over parameter value lists → для каждой
комбинации копия schematic → apply edits → design_to_sim → собираем
SimulationResult. Оригинальный schematic не трогается.

MVP scope (T004b Phase 1):
* Только OP analysis (TRAN/AC — Phase 2 backlog T021/T022).
* Output: list[SweepRun] — пары (parameters dict, SimulationResult).

CLI представление через `bridge sweep` — печатает table parameters +
operating_points per combination.
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
from application.sim_run import sim_run
from domain.simulation import SimulationResult
from ports.outbound.schematic_exporter import SchematicExportError
from ports.outbound.simulator import SimulationFailedError

if TYPE_CHECKING:
    from domain.simulation import AnalysisSpec
    from ports.outbound.schematic_exporter import SchematicExporter
    from ports.outbound.simulator import Simulator


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
    analysis: AnalysisSpec,
    exporter: SchematicExporter,
    simulator: Simulator,
    netlist_dir: Path | None = None,
    timeout_seconds: float = 60.0,
) -> list[SweepRun]:
    """
    Прогнать sweep по Cartesian product `parameters`.

    `parameters` — dict[ref → list_of_values]. Например,
    `{'R1': ['1k', '10k'], 'C1': ['100n', '1u']}` даёт 4 combinations.

    Для каждой combination: копия schematic, apply edits, export netlist,
    run sim. На failure (export или sim) — добавить SweepRun с
    `result=None, error='...'` и продолжить (sweep не аборт).

    `netlist_dir` — куда писать netlist files (для debug). Если None —
    tempdir per run.
    """
    refs = list(parameters)
    value_lists = [parameters[r] for r in refs]
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

            try:
                result = await sim_run(
                    netlist=netlist,
                    analysis=analysis,
                    simulator=simulator,
                    timeout_seconds=timeout_seconds,
                )
            except SimulationFailedError as exc:
                runs.append(
                    SweepRun(
                        parameters=params_dict,
                        result=None,
                        error=f'sim failed: {exc}',
                    ),
                )
                continue

            runs.append(SweepRun(parameters=params_dict, result=result))

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


__all__ = ['SweepRun', 'bridge_sweep']
