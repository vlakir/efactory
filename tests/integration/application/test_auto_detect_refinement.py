"""T164 — auto-detect heuristic refinement (multi-loop tube NFB + KiCad ordering).

Two failure modes from T153 Phase C.3 + Phase D smoke:

1. **Multi-loop tube NFB.** `score_break_candidates` на NFB SE tube amp
   находит ~72 feedback cycles. Прежнее scoring weighted forward vs
   feedback ratio uniformly → top candidate `(sec_b, R_load)` (load
   junction, не feedback). True canonical break `(sec_a, C_fb)` ranked
   below load chord. T164 fix: multi-active boost — cycles passing
   through more distinct active elements (global outer NFB) get
   confidence boost, pushing 3-active cycle `(X1, X2, X3, C_fb, R_fb,
   R_p1)` (canonical) above 2-active load chord.

2. **KiCad-export element ordering.** Same op-amp inverting topology
   parsed from inline netlist gives correct `(vout, R_fb)`, но
   parsed from KiCad-export with active subckt (XU1) listed FIRST
   in netlist gives wrong `(in_neg, R_fb)`. Root cause — DFS walk
   direction depends on element-iteration order, и `_pick_break_edge`
   prev-first preference picks net_path[0] vs net_path[1] differently.
   T164 fix: stimulus-distance ranking — candidates ranked by BFS
   distance from V/I source через passive edges (output-side wins
   over input-side independently of walk direction).

Tests written PRE-implementation (TDD red phase). Pass after T164
implementation in src/domain/netlist_graph.py + src/application/
detect_feedback_break_node.py.
"""

from __future__ import annotations

import pytest

from application.detect_feedback_break_node import detect_feedback_break_node
from domain.phase_margin import AutoDetectConfidenceTooLowError


# ============================== NFB SE tube — multi-loop boost ============


_NFB_SE_NETLIST = (
    '* NFB SE tube amp (T164 inline mirror of data/templates/nfb-se-amp/)\n'
    'V_BB Bplus 0 DC 250\n'
    'V_in input 0 DC 0 AC 1\n'
    'C_in input grid1 100n\n'
    'R_g1 grid1 0 1Meg\n'
    'X1 plate1 grid1 cath1 6N1P\n'
    'R_p1 Bplus plate1 100k\n'
    'R_k1 cath1 0 1.5k\n'
    'C_c plate1 grid2 22n\n'
    'R_g2 grid2 0 470k\n'
    'X2 plate2 Bplus grid2 cath2 6P14P\n'
    'R_k2 cath2 0 130\n'
    'C_k2 cath2 0 100u\n'
    'X3 plate2 Bplus sec_a sec_b OPT_SE_5K_8\n'
    'R_load sec_a sec_b 8\n'
    'C_fb sec_a fb_mid 10u\n'
    'R_fb fb_mid cath1 4.7k\n'
    '.end\n'
)


def test_nfb_se_auto_detect_picks_canonical_sec_a_c_fb() -> None:
    """T164 acceptance — multi-active boost picks global outer NFB.

    Before T164: `(sec_b, R_load)` conf=0.45 — load chord (X3+R_load
    parallel between sec_a/sec_b), NOT feedback. After T164:
    `(sec_a, C_fb)` — OPT secondary → feedback chain junction. The
    boost favors cycles passing through more distinct active elements
    (global outer loop X1→X2→X3→C_fb→R_fb has 3 actives; local chord
    X3+R_load has 1 active).

    Threshold 0.7 — see T164 BACKLOG acceptance. Default 0.8 не
    обязателен для tube NFB (multi-cycle topology inherently lowers
    confidence vs single-active op-amp).
    """
    info = detect_feedback_break_node(
        netlist_text=_NFB_SE_NETLIST,
        confidence_threshold=0.7,
    )
    assert info.chosen_node == 'sec_a', (
        f'expected sec_a (OPT secondary feedback junction), '
        f'got {info.chosen_node!r}; alternatives: {info.alternatives[:3]}'
    )
    assert info.chosen_element_ref == 'C_fb', (
        f'expected C_fb (DC-block feedback cap), '
        f'got {info.chosen_element_ref!r}'
    )
    assert info.confidence >= 0.7, (
        f'expected confidence >= 0.7, got {info.confidence:.3f}'
    )


def test_nfb_se_auto_detect_default_threshold_still_too_low() -> None:
    """Default threshold 0.8 на tube NFB всё ещё raises — multi-active
    boost поднимает до ~0.7, не до 0.8.

    Tube NFB topology fundamentally multi-cycle (local cathode
    degeneration + global NFB + parasitic ground cycles → 72 cycles).
    Boost закрывает gap до ~0.7; пользователь сознательно понижает
    threshold до 0.7 на tube circuits (или передаёт break explicitly).
    """
    with pytest.raises(AutoDetectConfidenceTooLowError):
        detect_feedback_break_node(netlist_text=_NFB_SE_NETLIST)


