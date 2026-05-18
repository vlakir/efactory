"""SPICE-суффиксы для CLI: parse_spice_number (T008 Phase 4)."""

from __future__ import annotations

import pytest

from adapters.inbound.cli.spice_units import (
    SpiceNumberFormatError,
    parse_spice_number,
)


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('1', 1.0),
        ('0', 0.0),
        ('-1', -1.0),
        ('1.5', 1.5),
        ('1e3', 1000.0),
        ('1E6', 1e6),
        ('-2.5e-3', -2.5e-3),
        ('1f', 1e-15),
        ('1p', 1e-12),
        ('1n', 1e-9),
        ('1u', 1e-6),
        ('1U', 1e-6),
        ('1m', 1e-3),
        ('1.5k', 1500.0),
        ('1K', 1000.0),
        ('1Meg', 1e6),
        ('1MEG', 1e6),
        ('1meg', 1e6),
        ('2.5Meg', 2.5e6),
        ('1G', 1e9),
        ('1T', 1e12),
    ],
)
def test_parse_spice_number_known_suffixes(raw: str, expected: float) -> None:
    assert parse_spice_number(raw) == pytest.approx(expected)


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('20mA', 0.020),
        ('1kHz', 1000.0),
        ('1MegHz', 1e6),
        ('1uF', 1e-6),
        ('100nS', 100e-9),
    ],
)
def test_parse_spice_number_ignores_unit_hint_after_prefix(
    raw: str,
    expected: float,
) -> None:
    """ngspice convention: после prefix-буквы любые буквы игнорируются (unit hint)."""
    assert parse_spice_number(raw) == pytest.approx(expected)


@pytest.mark.parametrize(
    'raw',
    [
        '',
        '   ',
        'abc',
        'k1',
        '1z',
        '1xyz',
        '1m1',  # цифра после prefix не имеет смысла
    ],
)
def test_parse_spice_number_rejects_invalid(raw: str) -> None:
    with pytest.raises(SpiceNumberFormatError):
        parse_spice_number(raw)


def test_parse_spice_number_strips_whitespace() -> None:
    assert parse_spice_number('  1k  ') == 1000.0


def test_parse_spice_number_does_not_confuse_milli_with_mega() -> None:
    """Регрессия: `m` это milli, `Meg` — mega; не путать."""
    assert parse_spice_number('1m') == 1e-3
    assert parse_spice_number('1Meg') == 1e6
    assert parse_spice_number('1m') != parse_spice_number('1Meg')


def test_parse_spice_number_e_notation_not_treated_as_prefix() -> None:
    """`1e3` — научная нотация (= 1000), не `1` + suffix `e3`."""
    assert parse_spice_number('1e3') == 1000.0
    assert parse_spice_number('1.5e-6') == pytest.approx(1.5e-6)
