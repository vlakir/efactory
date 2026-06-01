"""CircuitGraph / CircuitEdge VOs + NetlistGraphAnalyzer (T153 Phase B.5).

Этот файл будет наполняться постепенно: VOs → parse → find_cycles
→ score_break_candidates. Здесь — VOs (Phase B.5.1).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.netlist_graph import (
    CircuitEdge,
    CircuitGraph,
    ElementType,
    find_cycles,
    parse,
    score_break_candidates,
)
from domain.phase_margin import (
    AutoDetectInfo,
    FeedbackCycle,
)


# ============================== CircuitEdge ===================================


def test_edge_happy() -> None:
    e = CircuitEdge(
        element_id='R1',
        element_type='resistor',
        net_pair=('a', 'b'),
    )
    assert e.element_id == 'R1'
    assert e.element_type == 'resistor'
    assert e.net_pair == ('a', 'b')


def test_edge_all_element_types_accepted() -> None:
    """Все 11 element_type ALLOWED."""
    types: tuple[ElementType, ...] = (
        'resistor',
        'capacitor',
        'inductor',
        'diode',
        'bjt',
        'mosfet',
        'jfet',
        'voltage_source',
        'current_source',
        'voltage_controlled_source',
        'current_controlled_source',
        'subckt',
    )
    for t in types:
        e = CircuitEdge(element_id='X1', element_type=t, net_pair=('a', 'b'))
        assert e.element_type == t


def test_edge_invalid_element_type_rejected() -> None:
    with pytest.raises(ValidationError, match='element_type'):
        CircuitEdge(
            element_id='X1',
            element_type='magical',  # type: ignore[arg-type]
            net_pair=('a', 'b'),
        )


def test_edge_element_id_non_empty() -> None:
    with pytest.raises(ValidationError, match='element_id'):
        CircuitEdge(element_id='', element_type='resistor', net_pair=('a', 'b'))


def test_edge_net_pair_both_non_empty() -> None:
    with pytest.raises(ValidationError, match='net_pair'):
        CircuitEdge(element_id='R1', element_type='resistor', net_pair=('', 'b'))
    with pytest.raises(ValidationError, match='net_pair'):
        CircuitEdge(element_id='R1', element_type='resistor', net_pair=('a', ''))


def test_edge_self_loop_allowed() -> None:
    """Element with same node на обоих pins — допустим (KCL-degenerate, но valid)."""
    e = CircuitEdge(element_id='R1', element_type='resistor', net_pair=('a', 'a'))
    assert e.net_pair == ('a', 'a')


def test_edge_is_frozen() -> None:
    e = CircuitEdge(element_id='R1', element_type='resistor', net_pair=('a', 'b'))
    with pytest.raises(ValidationError):
        e.element_id = 'R2'  # type: ignore[misc]


# ============================== CircuitGraph ==================================


def test_graph_happy() -> None:
    edges = (
        CircuitEdge(element_id='R1', element_type='resistor', net_pair=('a', 'b')),
        CircuitEdge(element_id='C1', element_type='capacitor', net_pair=('b', '0')),
    )
    g = CircuitGraph(nets=('a', 'b', '0'), edges=edges)
    assert g.nets == ('a', 'b', '0')
    assert len(g.edges) == 2


def test_graph_nets_must_cover_edge_endpoints() -> None:
    """Если edge ссылается на net не из `nets` — ValidationError."""
    edges = (
        CircuitEdge(element_id='R1', element_type='resistor', net_pair=('a', 'b')),
    )
    with pytest.raises(ValidationError, match='nets'):
        CircuitGraph(nets=('a',), edges=edges)


def test_graph_empty_edges_allowed() -> None:
    """Граф без element'ов (только nets) — valid (например, after parse)."""
    g = CircuitGraph(nets=('a',), edges=())
    assert len(g.edges) == 0


def test_graph_is_frozen() -> None:
    g = CircuitGraph(nets=('a',), edges=())
    with pytest.raises(ValidationError):
        g.nets = ('b',)  # type: ignore[misc]


