"""T107 Phase 1: structural asserts на sexp content.

Three structural tests за тремя визуальными изменениями:

* **GU50** имеет top-cap anode pin `TC` с extended length 5.08 + circle
  marker (`(center 0 13.97)`).
* **6П45С** имеет top-cap anode `TC` + 2 beam-forming plates (короткие
  толстые vertical polylines at X=±4.572 с stroke width 0.508).
* **6Н6П** — multi-unit (две unit definitions `6N6P_1_1` + `6N6P_2_1`).

Эти assert'ы — fast-fail guard от silent regression (например, если кто-
то перепишет sexp руками или удалит beam plates во время рефакторинга
visual style). Они НЕ заменяют visual GUI ack — Vladimir смотрит финал
в KiCad перед squash-merge.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_LIB_SYMBOLS_DIR = (
    _REPO_ROOT
    / 'src'
    / 'adapters'
    / 'outbound'
    / 'schematic_kicad'
    / 'lib_symbols'
)


def _load_sexp(name: str) -> str:
    path = _LIB_SYMBOLS_DIR / name
    return path.read_text(encoding='utf-8')


# ───────── GU50 ─────────

def test_gu50_has_top_cap_anode_pin() -> None:
    sexp = _load_sexp('Tubes_Soviet.GU50.sexp')
    assert '(number "TC"' in sexp, (
        'GU50 должен иметь pin number "TC" (top-cap anode), не "7"'
    )
    assert '(at 0 13.97 270)' in sexp, (
        'GU50 anode pin должен быть at (0, 13.97, 270) — extended top-cap '
        'position на 5.08 mm выше обычной anode (был at 0, 11.43)'
    )


def test_gu50_has_top_cap_circle_marker() -> None:
    sexp = _load_sexp('Tubes_Soviet.GU50.sexp')
    assert '(center 0 13.97)' in sexp, (
        'GU50 должен иметь filled circle marker at top-cap pin tip '
        '(center 0 13.97), обозначающий top-cap contact'
    )


def test_gu50_pin_numbers_match_datasheet() -> None:
    sexp = _load_sexp('Tubes_Soviet.GU50.sexp')
    assert '(number "2"' in sexp, 'GU50 G1 должен быть pin 2'
    assert '(number "3"' in sexp, 'GU50 K_G3 должен быть pin 3'
    assert '(number "5"' in sexp, 'GU50 G2 должен быть pin 5 (был 9)'
    assert '(number "9"' not in sexp, (
        'GU50 pin 9 от EL84 source должен быть удалён (Phase 0 artifact)'
    )


# ───────── 6П45С (6P45S) ─────────

def test_6p45s_has_top_cap_anode_pin() -> None:
    sexp = _load_sexp('Tubes_Soviet.6P45S.sexp')
    assert '(number "TC"' in sexp, (
        '6П45С должен иметь pin number "TC" (top-cap anode)'
    )
    assert '(at 0 13.97 270)' in sexp


def test_6p45s_has_beam_forming_plates() -> None:
    sexp = _load_sexp('Tubes_Soviet.6P45S.sexp')
    # Two thick vertical polylines at X=±4.572, Y from -2.54 to 1.27.
    # Distinguishing feature beam tetrode vs pentode — отсутствуют у GU50.
    assert '(xy -4.572 -2.54) (xy -4.572 1.27)' in sexp, (
        '6П45С должен иметь левую beam-forming plate '
        '(thick vertical at X=-4.572)'
    )
    assert '(xy 4.572 -2.54) (xy 4.572 1.27)' in sexp, (
        '6П45С должен иметь правую beam-forming plate '
        '(thick vertical at X=+4.572)'
    )
    # Stroke width 0.508 — толще обычных grid lines 0.2032; visual marker.
    assert '(width 0.508)' in sexp, (
        '6П45С beam plates должны быть stroke width 0.508 '
        '(толще обычных grid wires 0.2032)'
    )


def test_6p45s_distinct_pin_numbers_from_gu50() -> None:
    gu50 = _load_sexp('Tubes_Soviet.GU50.sexp')
    p45s = _load_sexp('Tubes_Soviet.6P45S.sexp')
    # G1: GU50=2, 6P45S=7; G2: GU50=5, 6P45S=6.
    assert '(number "7"' in p45s, '6П45С G1 должен быть pin 7'
    assert '(number "6"' in p45s, '6П45С G2 должен быть pin 6'
    assert '(number "7"' not in gu50, 'GU50 не должна иметь pin 7'
    assert '(number "6"' not in gu50, 'GU50 не должна иметь pin 6'


# ───────── 6Н6П (6N6P) ─────────

def test_6n6p_is_multi_unit() -> None:
    sexp = _load_sexp('Tubes_Soviet.6N6P.sexp')
    assert '(symbol "6N6P_1_1"' in sexp, (
        '6Н6П должен иметь unit 1 sub-symbol "6N6P_1_1"'
    )
    assert '(symbol "6N6P_2_1"' in sexp, (
        '6Н6П должен иметь unit 2 sub-symbol "6N6P_2_1" '
        '(multi-unit — две половинки по советскому ГОСТу)'
    )


def test_6n6p_unit_pins_match_datasheet() -> None:
    sexp = _load_sexp('Tubes_Soviet.6N6P.sexp')
    # Unit 1 (KiCad): A=6, G=7, K=8 (ECC81-pattern); Unit 2: A=1, G=2, K=3.
    # All 6 pin numbers должны присутствовать.
    for num in ('1', '2', '3', '6', '7', '8'):
        assert f'(number "{num}"' in sexp, (
            f'6Н6П должен иметь pin {num} (multi-unit dual triode pinout)'
        )


def test_6n6p_has_two_anode_pins_at_top() -> None:
    sexp = _load_sexp('Tubes_Soviet.6N6P.sexp')
    # Каждый unit имеет anode pin at (0, 10.16, 270) — два таких anode pin'а
    # — критическая структурная подпись multi-unit dual triode.
    # `(at 0 10.16 270)` встречается ровно дважды (по разу в unit 1 и unit 2).
    occurrences = sexp.count('(at 0 10.16 270)')
    assert occurrences == 2, (
        f'6Н6П multi-unit должен иметь 2 anode pin\'а at (0, 10.16, 270) '
        f'(по одному в unit 1 и unit 2), нашёл {occurrences}'
    )
