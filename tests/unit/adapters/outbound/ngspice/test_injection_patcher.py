"""Ngspice injection patcher — edge-aware topology surgery (T153 Phase B.3)."""

from __future__ import annotations

import pytest

from adapters.outbound.ngspice.injection_patcher import (
    NgspiceInjectionNetlistPatcher,
    insert_current_source,
    insert_voltage_source,
    open_break,
    short_break,
)
from ports.outbound.injection_netlist_patcher import (
    InjectionNetlistPatcher,
    NetlistPatchResult,
    ProbePair,
)

# ---------------------------------------------------------- sample netlists ----

# Op-amp inverting amp: break edge at `in_neg` via element R_fb (feedback path).
_OPAMP_INV = (
    '* op-amp inverting amplifier\n'
    'V_in vin 0 AC 1\n'
    'R_in vin in_neg 1k\n'
    'R_fb vout in_neg 10k\n'
    'X_opamp 0 in_neg vout opa1\n'
    'R_load vout 0 100k\n'
    '.end\n'
)

# NFB SE amp-flavour: break at /sec_a, edge via C_fb_block. Three elements use /sec_a.
_NFB_SE_LIKE = (
    '* nfb se amp fragment\n'
    'V_HT b_plus 0 DC 250\n'
    'L_sec_pri /plate b_plus 10\n'
    'L_sec /sec_a /sec_b 1\n'
    'R_load /sec_a /sec_b 8\n'
    'C_fb_block /sec_a /fb_cap_node 10u\n'
    'R_fb /fb_cap_node /cathode 4.7k\n'
    '.end\n'
)


# ---------------------------------------- Protocol conformance / module API ----


def test_class_satisfies_protocol() -> None:
    patcher: InjectionNetlistPatcher = NgspiceInjectionNetlistPatcher()
    assert hasattr(patcher, 'insert_voltage_source')
    assert hasattr(patcher, 'insert_current_source')
    assert hasattr(patcher, 'open_break')
    assert hasattr(patcher, 'short_break')


def test_module_returns_netlist_patch_result_with_probe_pair() -> None:
    result = insert_voltage_source(
        _OPAMP_INV,
        break_node='in_neg',
        break_element_ref='R_fb',
        source_ref='Vinj',
        ac_magnitude=1.0,
    )
    assert isinstance(result, NetlistPatchResult)
    assert isinstance(result.probe_pair, ProbePair)


# =========================================== insert_voltage_source ============


def test_voltage_renames_break_node_in_target_element_only() -> None:
    result = insert_voltage_source(
        _OPAMP_INV,
        break_node='in_neg',
        break_element_ref='R_fb',
        source_ref='Vinj',
    )
    text = result.patched_netlist
    # R_fb's pin connection was renamed
    assert 'R_fb vout in_neg__fwd 10k' in text
    # other in_neg references untouched
    assert 'R_in vin in_neg 1k' in text
    assert 'X_opamp 0 in_neg vout opa1' in text


def test_voltage_inserts_source_line_before_end_card() -> None:
    result = insert_voltage_source(
        _OPAMP_INV,
        break_node='in_neg',
        break_element_ref='R_fb',
        source_ref='Vinj',
        ac_magnitude=1.0,
    )
    text = result.patched_netlist
    # source bridges __fwd → break_node
    assert 'Vinj in_neg__fwd in_neg AC 1' in text
    # before .end (idiomatic), not after
    end_idx = text.rfind('.end')
    src_idx = text.find('Vinj')
    assert src_idx < end_idx


def test_voltage_probe_pair_uses_voltage_traces() -> None:
    result = insert_voltage_source(
        _OPAMP_INV,
        break_node='in_neg',
        break_element_ref='R_fb',
        source_ref='Vinj',
    )
    assert result.probe_pair.fwd == 'v(in_neg__fwd)'
    assert result.probe_pair.rev == 'v(in_neg)'