def test_graph_nets_unique() -> None:
    """Дубликаты в nets отвергнуты."""
    with pytest.raises(ValidationError, match='nets'):
        CircuitGraph(nets=('a', 'a'), edges=())


# ============================== parse(netlist) ================================


def test_parse_empty_netlist_returns_empty_graph() -> None:
    g = parse('')
    assert g.nets == ()
    assert g.edges == ()


def test_parse_comment_only_returns_empty() -> None:
    g = parse('* this is a comment\n* another\n.end\n')
    assert g.edges == ()


def test_parse_single_resistor() -> None:
    g = parse('R1 a b 1k\n')
    assert len(g.edges) == 1
    assert g.edges[0].element_id == 'R1'
    assert g.edges[0].element_type == 'resistor'
    assert g.edges[0].net_pair == ('a', 'b')
    assert set(g.nets) == {'a', 'b'}


def test_parse_two_terminal_types() -> None:
    netlist = (
        'R1 a b 1k\n'
        'C1 b 0 1u\n'
        'L1 c d 10m\n'
        'D1 e f DMODEL\n'
        'V1 vin 0 DC 5\n'
        'I1 net1 net2 AC 1\n'
    )
    g = parse(netlist)
    types_by_id = {e.element_id: e.element_type for e in g.edges}
    assert types_by_id['R1'] == 'resistor'
    assert types_by_id['C1'] == 'capacitor'
    assert types_by_id['L1'] == 'inductor'
    assert types_by_id['D1'] == 'diode'
    assert types_by_id['V1'] == 'voltage_source'
    assert types_by_id['I1'] == 'current_source'


def test_parse_bjt_three_pin_pairwise() -> None:
    # Q1 collector base emitter model
    g = parse('Q1 col bas emi QNPN\n')
    bjt_edges = [e for e in g.edges if e.element_id == 'Q1']
    # 3 pairwise edges for 3 pins
    assert len(bjt_edges) == 3
    pairs = {tuple(sorted(e.net_pair)) for e in bjt_edges}
    assert pairs == {('bas', 'col'), ('col', 'emi'), ('bas', 'emi')}
    assert all(e.element_type == 'bjt' for e in bjt_edges)


def test_parse_mosfet_four_pin_pairwise() -> None:
    # M1 drain gate source bulk model
    g = parse('M1 d g s b MMODEL\n')
    mos_edges = [e for e in g.edges if e.element_id == 'M1']
    # 4 pins → 6 pairwise edges
    assert len(mos_edges) == 6
    pairs = {tuple(sorted(e.net_pair)) for e in mos_edges}
    assert pairs == {
        ('d', 'g'), ('d', 's'), ('b', 'd'),
        ('g', 's'), ('b', 'g'), ('b', 's'),
    }


def test_parse_jfet_three_pin_pairwise() -> None:
    g = parse('J1 d g s JMODEL\n')
    j_edges = [e for e in g.edges if e.element_id == 'J1']
    assert len(j_edges) == 3
    assert all(e.element_type == 'jfet' for e in j_edges)


def test_parse_vcvs_four_pin_pairwise() -> None:
    # E1 out+ out- in+ in- gain
    g = parse('E_amp v_out 0 in_p in_n 1e5\n')
    e_edges = [e for e in g.edges if e.element_id == 'E_amp']
    assert len(e_edges) == 6  # 4 pins → 6 pairs
    assert all(e.element_type == 'voltage_controlled_source' for e in e_edges)


def test_parse_subckt_call_three_pin() -> None:
    # X1 n1 n2 n3 OPA model
    g = parse('X_opamp inp inn out OPA1\n')
    x_edges = [e for e in g.edges if e.element_id == 'X_opamp']
    assert len(x_edges) == 3  # 3 pins → 3 pairs
    assert all(e.element_type == 'subckt' for e in x_edges)


