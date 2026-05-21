"""Netlist substitution helpers (T131 Phase C)."""

from __future__ import annotations

import pytest

from adapters.outbound.ngspice.netlist_substitution import (
    set_sin_source_amplitude,
    substitute_subckt_library,
)

_NEW_SATURABLE = (
    '.SUBCKT OPT_SE_5K_8 P1 P2 S1 S2\n'
    '* Saturable transformer (T131 Phase A).\n'
    'R_pri P1 N_a 200\n'
    '.ENDS OPT_SE_5K_8\n'
)


def test_substitute_replaces_unquoted_include() -> None:
    netlist = (
        '* sample\n'
        'X1 plate B+ S1 S2 OPT_SE_5K_8\n'
        '.include /home/v/data/models/transformers/generic/OPT_SE_5K_8.lib\n'
        'R_load S1 S2 8\n'
    )

    result = substitute_subckt_library(netlist, 'OPT_SE_5K_8', _NEW_SATURABLE)

    assert '.include' not in result
    assert '.SUBCKT OPT_SE_5K_8' in result
    assert '.ENDS OPT_SE_5K_8' in result
    assert 'X1 plate B+ S1 S2 OPT_SE_5K_8' in result  # X-instance не тронут
    assert 'R_load S1 S2 8' in result


def test_substitute_replaces_quoted_include() -> None:
    netlist = (
        '* sample\n'
        '.include "/full/path/OPT_SE_5K_8.lib"\n'
        'X1 P1 P2 S1 S2 OPT_SE_5K_8\n'
    )

    result = substitute_subckt_library(netlist, 'OPT_SE_5K_8', _NEW_SATURABLE)

    assert '.include' not in result
    assert '.SUBCKT OPT_SE_5K_8' in result


def test_substitute_replaces_lib_directive() -> None:
    netlist = (
        '* sample\n'
        '.lib OPT_SE_5K_8.lib\n'
        'X1 P1 P2 S1 S2 OPT_SE_5K_8\n'
    )

    result = substitute_subckt_library(netlist, 'OPT_SE_5K_8', _NEW_SATURABLE)

    assert '.lib' not in result
    assert '.SUBCKT OPT_SE_5K_8' in result


def test_substitute_replaces_inline_subckt_block() -> None:
    netlist = (
        '* sample\n'
        '.SUBCKT OPT_SE_5K_8 P1 P2 S1 S2\n'
        '* static linear model\n'
        'Lp P1 P2 50\n'
        'Ls S1 S2 0.08\n'
        'K1 Lp Ls 0.9995\n'
        '.ENDS OPT_SE_5K_8\n'
        'X1 P1 P2 S1 S2 OPT_SE_5K_8\n'
    )

    result = substitute_subckt_library(netlist, 'OPT_SE_5K_8', _NEW_SATURABLE)

    # Старая линейная модель удалена, новая saturable вставлена:
    assert 'Lp P1 P2 50' not in result
    assert 'R_pri P1 N_a 200' in result
    assert result.count('.SUBCKT OPT_SE_5K_8') == 1


def test_substitute_is_idempotent_when_already_inlined() -> None:
    netlist = (
        '* sample\n'
        + _NEW_SATURABLE
        + 'X1 P1 P2 S1 S2 OPT_SE_5K_8\n'
    )

    result = substitute_subckt_library(netlist, 'OPT_SE_5K_8', _NEW_SATURABLE)

    assert result.count('.SUBCKT OPT_SE_5K_8') == 1
    assert 'R_pri P1 N_a 200' in result


def test_substitute_raises_when_target_not_found() -> None:
    netlist = (
        '* sample\n'
        '.include foo.lib\n'
        'X1 P1 P2 S1 S2 UNRELATED\n'
    )

    with pytest.raises(ValueError, match='OPT_SE_5K_8'):
        substitute_subckt_library(netlist, 'OPT_SE_5K_8', _NEW_SATURABLE)


def test_substitute_raises_on_empty_target_name() -> None:
    with pytest.raises(ValueError, match='target_subckt_name'):
        substitute_subckt_library('* x', '', _NEW_SATURABLE)


# ---------- set_sin_source_amplitude ----------


def test_set_sin_amplitude_replaces_existing_sin() -> None:
    netlist = (
        '* sample\n'
        'V_in /in 0 SIN(0 0.5 100)\n'
        'R1 /in 0 1k\n'
    )

    result = set_sin_source_amplitude(
        netlist,
        source_ref='V_in',
        amplitude_peak=1.0,
        frequency_hz=1000.0,
    )

    assert 'SIN(0 1 1000)' in result
    assert 'SIN(0 0.5 100)' not in result
    assert 'R1 /in 0 1k' in result


def test_set_sin_amplitude_preserves_extra_ac_param() -> None:
    netlist = (
        '* sample\n'
        'V1 in 0 AC 1 SIN(0 0.1 50)\n'
    )

    result = set_sin_source_amplitude(
        netlist,
        source_ref='V1',
        amplitude_peak=2.5,
        frequency_hz=1000.0,
    )

    # AC 1 параметр сохранён до SIN(...)
    assert 'V1 in 0 AC 1 SIN(0 2.5 1000)' in result


def test_set_sin_amplitude_case_insensitive_ref() -> None:
    netlist = 'V_IN /in 0 SIN(0 0.5 100)\n'

    result = set_sin_source_amplitude(
        netlist,
        source_ref='v_in',
        amplitude_peak=1.0,
        frequency_hz=1000.0,
    )

    assert 'SIN(0 1 1000)' in result


def test_set_sin_amplitude_raises_when_source_not_found() -> None:
    netlist = 'R1 /in 0 1k\n'

    with pytest.raises(ValueError, match='V_in'):
        set_sin_source_amplitude(
            netlist,
            source_ref='V_in',
            amplitude_peak=1.0,
            frequency_hz=1000.0,
        )


def test_set_sin_amplitude_raises_on_negative_amplitude() -> None:
    netlist = 'V1 a 0 SIN(0 1 1k)\n'
    with pytest.raises(ValueError, match='amplitude_peak'):
        set_sin_source_amplitude(
            netlist,
            source_ref='V1',
            amplitude_peak=-1.0,
            frequency_hz=1000.0,
        )


def test_set_sin_amplitude_raises_on_non_positive_frequency() -> None:
    netlist = 'V1 a 0 SIN(0 1 1k)\n'
    with pytest.raises(ValueError, match='frequency_hz'):
        set_sin_source_amplitude(
            netlist,
            source_ref='V1',
            amplitude_peak=1.0,
            frequency_hz=0.0,
        )