def test_voltage_respects_custom_ac_magnitude() -> None:
    result = insert_voltage_source(
        _OPAMP_INV,
        break_node='in_neg',
        break_element_ref='R_fb',
        source_ref='Vinj',
        ac_magnitude=0.001,
    )
    assert 'Vinj in_neg__fwd in_neg AC 0.001' in result.patched_netlist


def test_voltage_respects_custom_source_ref() -> None:
    result = insert_voltage_source(
        _OPAMP_INV,
        break_node='in_neg',
        break_element_ref='R_fb',
        source_ref='V_test_inj',
    )
    assert 'V_test_inj in_neg__fwd in_neg AC 1' in result.patched_netlist
    assert 'Vinj' not in result.patched_netlist


def test_voltage_element_ref_case_insensitive() -> None:
    result = insert_voltage_source(
        _OPAMP_INV,
        break_node='in_neg',
        break_element_ref='r_fb',  # lower-case
        source_ref='Vinj',
    )
    assert 'R_fb vout in_neg__fwd 10k' in result.patched_netlist


def test_voltage_element_ref_not_found_raises() -> None:
    with pytest.raises(ValueError, match='R_nonexistent'):
        insert_voltage_source(
            _OPAMP_INV,
            break_node='in_neg',
            break_element_ref='R_nonexistent',
            source_ref='Vinj',
        )


def test_voltage_break_node_not_in_element_line_raises() -> None:
    # R_load uses vout & 0, not in_neg
    with pytest.raises(ValueError, match='in_neg'):
        insert_voltage_source(
            _OPAMP_INV,
            break_node='in_neg',
            break_element_ref='R_load',
            source_ref='Vinj',
        )


def test_voltage_skips_subckt_internal_elements() -> None:
    netlist = (
        '* main\n'
        'X1 a b c MYAMP\n'
        '.SUBCKT MYAMP in out gnd\n'
        'R_fb out in 10k\n'  # not the target — это inside subckt
        '.ENDS MYAMP\n'
        'R_fb top_a top_b 4.7k\n'  # this is the top-level R_fb (target)
        '.end\n'
    )
    result = insert_voltage_source(
        netlist,
        break_node='top_b',
        break_element_ref='R_fb',
        source_ref='Vinj',
    )
    # внутренний subckt'овый R_fb остался нетронутым (out in)
    assert 'R_fb out in 10k' in result.patched_netlist
    # top-level R_fb переименован (top_b → top_b__fwd)
    assert 'R_fb top_a top_b__fwd 4.7k' in result.patched_netlist


def test_voltage_multiple_break_node_pins_on_same_element_all_renamed() -> None:
    # synthetic edge case: element uses break_node on two pins
    netlist = (
        '* selfloop\n'
        'R_loop net_a net_a 1k\n'
        '.end\n'
    )
    result = insert_voltage_source(
        netlist,
        break_node='net_a',
        break_element_ref='R_loop',
        source_ref='Vinj',
    )
    # both pin tokens renamed
    assert 'R_loop net_a__fwd net_a__fwd 1k' in result.patched_netlist


# =========================================== insert_current_source ===========


def test_current_renames_break_node_in_target_element_only() -> None:
    result = insert_current_source(
        _OPAMP_INV,
        break_node='in_neg',
        break_element_ref='R_fb',
        source_ref='Iinj',
    )
    text = result.patched_netlist
    assert 'R_fb vout in_neg__fwd 10k' in text
    assert 'R_in vin in_neg 1k' in text


def test_current_inserts_probe_voltage_sources_plus_current_source() -> None:
    result = insert_current_source(
        _OPAMP_INV,
        break_node='in_neg',
        break_element_ref='R_fb',
        source_ref='Iinj',
        ac_magnitude=1.0,
    )
    text = result.patched_netlist
    # two 0-V ammeter sources around __probe bus
    assert 'V_fwd_probe in_neg__fwd in_neg__probe 0' in text
    assert 'V_rev_probe in_neg in_neg__probe 0' in text
    # current source from __probe to ground (DC 0 + AC 1)
    assert 'Iinj in_neg__probe 0 DC 0 AC 1' in text


