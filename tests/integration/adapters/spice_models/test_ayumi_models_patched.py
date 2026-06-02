"""T167 regression: 8 Ayumi tube models patched к ngspice-syntax.

После T166 (6DJ8 / 6922) и T167 (211, 2A3, 300B, 6080, 6C33C, 6V6_AYUMI,
845, GENERIC_PENTODE) все Ayumi .inc файлы хранятся pre-converted: `^`
заменён на `**`, PWRS — на `sgn(x)*pwr(abs(x), y)`. Регрессия —
случайное возвращение HSPICE-синтаксиса в data file.

Idempotency check ловит обе формы регрессии: если повторное применение
конвертеров что-то меняет — файл содержал untranslated `^` или `PWRS(`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from adapters.outbound.spice_models.conversion import (
    convert_ayumi_to_ngspice,
    convert_pwrs_to_ngspice,
)

_AYUMI_DIR = (
    Path(__file__).resolve().parents[4]
    / 'data' / 'models' / 'tubes' / 'ayumi'
)

_PATCHED_FILES = (
    '211.inc',
    '2A3.inc',
    '300B.inc',
    '6080.inc',
    '6922.inc',
    '6C33C.inc',
    '6DJ8.inc',
    '6V6_AYUMI.inc',
    '845.inc',
    'GENERIC_PENTODE.inc',
)


@pytest.mark.parametrize('filename', _PATCHED_FILES)
def test_ayumi_model_pre_converted_to_ngspice(filename: str) -> None:
    """File contains ngspice-syntax (no HSPICE `^` или `PWRS(`)."""
    text = (_AYUMI_DIR / filename).read_text(encoding='utf-8')
    # Allow `^` в комментарной строке "ngspice-syntax: `^` уже `**`" —
    # такой маркер не парсится симулятором (line starts with `*`).
    body = '\n'.join(
        line for line in text.splitlines()
        if not line.lstrip().startswith('*')
    )
    assert '^' not in body, f'{filename}: stray `^` in SPICE body'
    assert 'PWRS(' not in body.upper(), (
        f'{filename}: stray `PWRS(` in SPICE body'
    )


@pytest.mark.parametrize('filename', _PATCHED_FILES)
def test_ayumi_model_converters_idempotent(filename: str) -> None:
    """Re-applying converters не меняет файл (файл уже в финальной форме)."""
    text = (_AYUMI_DIR / filename).read_text(encoding='utf-8')
    once = convert_pwrs_to_ngspice(convert_ayumi_to_ngspice(text))
    assert once == text, (
        f'{filename}: not idempotent — converters changed the file, '
        f'meaning untranslated `^` или `PWRS(` still present'
    )
