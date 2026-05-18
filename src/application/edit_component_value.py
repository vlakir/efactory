"""
edit_component_value — изменить `value`-проперти компонента в `.kicad_sch` (T004b).

Текстовая targeted-замена: найти `(symbol ... (property "Reference" "R1" ...))`
блок, в нём заменить `(property "Value" "OLD" ...)` → `(property "Value" "NEW" ...)`.
Атомарная запись (`tmp + os.replace`).

Минималистично: только value-edit, без model-swap (Sim.Name/Sim.Library —
T005). Не парсит s-expr (sexpdata round-trip ломает форматирование
KiCad-файла); regex-based точечный replace сохраняет всё кроме целевого
property.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path


class ComponentNotFoundError(Exception):
    """Symbol с указанным reference не найден в schematic."""


class MultipleMatchesError(Exception):
    """Найдено более одного symbol с этим reference (annotation collision)."""


def _find_symbol_block(text: str, reference: str) -> tuple[int, int]:
    """
    Найти диапазон `(symbol ... (property "Reference" "<reference>" ...) ...)`.

    Возвращает `(start, end)` — позиции открывающей `(` и после закрывающей `)`.
    Raises `ComponentNotFoundError` / `MultipleMatchesError`.
    """
    # Find all `(symbol` opener positions at top level (после `(lib_symbols ...)
    # каждый component обернут в balanced `(symbol ... )`).
    matches: list[tuple[int, int]] = []
    ref_pattern = re.compile(
        rf'\(property "Reference" "{re.escape(reference)}"',
    )
    # Iterate all `(symbol` occurrences after `(lib_symbols`. Component
    # instance symbol blocks live AFTER the `(lib_symbols ...)` closing.
    # We can't easily skip lib_symbols section; instead, walk all (symbol
    # ... ) blocks and check via ref_pattern.
    pos = 0
    while True:
        idx = text.find('(symbol', pos)
        if idx == -1:
            break
        depth = 0
        i = idx
        while i < len(text):
            if text[i] == '(':
                depth += 1
            elif text[i] == ')':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
            i += 1
        else:
            break
        block = text[idx:end]
        if ref_pattern.search(block):
            matches.append((idx, end))
        pos = end
    if not matches:
        msg = f'No symbol with Reference={reference!r} в schematic'
        raise ComponentNotFoundError(msg)
    if len(matches) > 1:
        msg = (
            f'Multiple symbols ({len(matches)}) с Reference={reference!r} '
            f'(annotation collision; ожидается уникальный)'
        )
        raise MultipleMatchesError(msg)
    return matches[0]


def edit_component_value(
    schematic_path: Path,
    reference: str,
    new_value: str,
) -> str:
    """
    Заменить value компонента `reference` на `new_value`. Возвращает old_value.

    Атомарная запись через `tmp + os.replace`. Не трогает Sim.* / Reference /
    другие properties — только `(property "Value" "..." ...)` верхнего уровня
    внутри symbol-блока (не trogu `(property "Value" "..."` в `lib_symbols`
    secции).
    """
    text = schematic_path.read_text(encoding='utf-8')
    start, end = _find_symbol_block(text, reference)
    symbol_block = text[start:end]
    value_pattern = re.compile(r'\(property "Value" "([^"]*)"')
    m = value_pattern.search(symbol_block)
    if m is None:
        msg = (
            f'Symbol с Reference={reference!r} не содержит '
            f'(property "Value" ...) — повреждённый schematic?'
        )
        raise ComponentNotFoundError(msg)
    old_value = m.group(1)
    if old_value == new_value:
        return old_value  # no-op
    new_block = (
        symbol_block[: m.start()]
        + f'(property "Value" "{new_value}"'
        + symbol_block[m.end() :]
    )
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
    return old_value


__all__ = [
    'ComponentNotFoundError',
    'MultipleMatchesError',
    'edit_component_value',
]