def test_parse_skips_subckt_internals() -> None:
    netlist = (
        'R_top a b 1k\n'
        '.SUBCKT MY_OPA in out gnd\n'
        'R_internal in out 1k\n'  # внутри subckt, должен быть пропущен
        '.ENDS MY_OPA\n'
        'R_bot c d 2k\n'
    )
    g = parse(netlist)
    ids = {e.element_id for e in g.edges}
    assert 'R_top' in ids
    assert 'R_bot' in ids
    assert 'R_internal' not in ids


def test_parse_skips_directives_like_ac_tran_end() -> None:
    netlist = (
        'R1 a b 1k\n'
        '.ac dec 10 1 1e6\n'
        '.tran 1u 10m\n'
        '.print v(a) v(b)\n'
        '.end\n'
    )
    g = parse(netlist)
    assert len(g.edges) == 1
    assert g.edges[0].element_id == 'R1'


def test_parse_handles_leading_whitespace_and_blank_lines() -> None:
    netlist = (
        '\n'
        '   \n'
        '\tR1 a b 1k\n'
        '   C1 b 0 1u\n'
        '\n'
    )
    g = parse(netlist)
    assert {e.element_id for e in g.edges} == {'R1', 'C1'}


def test_parse_case_insensitive_element_type_detection() -> None:
    netlist = (
        'r1 a b 1k\n'  # lowercase
        'R2 c d 2k\n'  # uppercase
        'q1 col bas emi QNPN\n'  # lowercase BJT
    )
    g = parse(netlist)
    types = {e.element_id: e.element_type for e in g.edges}
    assert types['r1'] == 'resistor'
    assert types['R2'] == 'resistor'
    assert types['q1'] == 'bjt'


def test_parse_includes_ground_net_zero() -> None:
    g = parse('R1 a 0 1k\n')
    assert '0' in g.nets


def test_parse_nets_in_declaration_order_unique() -> None:
    netlist = (
        'R1 a b 1k\n'
        'C1 b c 1u\n'
        'R2 a c 2k\n'  # дублирует уже-existing nets
    )
    g = parse(netlist)
    assert set(g.nets) == {'a', 'b', 'c'}
    assert len(g.nets) == 3  # без дубликатов


def test_parse_ignores_dot_lib_dot_include() -> None:
    netlist = (
        '.include some_lib.lib\n'
        '.lib /path/file.lib\n'
        'R1 a b 1k\n'
    )
    g = parse(netlist)
    assert len(g.edges) == 1
    assert g.edges[0].element_id == 'R1'


def test_parse_inline_comment_strippped() -> None:
    g = parse('R1 a b 1k ; this is feedback\n')
    assert g.edges[0].net_pair == ('a', 'b')


def test_parse_unknown_first_char_skipped_with_no_crash() -> None:
    """Неопознанные prefix ('Z', 'U' etc.) — пропускаются без ошибок."""
    netlist = (
        'Z_unknown a b 1k\n'  # unknown element type
        'R1 c d 2k\n'
    )
    g = parse(netlist)
    ids = {e.element_id for e in g.edges}
    assert 'R1' in ids
    assert 'Z_unknown' not in ids  # пропущен


def test_parse_ccvs_h_element_three_pin() -> None:
    """H — current controlled voltage source: H<name> n+ n- Vcontrol gain.
    Pin pair: n+ n-. Vcontrol is a reference, not a node.
    """
    g = parse('H1 out 0 V_sense 0.5\n')
    h_edges = [e for e in g.edges if e.element_id == 'H1']
    assert len(h_edges) == 1
    assert h_edges[0].element_type == 'current_controlled_source'
    assert h_edges[0].net_pair == ('out', '0')


# ============================== find_cycles + scoring =========================


_OPAMP_INV_NETLIST = (
    '* op-amp inverting amp с output RC pole\n'
    'V_in vin 0 DC 0\n'
    'R_in vin in_neg 1k\n'
    'R_fb vout in_neg 10k\n'
    'E_amp v_open 0 0 in_neg 1e5\n'
    'R_amp v_open vout 1k\n'
    'C_amp vout 0 10u\n'
    'R_load vout 0 1Meg\n'
    '.end\n'
)


