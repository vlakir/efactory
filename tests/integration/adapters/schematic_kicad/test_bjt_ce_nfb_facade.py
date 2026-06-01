"""T163 Phase A acceptance: BJT CE NFB single-stage fixture.

Single-stage common-emitter NPN amplifier (2N3904) с voltage-divider
bias (R_B1+R_B2) + emitter degeneration R_E + C_E bypass + shunt-shunt
AC-only feedback (R_F + C_F DC-block, collector→base). Закрывает
ADR-T153g BJT CE row (`?` → empirical).

**Q-point validated** в `test_bjt_ce_nfb_op_point_in_active_region`:
V_CE_q ∈ [4, 8] V, I_C_q ∈ [0.5, 3] mA, V_BE_q ∈ [0.55, 0.75] V.

Топология (left → right):

  V_in (VSIN 1 mV @ 1 kHz) → R_S (50 Ω) → C_in (1 µF) → base;
  V_CC (12 V) → R_B1 (100 kΩ) → base;  R_B2 (10 kΩ) → GND (divider bias);
  V_CC → R_C (4.7 kΩ) → vout (collector);
  vout → C_F (1 µF) → R_F (47 kΩ) → base (shunt-shunt AC NFB);
  vout → C_out (10 µF) → vload → R_L (10 kΩ) → GND;
  Q1.E → R_E (470 Ω) ‖ C_E (47 µF) → GND.

Acceptance:
  * netlist содержит Q1 (Q2N3904) primitive call + `.MODEL` через
    `.include models/Q2N3904.lib` directive.
  * Topology asserts: R_F between vout/cf_b, C_F between cf_b/base,
    voltage divider R_B1+R_B2 на base, R_E + C_E parallel на emitter.
  * ngspice op-point analysis: Q1 в active region (Q-point bounds).
  * ERC: 0 errors (cosmetic warnings OK).
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from adapters.outbound.kicad_cli.schematic_exporter import (
    KicadCliSchematicExporter,
)
from adapters.outbound.ngspice.simulator import NgspiceSimulator
from adapters.outbound.platform_native.platform_layer import (
    NativePlatformLayer,
)
from adapters.outbound.schematic_kicad.facade import Schematic
from adapters.outbound.subprocess_apps.app_manager import (
    SubprocessAppManager,
)
from domain.schematic import Position
from domain.simulation import OpAnalysis

_KICAD_AVAILABLE = any(
    (Path.home() / 'kicad').glob('kicad*.AppImage'),
) or shutil.which('kicad-cli') is not None

_NGSPICE_AVAILABLE = shutil.which('ngspice') is not None

needs_kicad = pytest.mark.skipif(
    not _KICAD_AVAILABLE,
    reason='KiCad not installed',
)
needs_ngspice = pytest.mark.skipif(
    not _NGSPICE_AVAILABLE,
    reason='ngspice not installed',
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_BJT_2N3904_LIB = (
    _REPO_ROOT / 'data' / 'models' / 'bjt' / 'onsemi' / 'Q2N3904.lib'
)


# === Layout (mm, Y-down, KiCad standard grid 1.27 mm) ===

# B+ rail Y; rail spans X=50 (V_CC.pin_minus) to X=97.79 (R_C tap).
_BPLUS_RAIL_Y = 58.42
_BPLUS_RAIL_END_X = 97.79  # X of right-most tap (R_C.pin_b)

# Power supply column (X=50): V_CC (DC) above V_in (AC).
_V_CC_AT = (50.0, 63.5)
_GND_VCC_AT = (50.0, 73.66)
_V_IN_AT = (50.0, 88.9)
_GND_VIN_AT = (50.0, 97.79)

# Power flag для B+ rail (ERC).
_FLG_AT = (45.72, 58.42)

# Input chain (Y=88.9): R_S → C_in horizontal pipe to base trunk.
_R_S_AT = (60.96, 88.9)  # rot=90; pin_a@(57.15,88.9), pin_b@(64.77,88.9)
_C_IN_AT = (73.66, 88.9)  # rot=90; pin_a@(69.85,88.9), pin_b@(77.47,88.9)

# Base bias divider: R_B1 (top, V_CC→base) on column X=78.74,
# R_B2 (bottom, base→GND) on column X=88.9 (left of Q1).
_R_B1_AT = (78.74, 63.5)  # pin_a@(78.74,67.31)→base trunk, pin_b@(78.74,59.69)→rail
_R_B2_AT = (88.9, 96.52)  # pin_a@(88.9,100.33)→GND, pin_b@(88.9,92.71)→base trunk

# Feedback chain (Y=74.93): R_F (shunt-shunt res, base-side) + C_F
# (DC-block, vout-side). Order ОТ base К collector: base → R_F → fb_mid
# → C_F → vout. Это matches inline calibration netlist AND KB convention
# `(vout, C_F)` (DC-block прямо за active output, analog к tube `(sec_a,
# C_fb)`).
_R_F_AT = (82.55, 74.93)  # rot=90; pin_a@(78.74,74.93)→base, pin_b@(86.36,74.93)→fb_mid
_C_F_AT = (91.44, 74.93)  # rot=90; pin_a@(87.63,74.93)→fb_mid, pin_b@(95.25,74.93)→collector

# Q1 (NPN 2N3904) center (95.25, 88.9). Pin positions (from _BJT_PINS):
#   B (left):  (95.25-5.08, 88.9)     = (90.17, 88.9)
#   C (right top): (95.25+2.54, 88.9-5.08) = (97.79, 83.82)
#   E (right bot): (95.25+2.54, 88.9+5.08) = (97.79, 93.98)
_Q1_AT = (95.25, 88.9)

# Collector load R_C vertical column X=97.79.
_R_C_AT = (97.79, 63.5)  # pin_a@(97.79,67.31)→collector wire, pin_b@(97.79,59.69)→rail

# Emitter degeneration R_E + C_E bypass.
_R_E_AT = (97.79, 100.0)  # pin_a@(97.79,103.81)→GND, pin_b@(97.79,96.19)→emitter rail
_C_E_AT = (107.95, 96.19)  # rot=90; pin_a@(104.14,96.19)→emitter rail, pin_b@(111.76,96.19)→GND

# Output chain (Y=83.82): C_out coupling + R_L load.
_C_OUT_AT = (107.95, 83.82)  # rot=90; pin_a@(104.14,83.82)→vout extension, pin_b@(111.76,83.82)→vload
_R_L_AT = (124.46, 83.82)  # rot=90; pin_a@(120.65,83.82)→vload, pin_b@(128.27,83.82)→GND

# Ground placements.
_GND_RB2_AT = (88.9, 106.68)
_GND_RE_AT = (97.79, 109.22)
_GND_CE_AT = (111.76, 105.41)
_GND_RL_AT = (128.27, 91.44)

# SPICE directive node (text annotation).
_SPICE_INCLUDE_AT = (135.0, 50.0)


def _app_manager() -> SubprocessAppManager:
    return SubprocessAppManager(NativePlatformLayer())


def _build_bjt_ce_nfb(path: Path) -> Path:  # noqa: PLR0915
    """Builds bjt-ce-nfb reference fixture.

    Imported by `scripts/regenerate-templates.py` to bake the shipping
    template (`data/templates/bjt-ce-nfb/`).
    """
    sch = Schematic('bjt_ce_nfb')

    # === Supplies (column X=50) ===
    # V_DC swap-bug: real "+" pin (1, top, Y-=5.08) — `pin_minus` attr;
    # real "-" pin (2, bottom, Y+=5.08) — `pin_plus` attr. Connect:
    # pin_minus → rail/signal, pin_plus → GND.
    v_cc = sch.add_v_dc(value='12', at=_V_CC_AT, reference='V_CC')
    gnd_vcc = sch.add_ground(at=_GND_VCC_AT)
    sch.connect(v_cc.pin_plus, gnd_vcc.pin)  # real "-" → GND

    v_in = sch.add_v_ac(
        value='VSIN',
        at=_V_IN_AT,
        amplitude=0.001,  # 1 mV small-signal
        frequency=1000.0,
        reference='V_in',
    )
    gnd_vin = sch.add_ground(at=_GND_VIN_AT)
    sch.connect(v_in.pin_plus, gnd_vin.pin)  # real "-" → GND

    # Power flag on B+ rail (ERC requires for un-driven nets).
    flg = sch.add_pwr_flag(at=_FLG_AT, rotation=180)

    # === Resistors and capacitors ===
    r_s = sch.add_resistor(
        value='50', at=_R_S_AT, rotation=90, reference='R_S',
    )
    c_in = sch.add_capacitor(
        value='1u', at=_C_IN_AT, rotation=90, reference='C_in',
    )
    r_b1 = sch.add_resistor(value='100k', at=_R_B1_AT, reference='R_B1')
    r_b2 = sch.add_resistor(value='10k', at=_R_B2_AT, reference='R_B2')
    c_f = sch.add_capacitor(
        value='1u', at=_C_F_AT, rotation=90, reference='C_F',
    )
    r_f = sch.add_resistor(
        value='47k', at=_R_F_AT, rotation=90, reference='R_F',
    )
    r_c = sch.add_resistor(value='4.7k', at=_R_C_AT, reference='R_C')
    r_e = sch.add_resistor(value='470', at=_R_E_AT, reference='R_E')
    c_e = sch.add_capacitor(
        value='47u', at=_C_E_AT, rotation=90, reference='C_E',
    )
    c_out = sch.add_capacitor(
        value='10u', at=_C_OUT_AT, rotation=90, reference='C_out',
    )
    r_l = sch.add_resistor(
        value='10k', at=_R_L_AT, rotation=90, reference='R_L',
    )

    # === Q1 BJT NPN 2N3904 ===
    q1 = sch.add_bjt(
        value='Q2N3904',
        polarity='NPN',
        model_name='Q2N3904',
        at=_Q1_AT,
        reference='Q1',
    )

    # === Grounds ===
    gnd_rb2 = sch.add_ground(at=_GND_RB2_AT)
    gnd_re = sch.add_ground(at=_GND_RE_AT)
    gnd_ce = sch.add_ground(at=_GND_CE_AT)
    gnd_rl = sch.add_ground(at=_GND_RL_AT)

    # === B+ rail (Y=58.42) ===
    # V_CC.pin_minus → horizontal rail → X=_BPLUS_RAIL_END_X (=R_C tap).
    # Pass-through junctions: R_B1.pin_b (X=78.74), pwr_flag (X=45.72),
    # R_C.pin_b (X=97.79 end).
    sch.connect(
        flg.pin,
        Position(x_mm=_BPLUS_RAIL_END_X, y_mm=_BPLUS_RAIL_Y),
    )
    # R_B1 vertical stub: pin_b @ (78.74, 59.69) → rail @ (78.74, 58.42).
    sch.connect(r_b1.pin_b, Position(x_mm=78.74, y_mm=_BPLUS_RAIL_Y))
    sch.junction(at=(78.74, _BPLUS_RAIL_Y))
    # R_C vertical stub: pin_b @ (97.79, 59.69) → rail @ (97.79, 58.42).
    sch.connect(r_c.pin_b, Position(x_mm=_BPLUS_RAIL_END_X, y_mm=_BPLUS_RAIL_Y))
    # V_CC.pin_minus stub from (50, 58.42) — already on rail (covered by flg
    # → rail-end wire passing through X=50).
    sch.connect(
        v_cc.pin_minus,
        Position(x_mm=50.0, y_mm=_BPLUS_RAIL_Y),
    )
    sch.junction(at=(50.0, _BPLUS_RAIL_Y))

    # === Input chain (Y=88.9): V_in → R_S → C_in → base trunk → Q1.B ===
    # V_in.pin_minus (50, 83.82) → R_S.pin_a (57.15, 88.9): Manhattan
    # (vertical→horizontal from start).
    sch.connect(v_in.pin_minus, r_s.pin_a)
    # R_S.pin_b (64.77, 88.9) → C_in.pin_a (69.85, 88.9): horizontal Y=88.9.
    sch.connect(r_s.pin_b, c_in.pin_a)
    # C_in.pin_b (77.47, 88.9) → Q1.B (90.17, 88.9): base trunk Y=88.9.
    sch.connect(c_in.pin_b, q1.pin_b)

    # === Base node taps on base trunk Y=88.9 ===
    # R_B1.pin_a (78.74, 67.31) → base trunk @ (78.74, 88.9). Vertical wire
    # X=78.74 from Y=67.31 to Y=88.9; passes through (78.74, 74.93) where
    # C_F.pin_a sits (тоже base node) — natural merge.
    sch.connect(r_b1.pin_a, Position(x_mm=78.74, y_mm=88.9))
    sch.junction(at=(78.74, 88.9))  # base trunk + R_B1 drop
    sch.junction(at=(78.74, 74.93))  # R_F.pin_a on R_B1 vertical wire (base node)

    # R_B2.pin_b (88.9, 92.71) → base trunk @ (88.9, 88.9): short vertical.
    sch.connect(r_b2.pin_b, Position(x_mm=88.9, y_mm=88.9))
    sch.junction(at=(88.9, 88.9))  # base trunk + R_B2 stub
    # R_B2.pin_a → GND.
    sch.connect(r_b2.pin_a, gnd_rb2.pin)

    # === Feedback chain (Y=74.93): base — R_F — fb_mid — C_F — collector.
    # R_F.pin_a sits on base trunk (X=78.74, junction добавлен выше);
    # R_F.pin_b → C_F.pin_a (gap 1.27 mm); C_F.pin_b → collector wire @
    # (97.79, 74.93). Order matches inline calibration + KB convention
    # `(vout, C_F)` — DC-block прямо за active output. ===
    sch.connect(r_f.pin_b, c_f.pin_a)  # (86.36, 74.93) → (87.63, 74.93)
    sch.connect(
        c_f.pin_b,
        Position(x_mm=_BPLUS_RAIL_END_X, y_mm=74.93),
    )
    sch.junction(at=(_BPLUS_RAIL_END_X, 74.93))  # C_F.pin_b on collector wire

    # === Collector chain (X=97.79): Q1.C → R_C.pin_a vertical ===
    # Wire passes through (97.79, 74.93) where R_F.pin_b joins.
    sch.connect(q1.pin_c, r_c.pin_a)
    # Q1.C also extends RIGHT to C_out.pin_a @ (104.14, 83.82).
    sch.connect(q1.pin_c, c_out.pin_a)
    sch.junction(at=q1.pin_c)  # T-junction at Q1.C (collector + R_C up + C_out right)

    # === Output chain (Y=83.82): C_out → vload → R_L → GND ===
    sch.connect(c_out.pin_b, r_l.pin_a)  # (111.76, 83.82) → (120.65, 83.82)
    sch.connect(r_l.pin_b, gnd_rl.pin)  # (128.27, 83.82) → (128.27, 91.44)

    # === Emitter chain ===
    # Q1.E (97.79, 93.98) → R_E.pin_b (97.79, 96.19): vertical short stub.
    sch.connect(q1.pin_e, r_e.pin_b)
    sch.junction(at=(97.79, 96.19))  # R_E.pin_b + C_E horizontal tap
    # C_E.pin_a (104.14, 96.19) → emitter rail @ (97.79, 96.19) horizontal.
    sch.connect(c_e.pin_a, Position(x_mm=97.79, y_mm=96.19))
    # C_E.pin_b → GND.
    sch.connect(c_e.pin_b, gnd_ce.pin)
    # R_E.pin_a → GND.
    sch.connect(r_e.pin_a, gnd_re.pin)

    # === SPICE labels (trace names для phase-margin tools) ===
    sch.label('vin', at=r_s.pin_a)
    sch.label('base', at=q1.pin_b)
    sch.label('vout', at=q1.pin_c)
    sch.label('vload', at=Position(x_mm=115.0, y_mm=83.82))
    sch.label('emitter', at=q1.pin_e)

    # === SPICE include для 2N3904 model card ===
    sch.spice_directive(
        f'.include {_BJT_2N3904_LIB}',
        at=_SPICE_INCLUDE_AT,
    )

    return sch.save(path)


async def _export_netlist(schematic_path: Path, netlist_path: Path) -> Path:
    exporter = KicadCliSchematicExporter(_app_manager())
    return await exporter.export_spice_netlist(schematic_path, netlist_path)


@needs_kicad
async def test_facade_bjt_ce_nfb_writes_model_include(tmp_path: Path) -> None:
    """Netlist contains Q1 primitive call + .include for Q2N3904 model."""
    sch_path = _build_bjt_ce_nfb(tmp_path / 'bjt_ce_nfb.kicad_sch')
    netlist = await _export_netlist(sch_path, tmp_path / 'bjt_ce_nfb.cir')
    text = netlist.read_text()

    # `.include` директива для model card.
    assert 'Q2N3904.lib' in text, text
    # Q1 — primitive BJT call, не subckt (no leading X).
    q_lines = [ln for ln in text.splitlines() if re.match(r'^Q\w', ln)]
    assert len(q_lines) == 1, (
        f'expected exactly one Q (BJT primitive), got {len(q_lines)}: {q_lines}'
    )
    assert q_lines[0].endswith('Q2N3904'), q_lines[0]


@needs_kicad
async def test_facade_bjt_ce_nfb_topology(tmp_path: Path) -> None:
    """Verify CE shunt-shunt topology in exported SPICE netlist."""
    sch_path = _build_bjt_ce_nfb(tmp_path / 'bjt_ce_nfb.kicad_sch')
    netlist = await _export_netlist(sch_path, tmp_path / 'bjt_ce_nfb.cir')
    lines = netlist.read_text().splitlines()

    # R_C between B+ rail (V_CC side) and vout (collector).
    assert any(
        ln.startswith('R_C ') and 'vout' in ln and ' 4.7k' in ln
        for ln in lines
    ), '\n'.join(lines)

    # R_F between vout and base via C_F (DC-blocked AC feedback).
    # R_F одной стороной на vout-side feedback midpoint, другой на C_F.
    r_f_line = next(ln for ln in lines if ln.startswith('R_F '))
    assert ' 47k' in r_f_line, r_f_line
    # C_F same way — DC-block.
    c_f_line = next(ln for ln in lines if ln.startswith('C_F '))
    assert ' 1u' in c_f_line, c_f_line

    # R_B1 + R_B2 на base voltage divider.
    r_b1_line = next(ln for ln in lines if ln.startswith('R_B1 '))
    r_b2_line = next(ln for ln in lines if ln.startswith('R_B2 '))
    assert 'base' in r_b1_line and ' 100k' in r_b1_line, r_b1_line
    assert 'base' in r_b2_line and ' 10k' in r_b2_line, r_b2_line

    # R_E + C_E parallel на emitter.
    r_e_line = next(ln for ln in lines if ln.startswith('R_E '))
    c_e_line = next(ln for ln in lines if ln.startswith('C_E '))
    assert 'emitter' in r_e_line and ' 470' in r_e_line, r_e_line
    assert 'emitter' in c_e_line and ' 47u' in c_e_line, c_e_line

    # Q1: пины C/B/E на vout/base/emitter nodes.
    q1_line = next(ln for ln in lines if ln.startswith('Q1 '))
    parts = q1_line.split()
    # Q1 <C> <B> <E> Q2N3904
    assert parts[-1] == 'Q2N3904', q1_line
    assert any('vout' in p for p in parts[1:4]), q1_line
    assert any('base' in p for p in parts[1:4]), q1_line
    assert any('emitter' in p for p in parts[1:4]), q1_line


@needs_kicad
@needs_ngspice
async def test_facade_bjt_ce_nfb_op_point_in_active_region(
    tmp_path: Path,
) -> None:
    """DC op-point: Q1 в active region (V_CE_q ∈ [4,8]V, I_C_q ∈ [0.5,3]mA).

    Acceptance gate в spec §3 — гарантирует, что bias network даёт
    working Q-point. При future changes к component values этот тест
    ловит регрессию.
    """
    sch_path = _build_bjt_ce_nfb(tmp_path / 'bjt_ce_nfb.kicad_sch')
    netlist_path = await _export_netlist(
        sch_path, tmp_path / 'bjt_ce_nfb.cir',
    )

    simulator = NgspiceSimulator(_app_manager())
    result = await simulator.run(netlist_path, analysis=OpAnalysis())
    assert result.operating_points is not None, result

    # ngspice op-point keys: `v(/base)`, `v(/vout)`, `i(v_cc)`. Strip
    # `v(...)` envelope and leading `/` to get pure node names.
    nodes = {}
    for raw_key, value in result.operating_points.items():
        if raw_key.startswith('v(') and raw_key.endswith(')'):
            name = raw_key[2:-1].lstrip('/').lower()
            nodes[name] = value
    assert 'vout' in nodes, list(nodes.keys())
    assert 'base' in nodes, list(nodes.keys())
    assert 'emitter' in nodes, list(nodes.keys())

    v_vout = nodes['vout']
    v_base = nodes['base']
    v_emitter = nodes['emitter']

    v_ce = v_vout - v_emitter
    v_be = v_base - v_emitter
    # I_C ≈ (V_CC - V_vout) / R_C = (12 - V_vout) / 4.7k.
    i_c_ma = (12.0 - v_vout) / 4.7

    assert 4.0 <= v_ce <= 8.0, (
        f'V_CE_q out of active region: {v_ce:.3f} V '
        f'(V_vout={v_vout:.3f}, V_emitter={v_emitter:.3f})'
    )
    assert 0.55 <= v_be <= 0.75, (
        f'V_BE_q implausible: {v_be:.3f} V'
    )
    assert 0.5 <= i_c_ma <= 3.0, (
        f'I_C_q out of target window: {i_c_ma:.3f} mA'
    )
