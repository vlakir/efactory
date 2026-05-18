"""
Parser SPICE-нотации чисел с power-of-10 суффиксами (T008 Phase 4).

Поддержка:
- f, F  → 1e-15 (femto)
- p, P  → 1e-12 (pico)
- n, N  → 1e-9  (nano)
- u, U  → 1e-6  (micro)
- m     → 1e-3  (milli)
- k, K  → 1e3   (kilo)
- Meg/MEG/meg → 1e6 (mega) — должно проверяться до single-char `m`/`M`
- G, g  → 1e9   (giga)
- T, t  → 1e12  (tera)

После префикса любые буквы — unit-hint (ngspice convention): `20mA` → 0.020,
`1kHz` → 1000, `1uF` → 1e-6.
"""

from __future__ import annotations

import re

_NUMBER_RE = re.compile(r'^([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)([A-Za-z]*)$')

_MEG_TOKENS = ('Meg', 'MEG', 'meg')

_SINGLE_CHAR_PREFIXES: dict[str, float] = {
    'f': 1e-15,
    'F': 1e-15,
    'p': 1e-12,
    'P': 1e-12,
    'n': 1e-9,
    'N': 1e-9,
    'u': 1e-6,
    'U': 1e-6,
    'm': 1e-3,  # mega имеет приоритет — проверяется ДО single-char
    'k': 1e3,
    'K': 1e3,
    'g': 1e9,
    'G': 1e9,
    't': 1e12,
    'T': 1e12,
}


class SpiceNumberFormatError(ValueError):
    """Строка не похожа на SPICE-число (число + опц. префикс + опц. unit-hint)."""


def parse_spice_number(text: str) -> float:
    """Разобрать SPICE-нотацию: `1k`, `1.5Meg`, `20mA`, `1e3`, `-2.5e-3`."""
    stripped = text.strip()
    match = _NUMBER_RE.match(stripped)
    if match is None:
        msg = f'SPICE-число не распознано: {text!r}'
        raise SpiceNumberFormatError(msg)

    number_part, suffix = match.group(1), match.group(2)
    value = float(number_part)

    if not suffix:
        return value

    # Mega-проверка первой (строковый литерал, чтобы не путать с milli `m`).
    for meg in _MEG_TOKENS:
        if suffix.startswith(meg):
            return value * 1e6

    head = suffix[0]
    multiplier = _SINGLE_CHAR_PREFIXES.get(head)
    if multiplier is None:
        msg = f'SPICE-число: неизвестный префикс {head!r} в {text!r}'
        raise SpiceNumberFormatError(msg)
    return value * multiplier


__all__ = ['SpiceNumberFormatError', 'parse_spice_number']
