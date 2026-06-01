"""Unit tests for `_zero_existing_ac_sources` (T153 Phase D).

Спецификация Q7=a (Phase B.4 design): phase-margin pipeline assumes Vinj is
the only AC source. Other sources keep DC bias но AC drive zeroed before
patcher injection (иначе linear superposition contaminates loop-gain
measurement). Phase D 2026-06-01 enforced — этот sanitizer применяется
автоматически в `measure_phase_margin` use case до strategy.prepare().
"""

from __future__ import annotations

from application.measure_phase_margin import (
    _zero_ac_in_one_source_line,
    _zero_existing_ac_sources,
)


def test_zeroes_voltage_source_ac_magnitude() -> None:
    netlist = 'V_in vin 0 DC 0 AC 1\n.end\n'
    expected = 'V_in vin 0 DC 0 AC 0\n.end\n'
    assert _zero_existing_ac_sources(netlist) == expected


def test_zeroes_current_source_ac_magnitude() -> None:
    netlist = 'I_drive base 0 AC 2.5\n.end\n'
    expected = 'I_drive base 0 AC 0\n.end\n'
    assert _zero_existing_ac_sources(netlist) == expected


def test_preserves_dc_bias_and_ac_phase() -> None:
    netlist = 'V_in vin 0 DC 12 AC 1.5 45\n.end\n'
    expected = 'V_in vin 0 DC 12 AC 0 45\n.end\n'
    assert _zero_existing_ac_sources(netlist) == expected


def test_preserves_transient_function_alongside_ac() -> None:
    netlist = 'V_in vin 0 DC 0 AC 1 SIN(0 1 1k)\n.end\n'
    expected = 'V_in vin 0 DC 0 AC 0 SIN(0 1 1k)\n.end\n'
    assert _zero_existing_ac_sources(netlist) == expected


def test_zeroes_multiple_top_level_sources() -> None:
    netlist = (
        'V_in vin 0 DC 0 AC 1\n'
        'V_BB Bplus 0 DC 250\n'
        'I_bias base 0 AC 0.5\n'
        '.end\n'
    )
    expected = (
        'V_in vin 0 DC 0 AC 0\n'
        'V_BB Bplus 0 DC 250\n'
        'I_bias base 0 AC 0\n'
        '.end\n'
    )
    assert _zero_existing_ac_sources(netlist) == expected


def test_leaves_sources_without_ac_clause_unchanged() -> None:
    netlist = 'V_BB Bplus 0 DC 250\n.end\n'
    assert _zero_existing_ac_sources(netlist) == netlist


def test_leaves_comments_directives_and_blanks_unchanged() -> None:
    netlist = (
        '* header comment\n'
        '\n'
        '.title TestNetlist\n'
        '.include foo.lib\n'
        'V_in vin 0 AC 1\n'
        '.end\n'
    )
    expected = (
        '* header comment\n'
        '\n'
        '.title TestNetlist\n'
        '.include foo.lib\n'
        'V_in vin 0 AC 0\n'
        '.end\n'
    )
    assert _zero_existing_ac_sources(netlist) == expected


def test_does_not_touch_subckt_internals() -> None:
    netlist = (
        'V_in vin 0 DC 0 AC 1\n'
        '.SUBCKT OPAMP INP INN OUT\n'
        'V_inside_subckt n1 n2 AC 9.9\n'
        '.ENDS OPAMP\n'
        'V_BB Bplus 0 DC 250\n'
        '.end\n'
    )
    expected = (
        'V_in vin 0 DC 0 AC 0\n'
        '.SUBCKT OPAMP INP INN OUT\n'
        'V_inside_subckt n1 n2 AC 9.9\n'
        '.ENDS OPAMP\n'
        'V_BB Bplus 0 DC 250\n'
        '.end\n'
    )
    assert _zero_existing_ac_sources(netlist) == expected


def test_preserves_inline_comment_after_source_line() -> None:
    netlist = 'V_in vin 0 AC 1  ; KiCad export default\n.end\n'
    expected = 'V_in vin 0 AC 0  ; KiCad export default\n.end\n'
    assert _zero_existing_ac_sources(netlist) == expected


def test_does_not_zero_ac_substring_inside_inline_comment() -> None:
    netlist = 'V_BB Bplus 0 DC 250 $ note: AC 9.9 should NOT be touched\n.end\n'
    assert _zero_existing_ac_sources(netlist) == netlist


def test_case_insensitive_ac_keyword() -> None:
    netlist = 'V_in vin 0 ac 1\n.end\n'
    expected = 'V_in vin 0 ac 0\n.end\n'
    assert _zero_existing_ac_sources(netlist) == expected


def test_idempotent_on_already_zeroed_netlist() -> None:
    netlist = 'V_in vin 0 DC 0 AC 0\n.end\n'
    once = _zero_existing_ac_sources(netlist)
    twice = _zero_existing_ac_sources(once)
    assert once == netlist
    assert twice == netlist


def test_leaves_resistor_and_other_components_unchanged() -> None:
    netlist = (
        'R_load /vout 0 1Meg\n'
        'C_in input grid1 100n\n'
        'X1 plate grid cath 6N1P\n'
        '.end\n'
    )
    assert _zero_existing_ac_sources(netlist) == netlist


def test_zero_ac_in_one_source_line_preserves_leading_whitespace() -> None:
    line = '    V_in vin 0 AC 1\n'
    expected = '    V_in vin 0 AC 0\n'
    assert _zero_ac_in_one_source_line(line) == expected