def test_current_probe_pair_uses_voltage_source_currents() -> None:
    result = insert_current_source(
        _OPAMP_INV,
        break_node='in_neg',
        break_element_ref='R_fb',
        source_ref='Iinj',
    )
    # ngspice convention: trace names lowercase regardless of netlist case
    assert result.probe_pair.fwd == 'i(v_fwd_probe)'
    assert result.probe_pair.rev == 'i(v_rev_probe)'


def test_current_respects_custom_ac_magnitude() -> None:
    result = insert_current_source(
        _OPAMP_INV,
        break_node='in_neg',
        break_element_ref='R_fb',
        source_ref='Iinj',
        ac_magnitude=0.5,
    )
    assert 'Iinj in_neg__probe 0 DC 0 AC 0.5' in result.patched_netlist


def test_current_element_ref_not_found_raises() -> None:
    with pytest.raises(ValueError, match='R_nonexistent'):
        insert_current_source(
            _OPAMP_INV,
            break_node='in_neg',
            break_element_ref='R_nonexistent',
            source_ref='Iinj',
        )


def test_current_break_node_not_in_element_line_raises() -> None:
    with pytest.raises(ValueError, match='in_neg'):
        insert_current_source(
            _OPAMP_INV,
            break_node='in_neg',
            break_element_ref='R_load',
            source_ref='Iinj',
        )


# ============================================== open_break ===============


def test_open_break_renames_node_in_target_element_only() -> None:
    result = open_break(
        _OPAMP_INV,
        break_node='in_neg',
        break_element_ref='R_fb',
    )
    text = result.patched_netlist
    assert 'R_fb vout in_neg__fwd 10k' in text
    assert 'R_in vin in_neg 1k' in text


def test_open_break_inserts_drive_source_and_pulldown() -> None:
    result = open_break(
        _OPAMP_INV,
        break_node='in_neg',
        break_element_ref='R_fb',
    )
    text = result.patched_netlist
    # drive AC voltage on __fwd against ground
    assert 'Vrr_oc_drv in_neg__fwd 0 AC 1' in text
    # 1 GOhm pulldown to keep DC op-point valid (dangling response side)
    assert 'Rrr_oc_pulldown in_neg 0 1G' in text


def test_open_break_probe_pair_uses_voltage_traces() -> None:
    result = open_break(
        _OPAMP_INV,
        break_node='in_neg',
        break_element_ref='R_fb',
    )
    assert result.probe_pair.fwd == 'v(in_neg__fwd)'
    assert result.probe_pair.rev == 'v(in_neg)'


def test_open_break_element_ref_not_found_raises() -> None:
    with pytest.raises(ValueError, match='R_nonexistent'):
        open_break(
            _OPAMP_INV,
            break_node='in_neg',
            break_element_ref='R_nonexistent',
        )


def test_open_break_break_node_not_in_element_line_raises() -> None:
    with pytest.raises(ValueError, match='in_neg'):
        open_break(
            _OPAMP_INV,
            break_node='in_neg',
            break_element_ref='R_load',
        )


# ============================================== short_break ==============


def test_short_break_renames_node_in_target_element_only() -> None:
    result = short_break(
        _OPAMP_INV,
        break_node='in_neg',
        break_element_ref='R_fb',
    )
    text = result.patched_netlist
    assert 'R_fb vout in_neg__fwd 10k' in text
    assert 'R_in vin in_neg 1k' in text


def test_short_break_inserts_voltage_drive_and_short_ammeter() -> None:
    result = short_break(
        _OPAMP_INV,
        break_node='in_neg',
        break_element_ref='R_fb',
    )
    text = result.patched_netlist
    # voltage source drives __fwd vs ground (Rosenstark SC convention,
    # adapter uses Vsrc not Isrc — ngspice не сохраняет i(I<src>) в AC)
    assert 'Vrr_sc_drv in_neg__fwd 0 AC 1' in text
    # 0V Vshort as ammeter to ground
    assert 'Vrr_sc_meas in_neg 0 0' in text


