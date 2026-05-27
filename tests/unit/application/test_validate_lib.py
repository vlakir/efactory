"""Unit tests для SPICE-models static validator (T146).

Floating-node detection в `.SUBCKT` блоках. Heuristic-based parser
для типичных SPICE elements (R/L/C/V/I/D/K + X-subckt skip).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from application.validate_lib import (
    FloatingNodeReport,
    LibValidationReport,
    validate_lib,
)


def _write_lib(tmp_path: Path, body: str) -> Path:
    path = tmp_path / 'test.lib'
    path.write_text(body, encoding='utf-8')
    return path


# ────────── happy paths: valid libs ──────────


def test_valid_simple_rc_subckt(tmp_path: Path) -> None:
    """RC: каждая нода (включая external) touched ≥2 раз."""
    body = (
        '.SUBCKT RC_NET in out\n'
        'R1 in out 1k\n'
        'C1 out 0 1u\n'
        '.ENDS RC_NET\n'
    )
    path = _write_lib(tmp_path, body)
    report = validate_lib(path)
    # in: SUBCKT-external + R1.left = 2x → ok
    # out: SUBCKT-external + R1.right + C1.left = 3x → ok
    # 0: C1.right = 1x ← но '0' это ground, special-case
    # Поэтому: no floating nodes.
    assert report.floating_nodes == []
    assert report.subckts_validated == 1


def test_post_t147_opt_no_floating(tmp_path: Path) -> None:
    """Post-T147 corrected OPT — Pint/Sint internal nodes touched 2x."""
    body = (
        '.SUBCKT OPT P1 P2 S1 S2\n'
        'Lp Pint P2 50\n'
        'Rp_dcr P1 Pint 200\n'
        'Ls Sint S2 0.08\n'
        'Rs_dcr S1 Sint 0.3\n'
        'K1 Lp Ls 0.9995\n'
        'Cps P1 S1 200pF\n'
        '.ENDS OPT\n'
    )
    path = _write_lib(tmp_path, body)
    report = validate_lib(path)
    # Pint: Lp + Rp_dcr = 2x; Sint: Ls + Rs_dcr = 2x → no floating.
    assert report.floating_nodes == []


# ────────── floating-node detection ──────────


def test_pre_t147_opt_detects_floating_p3_s3(tmp_path: Path) -> None:
    """Pre-T147 buggy OPT — P3 / S3 touched только 1x (floating)."""
    body = (
        '.SUBCKT OPT P1 P2 S1 S2\n'
        'Lp P1 P2 50\n'
        'Rp_dcr P1 P3 200\n'
        'Ls S1 S2 0.08\n'
        'Rs_dcr S1 S3 0.3\n'
        'K1 Lp Ls 0.9995\n'
        'Cps P1 S1 200pF\n'
        '.ENDS OPT\n'
    )
    path = _write_lib(tmp_path, body)
    report = validate_lib(path)

    floating_node_names = {f.node for f in report.floating_nodes}
    assert 'P3' in floating_node_names
    assert 'S3' in floating_node_names
    for f in report.floating_nodes:
        assert f.subckt == 'OPT'
        assert f.occurrences == 1


def test_single_resistor_dangling_node(tmp_path: Path) -> None:
    """Минимальная floating case — резистор с одной свободной нодой."""
    body = (
        '.SUBCKT BAD a b\n'
        'R1 a dangling 1k\n'  # dangling — internal, touched 1x → floating
        'R2 b 0 1k\n'
        '.ENDS BAD\n'
    )
    path = _write_lib(tmp_path, body)
    report = validate_lib(path)
    floating = {f.node for f in report.floating_nodes}
    assert 'dangling' in floating
    # a и b — external pins, touched внутри 1x + 1x external = 2x → ok.


# ────────── ground special-case ──────────


def test_ground_node_is_not_floating(tmp_path: Path) -> None:
    """`0` / `GND` — ground, всегда «connected» концептуально."""
    body = (
        '.SUBCKT FILT in out\n'
        'C1 in 0 1u\n'  # 0 here = ground, single occurrence — not floating
        'R1 in out 1k\n'
        '.ENDS FILT\n'
    )
    path = _write_lib(tmp_path, body)
    report = validate_lib(path)
    assert all(f.node not in ('0', 'GND') for f in report.floating_nodes)


# ────────── elements coverage ──────────


def test_inductor_diode_nodes_counted(tmp_path: Path) -> None:
    body = (
        '.SUBCKT MIX a b\n'
        'L1 a internal_l 1mH\n'  # internal_l touched 1x → floating
        'D1 b 0 DMODEL\n'
        '.ENDS MIX\n'
    )
    path = _write_lib(tmp_path, body)
    report = validate_lib(path)
    floating = {f.node for f in report.floating_nodes}
    assert 'internal_l' in floating


def test_bjt_three_nodes(tmp_path: Path) -> None:
    """BJT Q has 3 nodes (collector, base, emitter)."""
    body = (
        '.SUBCKT AMP in out vcc\n'
        'Q1 out in 0 NPN\n'  # все 3 ноды touched внутри + externals
        'R1 vcc out 4k\n'
        '.ENDS AMP\n'
    )
    path = _write_lib(tmp_path, body)
    report = validate_lib(path)
    assert report.floating_nodes == []


def test_mosfet_four_nodes(tmp_path: Path) -> None:
    """MOSFET M has 4 nodes (D, G, S, B)."""
    body = (
        '.SUBCKT SW in gate out\n'
        'M1 out gate in in NMOS\n'  # 4-node FET
        '.ENDS SW\n'
    )
    path = _write_lib(tmp_path, body)
    report = validate_lib(path)
    assert report.floating_nodes == []


# ────────── K (coupling) does not add nodes ──────────


def test_k_coupling_referencing_inductors_not_nodes(tmp_path: Path) -> None:
    """K-element refers to inductor names, not nodes — don't add nodes from it."""
    body = (
        '.SUBCKT XFM p1 p2 s1 s2\n'
        'Lp p1 p2 1\n'
        'Ls s1 s2 1\n'
        'K1 Lp Ls 0.99\n'
        '.ENDS XFM\n'
    )
    path = _write_lib(tmp_path, body)
    report = validate_lib(path)
    # Если бы K зачитывал Lp/Ls как nodes — они бы добавили счёт.
    # Корректное поведение: Lp/Ls — references, не nodes. Не флагуем.
    flagged = {f.node for f in report.floating_nodes}
    assert 'Lp' not in flagged
    assert 'Ls' not in flagged


