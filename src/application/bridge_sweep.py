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
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from application.edit_component_value import edit_component_value
from application.sim_run import sim_run
from domain.simulation import SimulationResult
from ports.outbound.schematic_exporter import SchematicExportError
from ports.outbound.simulator import SimulationFailedError

if TYPE_CHECKING:
    from domain.simulation import AnalysisSpec
    from ports.outbound.schematic_exporter import SchematicExporter
    from ports.outbound.simulator import Simulator


class SweepRun(BaseModel):
    """Один прогон sweep'а: фиксированные параметры + результат симуляции."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    parameters: dict[str, str]
    result: SimulationResult | None  # None если симуляция failed
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