def test_short_break_respects_custom_gnd_node() -> None:
    result = short_break(
        _OPAMP_INV,
        break_node='in_neg',
        break_element_ref='R_fb',
        gnd_node='gnd_alt',
    )
    text = result.patched_netlist
    assert 'Vrr_sc_meas in_neg gnd_alt 0' in text


def test_short_break_probe_pair_uses_current_traces() -> None:
    result = short_break(
        _OPAMP_INV,
        break_node='in_neg',
        break_element_ref='R_fb',
    )
    # ngspice convention: trace names lowercase
    assert result.probe_pair.fwd == 'i(vrr_sc_drv)'
    assert result.probe_pair.rev == 'i(vrr_sc_meas)'


def test_short_break_element_ref_not_found_raises() -> None:
    with pytest.raises(ValueError, match='R_nonexistent'):
        short_break(
            _OPAMP_INV,
            break_node='in_neg',
            break_element_ref='R_nonexistent',
        )


def test_short_break_break_node_not_in_element_line_raises() -> None:
    with pytest.raises(ValueError, match='in_neg'):
        short_break(
            _OPAMP_INV,
            break_node='in_neg',
            break_element_ref='R_load',
        )


# =============== NFB-SE-amp realistic 3-pin break case ==================


def test_voltage_nfb_se_amp_three_pin_break_only_one_renamed() -> None:
    """К /sec_a подключены L_sec, R_load, C_fb_block — рез только в C_fb_block."""
    result = insert_voltage_source(
        _NFB_SE_LIKE,
        break_node='/sec_a',
        break_element_ref='C_fb_block',
        source_ref='Vinj',
    )
    text = result.patched_netlist
    # L_sec и R_load остались на /sec_a — это не загвоздка
    assert 'L_sec /sec_a /sec_b 1' in text
    assert 'R_load /sec_a /sec_b 8' in text
    # только C_fb_block ушёл на __fwd
    assert 'C_fb_block /sec_a__fwd /fb_cap_node 10u' in text
    # source bridges
    assert 'Vinj /sec_a__fwd /sec_a AC 1' in text


def test_rosenstark_short_break_on_nfb_se_amp_keeps_topology() -> None:
    result = short_break(
        _NFB_SE_LIKE,
        break_node='/sec_a',
        break_element_ref='C_fb_block',
    )
    text = result.patched_netlist
    # L_sec и R_load — на /sec_a
    assert 'L_sec /sec_a /sec_b 1' in text
    assert 'R_load /sec_a /sec_b 8' in text
    # C_fb_block — на __fwd
    assert 'C_fb_block /sec_a__fwd /fb_cap_node 10u' in text
    # voltage-drive и amм-перемычка
    assert 'Vrr_sc_drv /sec_a__fwd 0 AC 1' in text
    assert 'Vrr_sc_meas /sec_a 0 0' in text


# ============================== inline-comment preservation ==============


def test_voltage_preserves_inline_comment_after_semicolon() -> None:
    netlist = (
        '* sample\n'
        'R_fb vout in_neg 10k ; feedback resistor\n'
        '.end\n'
    )
    result = insert_voltage_source(
        netlist,
        break_node='in_neg',
        break_element_ref='R_fb',
        source_ref='Vinj',
    )
    # comment retained
    assert '; feedback resistor' in result.patched_netlist
    assert 'R_fb vout in_neg__fwd 10k' in result.patched_netlist


# ============================== no .end card edge case ==================


def test_voltage_appends_source_when_no_end_card_present() -> None:
    netlist_no_end = 'R_fb vout in_neg 10k\n'
    result = insert_voltage_source(
        netlist_no_end,
        break_node='in_neg',
        break_element_ref='R_fb',
        source_ref='Vinj',
    )
    text = result.patched_netlist
    assert 'R_fb vout in_neg__fwd 10k' in text
    assert 'Vinj in_neg__fwd in_neg AC 1' in text
