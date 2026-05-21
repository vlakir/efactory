"""
Netlist text manipulation helpers (T131 Phase C).

Используется `analyze_distortion_spectrum` use case'ом для двух operation'ов:

1. **Library substitution** — заменить `.include <path>/<target>.lib`
   (или inline `.SUBCKT <target> ... .ENDS <target>`) на сгенерированный
   saturable subckt с тем же `<target>`-именем. X-инстанс в netlist'е не
   трогается (он ссылается на subckt по имени, а имя сохраняется).

2. **SIN source parameter update** — переписать аргументы `SIN(...)` у
   указанного voltage source ref'а (нодлист сохраняется); используется
   для voltage calibration per (freq, power) cell.

Оба helper'а чисто текстовые: не парсят SPICE как AST, а ищут конкретные
паттерны через regex / token-scan.
"""

from __future__ import annotations

import re

_INCLUDE_PATTERN_CACHE: dict[str, re.Pattern[str]] = {}
_INLINE_BLOCK_PATTERN_CACHE: dict[str, re.Pattern[str]] = {}


def substitute_subckt_library(
    netlist_text: str,
    target_subckt_name: str,
    new_subckt_text: str,
) -> str:
    """
    Заменить library reference / inline-блок на новый subckt-текст.

    Идемпотентно: повторный вызов с тем же `new_subckt_text` — noop
    (если netlist уже содержит этот block).

    Args:
        netlist_text: исходный текст netlist'а.
        target_subckt_name: имя целевого subckt'а (например, ``'OPT_SE_5K_8'``).
        new_subckt_text: текст замены — полный `.SUBCKT ... .ENDS` блок.

    Returns:
        Текст netlist'а с замещённой library / inline-секцией.

    Raises:
        ValueError: если в netlist'е не найден ни `.include` с этим
            именем библиотеки, ни inline `.SUBCKT <target>...`.

    """
    if not target_subckt_name.strip():
        msg = 'target_subckt_name не может быть пустым'
        raise ValueError(msg)

    replacement = new_subckt_text.rstrip()
    include_re = _include_pattern(target_subckt_name)
    new_text, include_count = include_re.subn(replacement, netlist_text)
    if include_count > 0:
        return new_text

    inline_re = _inline_block_pattern(target_subckt_name)
    new_text, inline_count = inline_re.subn(replacement, netlist_text)
    if inline_count > 0:
        return new_text

    msg = (
        f'target subckt {target_subckt_name!r} not found in netlist: '
        f'no `.include` with that library name, no inline `.SUBCKT` block'
    )
    raise ValueError(msg)


def _include_pattern(target_subckt_name: str) -> re.Pattern[str]:
    """Cached regex для `.include <path>/<target>(.lib|.cir|.sub|.inc)?`."""
    if target_subckt_name in _INCLUDE_PATTERN_CACHE:
        return _INCLUDE_PATTERN_CACHE[target_subckt_name]
    pattern = re.compile(
        # Опциональные whitespace в начале строки, потом `.include` или `.lib`
        rf'^[ \t]*\.(?:include|lib)\s+'
        # Опциональные кавычки и path-prefix (с любыми \\ или /):
        rf'["\']?(?:[^\s"\']*[/\\])?'
        # Целевое имя — escape, чтобы дотрейды и спецсимволы не интерпретировались:
        rf'{re.escape(target_subckt_name)}'
        # Опциональное расширение (.lib / .cir / .sub / .inc):
        rf'(?:\.[A-Za-z]+)?'
        # Закрывающая кавычка + конец строки:
        rf'["\']?[ \t]*$',
        re.MULTILINE | re.IGNORECASE,
    )
    _INCLUDE_PATTERN_CACHE[target_subckt_name] = pattern
    return pattern


def _inline_block_pattern(target_subckt_name: str) -> re.Pattern[str]:
    """Cached regex: full `.SUBCKT <target> ... .ENDS <target>` block."""
    if target_subckt_name in _INLINE_BLOCK_PATTERN_CACHE:
        return _INLINE_BLOCK_PATTERN_CACHE[target_subckt_name]
    pattern = re.compile(
        rf'^[ \t]*\.SUBCKT\s+{re.escape(target_subckt_name)}\b'
        rf'.*?'
        rf'^[ \t]*\.ENDS\s+{re.escape(target_subckt_name)}[ \t]*$',
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    _INLINE_BLOCK_PATTERN_CACHE[target_subckt_name] = pattern
    return pattern


def set_sin_source_amplitude(
    netlist_text: str,
    *,
    source_ref: str,
    amplitude_peak: float,
    frequency_hz: float,
    offset: float = 0.0,
) -> str:
    """
    Переписать аргументы `SIN(...)` у указанного voltage source.

    Преобразует строку вида ``<ref> <node1> <node2> ... SIN(<old>...)``
    в ``<ref> <node1> <node2> ... SIN(<offset> <amp> <freq>)``. Все
    токены до `SIN(` сохраняются, что позволяет работать с разными
    представлениями (с AC-параметром, без него и т.п.).

    Args:
        netlist_text: исходный текст netlist'а.
        source_ref: ref voltage source'а (например, ``'V_in'``, ``'V1'``).
        amplitude_peak: пиковая амплитуда (V).
        frequency_hz: частота (Hz).
        offset: DC-offset (V), default 0.

    Raises:
        ValueError: если строка с `<ref> ... SIN(...)` не найдена.

    """
    if not source_ref.strip():
        msg = 'source_ref не может быть пустым'
        raise ValueError(msg)
    if amplitude_peak < 0.0:
        msg = f'amplitude_peak должен быть ≥ 0, получено {amplitude_peak!r}'
        raise ValueError(msg)
    if frequency_hz <= 0.0:
        msg = f'frequency_hz должен быть > 0, получено {frequency_hz!r}'
        raise ValueError(msg)

    sin_args = f'{_g(offset)} {_g(amplitude_peak)} {_g(frequency_hz)}'
    new_sin = f'SIN({sin_args})'
    target = source_ref.upper()
    lines = netlist_text.splitlines(keepends=True)
    found = False

    for idx, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped:
            continue
        tokens = stripped.split(maxsplit=1)
        if not tokens or tokens[0].upper() != target:
            continue
        sin_match = re.search(r'SIN\s*\([^)]*\)', stripped, re.IGNORECASE)
        if sin_match is None:
            continue
        # offset in original line where stripped content begins
        leading_ws = line[: len(line) - len(stripped)]
        before_sin = stripped[: sin_match.start()].rstrip()
        trailing = stripped[sin_match.end() :]
        new_line = f'{leading_ws}{before_sin} {new_sin}{trailing}'
        if line.endswith('\n') and not new_line.endswith('\n'):
            new_line += '\n'
        lines[idx] = new_line
        found = True
        break

    if not found:
        msg = f'voltage source {source_ref!r} with SIN(...) not found in netlist'
        raise ValueError(msg)
    return ''.join(lines)


def _g(value: float) -> str:
    """Compact float rendering — same convention как в saturable_core."""
    return f'{value:.9g}'


__all__ = ['set_sin_source_amplitude', 'substitute_subckt_library']