# ────────── X-subckt: skip with warning ──────────


def test_x_subckt_reference_skipped(tmp_path: Path) -> None:
    """X-subckt — variable arity, не можем сказать что node, а что param.
    Skip subckt с X-references из validation."""
    body = (
        '.SUBCKT WRAPPER in out\n'
        'X1 in mid OPT_SE_5K_8\n'  # X-ref — не валидируем mid
        'R1 mid out 1k\n'
        '.ENDS WRAPPER\n'
    )
    path = _write_lib(tmp_path, body)
    report = validate_lib(path)
    assert 'WRAPPER' in report.skipped_subckts


# ────────── multiple subckts in one file ──────────


def test_multiple_subckts_each_validated_independently(tmp_path: Path) -> None:
    body = (
        '.SUBCKT GOOD a b\n'
        'R1 a b 1k\n'
        '.ENDS GOOD\n'
        '.SUBCKT BAD c d\n'
        'R2 c floating_x 1k\n'
        '.ENDS BAD\n'
    )
    path = _write_lib(tmp_path, body)
    report = validate_lib(path)
    assert report.subckts_validated == 2
    floating_subckts = {f.subckt for f in report.floating_nodes}
    assert floating_subckts == {'BAD'}


# ────────── comments and case-insensitivity ──────────


def test_comments_ignored(tmp_path: Path) -> None:
    body = (
        '* a comment .subckt FAKE in out\n'
        '.SUBCKT R_OK in out\n'
        '* another comment\n'
        'R1 in out 1k\n'
        '.ENDS R_OK\n'
    )
    path = _write_lib(tmp_path, body)
    report = validate_lib(path)
    assert report.subckts_validated == 1
    assert report.floating_nodes == []


def test_lowercase_subckt_handled(tmp_path: Path) -> None:
    body = (
        '.subckt rc in out\n'
        'r1 in out 1k\n'
        '.ends rc\n'
    )
    path = _write_lib(tmp_path, body)
    report = validate_lib(path)
    assert report.subckts_validated == 1


# ────────── error cases ──────────


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        validate_lib(tmp_path / 'nonexistent.lib')


def test_empty_file_returns_empty_report(tmp_path: Path) -> None:
    path = _write_lib(tmp_path, '')
    report = validate_lib(path)
    assert report.subckts_validated == 0
    assert report.floating_nodes == []


def test_lib_without_subckt_blocks(tmp_path: Path) -> None:
    """`.lib` may contain `.MODEL` cards без `.SUBCKT` — empty report."""
    body = (
        '.MODEL NPN BJT (IS=1e-15 BF=200)\n'
        '.MODEL DMODEL D (IS=1e-14)\n'
    )
    path = _write_lib(tmp_path, body)
    report = validate_lib(path)
    assert report.subckts_validated == 0
    assert report.floating_nodes == []


# ────────── return type contract ──────────


def test_report_is_pydantic_model(tmp_path: Path) -> None:
    body = '.SUBCKT R in out\nR1 in out 1k\n.ENDS R\n'
    path = _write_lib(tmp_path, body)
    report = validate_lib(path)
    assert isinstance(report, LibValidationReport)
    if report.floating_nodes:
        assert isinstance(report.floating_nodes[0], FloatingNodeReport)