# ============================== KiCad-ordering invariance =================


# Inline-style ordering (passives first, V_in last) — C.1 reference style.
_OPAMP_INV_PASSIVES_FIRST = (
    '* op-amp inverting — passives first (inline reference style)\n'
    'R_in vin in_neg 1k\n'
    'R_fb in_neg vout 10k\n'
    'R_load vout 0 1Meg\n'
    'XU1 0 in_neg vout GENERIC_OPAMP_2POLE\n'
    'V_in vin 0 DC 0 AC 1\n'
    '.end\n'
)

# KiCad-export style ordering (active subckt FIRST, passives after).
# Reproduces T153 Phase D Smoke S3 actual netlist structure where
# `_pick_break_edge` prev-first preference selected (in_neg, R_fb).
_OPAMP_INV_XU1_FIRST = (
    '* op-amp inverting — XU1 first (KiCad-export style)\n'
    'XU1 0 in_neg vout GENERIC_OPAMP_2POLE\n'
    'R_in vin in_neg 1k\n'
    'R_fb in_neg vout 10k\n'
    'R_load vout 0 1Meg\n'
    'V_in vin 0 DC 0 AC 1\n'
    '.end\n'
)


def test_opamp_auto_detect_picks_vout_when_passives_first() -> None:
    """Baseline — inline ordering gives canonical `(vout, R_fb)`.

    C.1.5 calibration (test_measure_phase_margin_calibration.py)
    already covers this; here we duplicate as anchor for the next
    invariance test.
    """
    info = detect_feedback_break_node(
        netlist_text=_OPAMP_INV_PASSIVES_FIRST,
        confidence_threshold=0.3,
    )
    assert info.chosen_node == 'vout'
    assert info.chosen_element_ref == 'R_fb'


def test_opamp_auto_detect_invariant_to_element_ordering() -> None:
    """T164 acceptance — XU1-first ordering still picks `(vout, R_fb)`.

    Before T164: passives-first → `(vout, R_fb)` ✓; XU1-first →
    `(in_neg, R_fb)` ✗. DFS walks the same 2-element cycle [XU1, R_fb]
    in opposite direction depending on which element registers in
    adjacency map first; current `_pick_break_edge` picks `net_path[0]`
    vs `net_path[1]` accordingly.

    After T164: stimulus-distance ranking discriminates by BFS
    distance from V/I source — `vout` (2 passive hops from V_in:
    vin→R_in→in_neg→R_fb→vout) wins over `in_neg` (1 hop) regardless
    of walk direction. Output-side break is physical-correct for
    Middlebrook V single-injection (low-Z driver convention).
    """
    info = detect_feedback_break_node(
        netlist_text=_OPAMP_INV_XU1_FIRST,
        confidence_threshold=0.3,
    )
    assert info.chosen_node == 'vout', (
        f'expected vout (op-amp output, low-Z driver side), '
        f'got {info.chosen_node!r}; alternatives: {info.alternatives[:3]}'
    )
    assert info.chosen_element_ref == 'R_fb'


# KiCad-export with leading `/` on local labels (matches the actual
# output of `kicad-cli sch export netlist` for unhierarchical labels).
_OPAMP_INV_KICAD_SLASH = (
    '* op-amp inverting — KiCad export (XU1 first + leading / on labels)\n'
    'XU1 GND /in_neg /vout GENERIC_OPAMP_2POLE\n'
    'R_in /vin /in_neg 1k\n'
    'R_fb /in_neg /vout 10k\n'
    'R_load /vout GND 1Meg\n'
    'V_in /vin 0 DC 0 AC 1\n'
    '.end\n'
)


def test_opamp_auto_detect_kicad_export_picks_slash_vout() -> None:
    """T164 acceptance — real KiCad-export format gives `(/vout, R_fb)`.

    Phase D Smoke S3 reproducer: leading `/` on local labels + XU1
    listed first in netlist (KiCad's typical emission order).
    Stimulus-distance fix preserves node names AS-IS (no `/`-stripping
    — that would be a workaround masking the actual ordering bug).
    """
    info = detect_feedback_break_node(
        netlist_text=_OPAMP_INV_KICAD_SLASH,
        confidence_threshold=0.3,
    )
    assert info.chosen_node == '/vout', (
        f'expected /vout (KiCad-export label), '
        f'got {info.chosen_node!r}; alternatives: {info.alternatives[:3]}'
    )
    assert info.chosen_element_ref == 'R_fb'