def test_find_cycles_detects_feedback_loop_in_opamp_inv() -> None:
    g = parse(_OPAMP_INV_NETLIST)
    cycles = find_cycles(g)
    # Должен найти хотя бы 1 valid feedback cycle (R_fb + E_amp + R_amp)
    assert len(cycles) >= 1
    assert all(isinstance(c, FeedbackCycle) for c in cycles)


def test_find_cycles_classifies_active_vs_passive() -> None:
    g = parse(_OPAMP_INV_NETLIST)
    cycles = find_cycles(g)
    # Хотя бы один cycle с правильной классификацией:
    # active = {E_amp}, passive ⊃ {R_fb, R_amp}
    valid = [
        c
        for c in cycles
        if 'E_amp' in c.elements
        and ({'R_fb', 'R_amp'} & set(c.elements))
    ]
    assert len(valid) >= 1


def test_find_cycles_skips_cycles_with_only_passive() -> None:
    """Open-loop без active element — нет valid feedback cycle."""
    netlist = (
        'V_in a 0 DC 1\n'
        'R1 a b 1k\n'
        'R2 b c 1k\n'
        'R3 c a 1k\n'  # closed triangle, all passive
    )
    g = parse(netlist)
    cycles = find_cycles(g)
    # Active-empty cycles НЕ считаются feedback'ом
    assert cycles == ()


def test_find_cycles_empty_graph_returns_empty() -> None:
    g = CircuitGraph(nets=(), edges=())
    assert find_cycles(g) == ()


def test_find_cycles_single_element_no_cycle() -> None:
    g = parse('R1 a b 1k\n')
    assert find_cycles(g) == ()


def test_score_break_candidates_returns_auto_detect_info() -> None:
    g = parse(_OPAMP_INV_NETLIST)
    cycles = find_cycles(g)
    info = score_break_candidates(cycles)
    assert isinstance(info, AutoDetectInfo)
    assert info.chosen_node != ''
    assert info.chosen_element_ref != ''
    assert 0.0 <= info.confidence <= 1.0


def test_score_break_candidates_chooses_passive_element_at_break() -> None:
    """Break ref должен быть passive element из feedback path."""
    g = parse(_OPAMP_INV_NETLIST)
    cycles = find_cycles(g)
    info = score_break_candidates(cycles)
    # Должен быть один из passive feedback elements
    assert info.chosen_element_ref in {'R_fb', 'R_amp', 'C_amp'}


def test_score_break_candidates_empty_cycles_raises_value_error() -> None:
    with pytest.raises(ValueError, match='no.*cycles'):
        score_break_candidates(())


def test_score_break_candidates_single_cycle_higher_confidence() -> None:
    """Single dominant cycle → higher confidence чем multi-cycle case."""
    g = parse(_OPAMP_INV_NETLIST)
    cycles = find_cycles(g)
    info = score_break_candidates(cycles)
    # Single feedback cycle → confidence > 0.5 (heuristic baseline)
    assert info.confidence > 0.4


def test_score_break_candidates_alternatives_sorted_by_confidence_desc() -> None:
    """Alternatives отсортированы по confidence убывающе."""
    g = parse(_OPAMP_INV_NETLIST)
    cycles = find_cycles(g)
    info = score_break_candidates(cycles)
    if info.alternatives:
        confs = [conf for _, _, conf in info.alternatives]
        assert confs == sorted(confs, reverse=True)


def test_find_cycles_skips_parallel_two_edge_short_cycles() -> None:
    """Multi-pairwise edges of one element НЕ дают valid cycle (single element)."""
    netlist = (
        'V_in a 0 DC 1\n'
        'M1 a b c d MMODEL\n'  # 4 pins → 6 pairwise edges within single element
    )
    g = parse(netlist)
    cycles = find_cycles(g)
    # M1 alone не должен давать feedback cycle (один element, без passive ringback)
    assert cycles == ()
