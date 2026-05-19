"""
edit_component_model — swap SPICE model компонента в `.kicad_sch` (T005 Phase 1).

Расширение T004b `edit_component_value` для tube/diode/transformer/load
instances: меняет `Value` + `Sim.Library` + `Sim.Name` properties одним
атомарным write'ом (через tmp + os.replace).

Use case: пользователь хочет swap'нуть `XV1: 6P14P` на `XV1: 6N1P` без
ручной правки s-expr — фасад резолвит SpiceModel из library, фасад
эмитит правильные Sim.* properties.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from application.edit_component_value import (
    ComponentNotFoundError,
    _find_symbol_block,
)

if TYPE_CHECKING:
    from domain.spice_model import SpiceModel


def edit_component_model(
    schematic_path: Path,
    reference: str,
    spice_model: SpiceModel,
) -> dict[str, str]:
    """
    Swap SPICE model для компонента `reference` на `spice_model`.

    Обновляет три property atomically:
    * `Value` → `spice_model.id`
    * `Sim.Library` → `str(spice_model.file_path)`
    * `Sim.Name` → `spice_model.id`

    Возвращает dict со старыми значениями для отображения diff
    (e.g. `{'Value': '6P14P', 'Sim.Name': '6P14P', ...}`).

    Raises `ComponentNotFoundError` если symbol с reference не найден
    ИЛИ если у symbol'а нет ожидаемых Sim.* properties (не-subckt
    компонент — например, обычный R/C).
    """
    text = schematic_path.read_text(encoding='utf-8')
    start, end = _find_symbol_block(text, reference)
    symbol_block = text[start:end]

    updates = {
        'Value': spice_model.id,
        'Sim.Library': str(spice_model.file_path),
        'Sim.Name': spice_model.id,
    }
    old_values: dict[str, str] = {}
    new_block = symbol_block

    for prop_name, new_value in updates.items():
        pattern = re.compile(
            rf'\(property "{re.escape(prop_name)}" "([^"]*)"',
        )
        match = pattern.search(new_block)
        if match is None:
            msg = (
                f'Symbol с Reference={reference!r} не содержит '
                f'(property "{prop_name}" ...) — не subckt-инстанс? '
                f'edit_component_model работает с tube/diode/transformer/'
                f'load компонентами, имеющими Sim.Library + Sim.Name.'
            )
            raise ComponentNotFoundError(msg)
        old_values[prop_name] = match.group(1)
        new_block = (
            new_block[: match.start()]
            + f'(property "{prop_name}" "{new_value}"'
            + new_block[match.end() :]
        )

    if all(old_values[k] == updates[k] for k in updates):
        return old_values  # no-op

    new_text = text[:start] + new_block + text[end:]
    # Atomic write
    tmp_fd, tmp_name = tempfile.mkstemp(
        dir=str(schematic_path.parent),
        prefix=f'.{schematic_path.name}.',
        suffix='.tmp',
    )
    try:
        with os.fdopen(tmp_fd, 'w', encoding='utf-8') as fh:
            fh.write(new_text)
        Path(tmp_name).replace(schematic_path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return old_values


__all__ = ['edit_component_model']
