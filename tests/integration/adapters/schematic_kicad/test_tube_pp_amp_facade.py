"""T027 Phase A acceptance: Tube push-pull power amp fixture.

Long-tail-pair (LTP) splitter на обеих половинах 6Н2П (Valve:ECC83
unit 1 + unit 2 = ECC83B) + пара 6П14П (Valve:EL84) в push-pull с
per-tube auto-bias + OPT_PP_6K6_8 (center-tapped primary) + 8 Ω load.
Open-loop (без global NFB) — NFB-вариант остаётся в BACKLOG отдельной
задачей по аналогии с nfb-se-amp.

**Phase splitter choice — LTP, not concertina (ADR-T027a).** Vladimir
изначально (Round 2 Q3) одобрил concertina на одной половине 6Н2П, но
empirical-валидация на Koren-style 6N2P model показала, что
equal-resistance concertina (Ra=Rk=47kΩ, grounded grid) biases tube
near cutoff (I_a quiescent ≈ 0.15 mA, V_GK ≈ -3.3 V), и plate-output
gain атрофирует до ≈0.05 V/V — splitter не балансирует anti-phase.
Концертина с grid voltage divider могла бы спасти, но LTP — textbook-
standard для PP (Williamson 1947, Marshall Plexi PI) и robust к
model parameter drift. ADR обновлён в DECISIONS.md.

Топология (left → right):

  V_in (VSIN 50 mV @ 1 kHz) → C_in (100 nF) → R_g1A (1 MΩ) ‖ V1A.G;
  V1B.G → R_g1B (1 MΩ) → GND (AC reference, anti-phase output side);
  V1A.K + V1B.K → R_tail (4.7 kΩ) → GND (common-mode tail);
  V1A.P → R_p1A (47 kΩ) → B+;
  V1B.P → R_p1B (47 kΩ) → B+;
  V1A.P → C_couple_a (47 nF) → R_g2a (470 kΩ) ‖ V2a.G (6П14П);
  V1B.P → C_couple_b (47 nF) → R_g2b (470 kΩ) ‖ V2b.G (6П14П);
  V2a/V2b.G2 → B+ (screen rail);
  V2a.K → R_k2a (270 Ω) ‖ C_k2a (220 µF) → GND (auto-bias);
  V2b.K → R_k2b (270 Ω) ‖ C_k2b (220 µF) → GND (auto-bias);
  V2a.P → OPT.P1;  V2b.P → OPT.P2;  OPT.PC → B+ (center tap);
  OPT.S1 → R_load (8 Ω) → OPT.S2 → GND (single-ended ref).

Acceptance:
  * netlist содержит X1 + X2 (6N2P pair) + X3 + X4 (6P14P PP pair) +
    X5 (OPT_PP_6K6_8); .include для всех трёх .lib (6N2P, 6P14P,
    OPT_PP_6K6_8).
  * Topology asserts: equal R_p1A=R_p1B (LTP plate-balance), per-tube
    R_k2=270 + C_k2=220µ, OPT.PC routed to B+ rail.
  * ngspice op-point: обе 6П14П в active region (V_anode_q ≈ B+, I_a_q
    ∈ [20, 50] mA, V_cath_q ∈ [4, 12] V auto-bias). V1A/V1B splitter в
    active region (V_plate_q ≪ B+ — proper LTP bias).
"""

from __future__ import annotations

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
from domain.spice_model import (
    ComponentCategory,
    ModelSource,
    SpiceModel,
)

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
_TUBE_6N2P_LIB = (
    _REPO_ROOT / 'data' / 'models' / 'tubes' / 'custom' / '6N2P.lib'
)
_TUBE_6P14P_LIB = (
    _REPO_ROOT / 'data' / 'models' / 'tubes' / 'custom' / '6P14P.lib'
)
_OPT_LIB = (
    _REPO_ROOT
    / 'data'
    / 'models'
    / 'transformers'
    / 'generic'
    / 'OPT_PP_6K6_8.lib'
)


def _tube_6n2p() -> SpiceModel:
    return SpiceModel(
        id='6N2P',
        name='6Н2П',
        category=ComponentCategory.TUBE,
        subcategory='triode',
        source=ModelSource.CUSTOM,
        file_path=_TUBE_6N2P_LIB,
        subckt_pins=('P', 'G', 'K'),
    )


def _tube_6p14p() -> SpiceModel:
    return SpiceModel(
        id='6P14P',
        name='6П14П',
        category=ComponentCategory.TUBE,
        subcategory='pentode',
        source=ModelSource.CUSTOM,
        file_path=_TUBE_6P14P_LIB,
        subckt_pins=('P', 'G2', 'G', 'K'),
    )


def _opt_pp_6k6_8() -> SpiceModel:
    return SpiceModel(
        id='OPT_PP_6K6_8',
        name='OPT_PP_6K6_8',
        category=ComponentCategory.TRANSFORMER,
        subcategory='opt',
        source=ModelSource.GENERIC,
        file_path=_OPT_LIB,
        subckt_pins=('P1', 'PC', 'P2', 'S1', 'S2'),
    )


# Layout (mm, Y-down, KiCad grid 1.27 mm). Stretched от nfb-se-amp:
# V1A, V1B (LTP splitter) side-by-side at Y=88.9, then V2a, V2b at
# Y=88.9, OPT (Transformer_2P_1S) at Y=72.39, R_load at right end.

_BPLUS_RAIL_Y = 58.42
_PLATE2_WIRE_Y = 67.31  # V2a/V2b plates → OPT.P1/P2 (above B+ rail)
_CCOUPLE_A_WIRE_Y = 72.39  # C_couple_a horizontal route (above plate-pin level)
_CCOUPLE_B_WIRE_Y = 63.5  # C_couple_b separate Y to не пересекаться с C_couple_a
_PLATE1_WIRE_Y = 78.74  # V1A.P / V1B.P (plate pins)
_CATHODE_RAIL_Y = 101.6  # Common cathode rail V1A.K + V1B.K → R_tail

# === Stage 0: power supply, input source, flag ===
_V_BB_AT = (50.8, 63.5)
_GND_VBB_AT = (50.8, 73.66)
_V_IN_AT = (50.8, 88.9)
_GND_VIN_AT = (50.8, 97.79)
_FLG_AT = (45.72, 97.79)

# === Stage 1: 6Н2П LTP splitter (V1A=ECC83 unit 1, V1B=ECC83B unit 2) ===
_C_IN_AT = (63.5, 83.82)
_R_G1A_AT = (78.74, 93.98)  # 1Meg: pin_a@(78.74,97.79)→GND, pin_b@(78.74,90.17)=V1A.G
# GND placements for grid-leak R's must avoid cathode_rail Y=101.6 (collision
# shorts cathode tail to GND). Use Y=99.06 (между pin_a Y=97.79 and rail).
_GND_RG1A_AT = (78.74, 99.06)
# V1A — ECC83 unit 1. Pin positions от center (88.9, 88.9):
#   '6' (P):  (0.0, -10.16)  → (88.9, 78.74)
#   '7' (G):  (-7.62, 0.0)   → (81.28, 88.9)
#   '8' (K):  (-2.54, 10.16) → (86.36, 99.06)
_TUBE1A_AT = (88.9, 88.9)
_R_P1A_AT = (88.9, 68.58)  # pin_a@(88.9,72.39), pin_b@(88.9,64.77)→rail

# V1B — ECC83 unit 2 (ECC83B). Same pin geometry. Center (114.3, 88.9):
#   '1' (P):  (0.0, -10.16)  → (114.3, 78.74)
#   '2' (G):  (-7.62, 0.0)   → (106.68, 88.9)
#   '3' (K):  (-2.54, 10.16) → (111.76, 99.06)
_TUBE1B_AT = (114.3, 88.9)
_R_G1B_AT = (99.06, 93.98)  # 1Meg V1B grid leak: pin_a→GND, pin_b@(99.06,90.17)→V1B.G wire
_GND_RG1B_AT = (99.06, 99.06)
_R_P1B_AT = (114.3, 68.58)

# Common cathode tail resistor (LTP).
_R_TAIL_AT = (99.06, 109.22)  # 4.7k: pin_a@(99.06,113.03)→GND, pin_b@(99.06,105.41)→cathode rail
_GND_RTAIL_AT = (99.06, 116.84)

# === Stage 1-2 coupling ===
# C_couple_a: V1A.P (88.9, 78.74) → V2a.G (137.16, 90.17). Route via
# Y=72.39 (above V1B body) to avoid V1B.P pin at Y=78.74.
_C_COUPLE_A_AT = (123.19, 72.39)  # rot=90: pin_a@(119.38,72.39), pin_b@(127, 72.39)
# C_couple_b: V1B.P (114.3, 78.74) → V2b.G (167.64, 90.17). Route via
# Y=63.5 (different level from C_couple_a route to clean crossing).
_C_COUPLE_B_AT = (148.59, 63.5)  # rot=90: pin_a@(144.78,63.5), pin_b@(152.4,63.5)

# === Stage 2: 6П14П PP pair (Valve:EL84) ===
# V2a (top tube)
_R_G2A_AT = (137.16, 93.98)  # 470k: pin_a→GND, pin_b@(137.16,90.17)=V2a.G
_GND_RG2A_AT = (137.16, 99.06)
_TUBE2A_AT = (144.78, 88.9)
_R_K2A_AT = (142.24, 109.22)
_C_K2A_AT = (152.4, 109.22)
_GND_RK2A_AT = (142.24, 116.84)
_GND_CK2A_AT = (152.4, 116.84)

# V2b (bottom tube)
_R_G2B_AT = (167.64, 93.98)
_GND_RG2B_AT = (167.64, 99.06)
_TUBE2B_AT = (175.26, 88.9)
_R_K2B_AT = (172.72, 109.22)
_C_K2B_AT = (182.88, 109.22)
_GND_RK2B_AT = (172.72, 116.84)
_GND_CK2B_AT = (182.88, 116.84)

# === Stage 2 → OPT_PP_6K6_8 ===
# Transformer_2P_1S center (195.58, 72.39):
#   P1 (primary top, V2a anode):    (-10.16, -5.08) → (185.42, 67.31)
#   PC (center tap, B+ rail):       (-10.16, 0.0)   → (185.42, 72.39)
#   P2 (primary bottom, V2b anode): (-10.16, +5.08) → (185.42, 77.47)
#   S1 (secondary top):             (+10.16, -5.08) → (205.74, 67.31)
#   S2 (secondary bottom, gnd-ref): (+10.16, +5.08) → (205.74, 77.47)
_OPT_AT = (195.58, 72.39)
_BPLUS_RAIL_END_X = 195.58
_R_LOAD_AT = (215.9, 81.28)  # 8Ω: pin_a@(215.9,85.09)→GND, pin_b@(215.9,77.47)=OPT.S2 horizontal wire
_GND_RLOAD_AT = (215.9, 88.9)
_GND_OPT_S2_HOP_AT = (205.74, 86.36)

# SPICE directive node.
_SPICE_DIRECTIVE_AT = (50.8, 130.0)


def _app_manager() -> SubprocessAppManager:
    return SubprocessAppManager(NativePlatformLayer())


def _build_tube_pp_amp(path: Path) -> Path:  # noqa: PLR0915
    """Builds tube-pp-amp reference fixture (LTP splitter version).

    Imported by `scripts/regenerate-templates.py` to bake the shipping
    template (`data/templates/tube-pp-amp/`).
    """
    sch = Schematic('tube_pp_amp_6n2p_6p14p')

    # === Supplies & input ===
    v_bb = sch.add_v_dc(value='300', at=_V_BB_AT)
    v_in = sch.add_v_ac(
        value='VSIN',
        at=_V_IN_AT,
        amplitude=0.050,
        frequency=1000.0,
    )
    flg = sch.add_pwr_flag(at=_FLG_AT, rotation=180)

    # === Stage 1: 6Н2П LTP splitter ===
    c_in = sch.add_capacitor(value='100n', at=_C_IN_AT, rotation=90)
    r_g1a = sch.add_resistor(value='1Meg', at=_R_G1A_AT)
    r_g1b = sch.add_resistor(value='1Meg', at=_R_G1B_AT)
    xv1a = sch.add_tube(
        spice_model=_tube_6n2p(),
        at=_TUBE1A_AT,
        symbol='Valve:ECC83',
    )
    xv1b = sch.add_tube(
        spice_model=_tube_6n2p(),
        at=_TUBE1B_AT,
        symbol='Valve:ECC83B',
    )
    r_p1a = sch.add_resistor(value='47k', at=_R_P1A_AT)
    r_p1b = sch.add_resistor(value='47k', at=_R_P1B_AT)
    r_tail = sch.add_resistor(value='4.7k', at=_R_TAIL_AT)

    # === Stage 1 → Stage 2 coupling ===
    c_couple_a = sch.add_capacitor(
        value='47n', at=_C_COUPLE_A_AT, rotation=90,
    )
    c_couple_b = sch.add_capacitor(
        value='47n', at=_C_COUPLE_B_AT, rotation=90,
    )

    # === Stage 2: 6П14П PP pair ===
    r_g2a = sch.add_resistor(value='470k', at=_R_G2A_AT)
    xv2a = sch.add_tube(
        spice_model=_tube_6p14p(),
        at=_TUBE2A_AT,
        symbol='Valve:EL84',
    )
    r_k2a = sch.add_resistor(value='270', at=_R_K2A_AT)
    c_k2a = sch.add_capacitor(value='220u', at=_C_K2A_AT)

    r_g2b = sch.add_resistor(value='470k', at=_R_G2B_AT)
    xv2b = sch.add_tube(
        spice_model=_tube_6p14p(),
        at=_TUBE2B_AT,
        symbol='Valve:EL84',
    )
    r_k2b = sch.add_resistor(value='270', at=_R_K2B_AT)
    c_k2b = sch.add_capacitor(value='220u', at=_C_K2B_AT)

    # === OPT + load ===
    xt1 = sch.add_transformer(
        spice_model=_opt_pp_6k6_8(),
        at=_OPT_AT,
        symbol='Device:Transformer_2P_1S',
    )
    r_load = sch.add_resistor(value='8', at=_R_LOAD_AT)

    # === Grounds ===
    gnd_vbb = sch.add_ground(at=_GND_VBB_AT)
    gnd_vin = sch.add_ground(at=_GND_VIN_AT)
    gnd_rg1a = sch.add_ground(at=_GND_RG1A_AT)
    gnd_rg1b = sch.add_ground(at=_GND_RG1B_AT)
    gnd_rtail = sch.add_ground(at=_GND_RTAIL_AT)
    gnd_rg2a = sch.add_ground(at=_GND_RG2A_AT)
    gnd_rk2a = sch.add_ground(at=_GND_RK2A_AT)
    gnd_ck2a = sch.add_ground(at=_GND_CK2A_AT)
    gnd_rg2b = sch.add_ground(at=_GND_RG2B_AT)
    gnd_rk2b = sch.add_ground(at=_GND_RK2B_AT)
    gnd_ck2b = sch.add_ground(at=_GND_CK2B_AT)
    gnd_rload = sch.add_ground(at=_GND_RLOAD_AT)
    gnd_opt_s2 = sch.add_ground(at=_GND_OPT_S2_HOP_AT)

    # === B+ rail (Y=58.42) ===
    # V_BB.pin_minus → горизонталь rail до X=BPLUS_RAIL_END_X. Junctions:
    # R_p1A (88.9), R_p1B (114.3), V2a.G2 (152.4), V2b.G2 (182.88), OPT.PC stub (185.42 corner).
    sch.connect(
        v_bb.pin_minus,
        Position(x_mm=_BPLUS_RAIL_END_X, y_mm=_BPLUS_RAIL_Y),
    )
    sch.connect(r_p1a.pin_b, Position(x_mm=88.9, y_mm=_BPLUS_RAIL_Y))
    sch.junction(at=(88.9, _BPLUS_RAIL_Y))
    sch.connect(r_p1b.pin_b, Position(x_mm=114.3, y_mm=_BPLUS_RAIL_Y))
    sch.junction(at=(114.3, _BPLUS_RAIL_Y))
    # V2a.G2 stub: (X+7.62, 87.63) = (152.4, 87.63). Vertical to rail.
    sch.connect(
        xv2a.pin('G2'),
        Position(x_mm=152.4, y_mm=_BPLUS_RAIL_Y),
    )
    sch.junction(at=(152.4, _BPLUS_RAIL_Y))
    sch.connect(
        xv2b.pin('G2'),
        Position(x_mm=182.88, y_mm=_BPLUS_RAIL_Y),
    )
    sch.junction(at=(182.88, _BPLUS_RAIL_Y))
    # OPT.PC stub L-route: (185.42, 72.39) → (185.42, 58.42) → rail end.
    sch.connect(
        xt1.pin('PC'),
        Position(x_mm=185.42, y_mm=_BPLUS_RAIL_Y),
    )
    sch.junction(at=(185.42, _BPLUS_RAIL_Y))

    # === Power-flag → V_in.pin_plus (T100 pattern) ===
    sch.connect(flg.pin, v_in.pin_plus)

    # === Stage 1A grid (V_in → C_in → R_g1A + V1A.G) ===
    sch.connect(v_in.pin_minus, c_in.pin_a)
    sch.connect(c_in.pin_b, Position(x_mm=67.31, y_mm=88.9))
    sch.connect(Position(x_mm=67.31, y_mm=88.9), xv1a.pin('G'))
    sch.connect(r_g1a.pin_b, Position(x_mm=78.74, y_mm=88.9))
    sch.junction(at=(78.74, 88.9))

    # === Stage 1B grid (V1B.G → R_g1B → GND, anti-phase AC reference) ===
    # V1B.G (106.68, 88.9) → R_g1B.pin_b (99.06, 90.17). L-route via
    # corner (99.06, 88.9). Or wire через grid trunk Y=88.9.
    sch.connect(r_g1b.pin_b, Position(x_mm=99.06, y_mm=88.9))
    sch.connect(
        Position(x_mm=99.06, y_mm=88.9),
        xv1b.pin('G'),
    )

    # === V1A plate (V1A.P → R_p1A.pin_a) ===
    # V1A.P (88.9, 78.74) overlaps R_p1A.pin_a (88.9, 72.39) on X=88.9.
    sch.connect(xv1a.pin('P'), r_p1a.pin_a)
    # V1A.P also → C_couple_a via Y=72.39 horizontal route. Wire:
    # (88.9, 78.74) → corner (88.9, 72.39) → C_couple_a.pin_a (119.38, 72.39).
    # Vertical X=88.9 already covered by V1A.P-R_p1A connection (which is
    # vertical line X=88.9, Y∈[72.39, 78.74]). Add junction at (88.9, 72.39)
    # to T-off horizontal route.
    sch.connect(
        Position(x_mm=88.9, y_mm=_CCOUPLE_A_WIRE_Y),
        c_couple_a.pin_a,
    )
    sch.junction(at=(88.9, _CCOUPLE_A_WIRE_Y))

    # === V1B plate (V1B.P → R_p1B.pin_a) ===
    sch.connect(xv1b.pin('P'), r_p1b.pin_a)
    # V1B.P → C_couple_b via Y=63.5 horizontal route (separate level
    # from C_couple_a route at Y=72.39). Wire:
    # (114.3, 78.74) → corner (114.3, 63.5) → C_couple_b.pin_a (144.78, 63.5).
    # Vertical X=114.3 от Y=78.74 → Y=63.5: passes through Y=72.39 (C_couple_a
    # route horizontal — но at X=88.9 to X=119.38). At X=114.3 — within range,
    # crossing without junction (no electrical contact).
    sch.connect(
        xv1b.pin('P'),
        Position(x_mm=114.3, y_mm=_CCOUPLE_B_WIRE_Y),
    )
    sch.connect(
        Position(x_mm=114.3, y_mm=_CCOUPLE_B_WIRE_Y),
        c_couple_b.pin_a,
    )

    # === Common cathode rail (V1A.K + V1B.K → R_tail) ===
    # V1A.K (86.36, 99.06) → cathode rail Y=101.6 → R_tail.pin_b (99.06, 105.41)
    sch.connect(xv1a.pin('K'), Position(x_mm=86.36, y_mm=_CATHODE_RAIL_Y))
    sch.junction(at=(86.36, _CATHODE_RAIL_Y))
    # Cathode rail horizontal Y=101.6: (86.36) → (111.76), passing (99.06).
    sch.connect(
        Position(x_mm=86.36, y_mm=_CATHODE_RAIL_Y),
        Position(x_mm=111.76, y_mm=_CATHODE_RAIL_Y),
    )
    sch.connect(xv1b.pin('K'), Position(x_mm=111.76, y_mm=_CATHODE_RAIL_Y))
    sch.junction(at=(111.76, _CATHODE_RAIL_Y))
    # R_tail.pin_b (99.06, 105.41) → cathode rail (99.06, 101.6) — vertical stub.
    sch.connect(
        r_tail.pin_b,
        Position(x_mm=99.06, y_mm=_CATHODE_RAIL_Y),
    )
    sch.junction(at=(99.06, _CATHODE_RAIL_Y))

    # === Stage 2 grid V2a (C_couple_a.pin_b → R_g2a + V2a.G) ===
    # C_couple_a.pin_b (127.0, 72.39) → V2a.G (137.16, 90.17). L-route.
    sch.connect(
        c_couple_a.pin_b,
        Position(x_mm=137.16, y_mm=_CCOUPLE_A_WIRE_Y),
    )
    sch.connect(
        Position(x_mm=137.16, y_mm=_CCOUPLE_A_WIRE_Y),
        xv2a.pin('G'),
    )
    sch.connect(r_g2a.pin_b, Position(x_mm=137.16, y_mm=90.17))
    sch.junction(at=(137.16, 90.17))

    # === Stage 2 grid V2b (C_couple_b.pin_b → R_g2b + V2b.G) ===
    # C_couple_b.pin_b (152.4, 63.5) → V2b.G (167.64, 90.17). L-route.
    sch.connect(
        c_couple_b.pin_b,
        Position(x_mm=167.64, y_mm=_CCOUPLE_B_WIRE_Y),
    )
    sch.connect(
        Position(x_mm=167.64, y_mm=_CCOUPLE_B_WIRE_Y),
        xv2b.pin('G'),
    )
    sch.connect(r_g2b.pin_b, Position(x_mm=167.64, y_mm=90.17))
    sch.junction(at=(167.64, 90.17))

    # === Stage 2 cathode V2a ===
    sch.connect(xv2a.pin('K'), r_k2a.pin_b)
    sch.junction(at=(142.24, 105.41))
    sch.connect(
        Position(x_mm=142.24, y_mm=105.41),
        c_k2a.pin_b,
    )

    # === Stage 2 cathode V2b ===
    sch.connect(xv2b.pin('K'), r_k2b.pin_b)
    sch.junction(at=(172.72, 105.41))
    sch.connect(
        Position(x_mm=172.72, y_mm=105.41),
        c_k2b.pin_b,
    )

    # === Stage 2 plate V2a → OPT.P1 ===
    # V2a.P (144.78, 77.47) → corner (144.78, 67.31) → OPT.P1 (185.42, 67.31).
    sch.connect(
        xv2a.pin('P'),
        Position(x_mm=144.78, y_mm=_PLATE2_WIRE_Y),
    )
    sch.connect(
        Position(x_mm=144.78, y_mm=_PLATE2_WIRE_Y),
        xt1.pin('P1'),
    )

    # === Stage 2 plate V2b → OPT.P2 ===
    # V2b.P (175.26, 77.47) → OPT.P2 (185.42, 77.47): horizontal Y=77.47.
    sch.connect(xv2b.pin('P'), xt1.pin('P2'))

    # === OPT secondary → R_load ===
    # OPT.S1 (205.74, 67.31) → corner (215.9, 67.31) → R_load.pin_b
    # (215.9, 77.47). L-route.
    sch.connect(
        xt1.pin('S1'),
        Position(x_mm=215.9, y_mm=67.31),
    )
    sch.connect(
        Position(x_mm=215.9, y_mm=67.31),
        r_load.pin_b,
    )
    # OPT.S2 → GND (single-ended reference)
    sch.connect(xt1.pin('S2'), gnd_opt_s2.pin)
    # R_load.pin_a → GND
    sch.connect(r_load.pin_a, gnd_rload.pin)

    # === Ground hookups ===
    sch.connect(v_bb.pin_plus, gnd_vbb.pin)
    sch.connect(v_in.pin_plus, gnd_vin.pin)
    sch.connect(r_g1a.pin_a, gnd_rg1a.pin)
    sch.connect(r_g1b.pin_a, gnd_rg1b.pin)
    sch.connect(r_tail.pin_a, gnd_rtail.pin)
    sch.connect(r_g2a.pin_a, gnd_rg2a.pin)
    sch.connect(r_k2a.pin_a, gnd_rk2a.pin)
    sch.connect(c_k2a.pin_a, gnd_ck2a.pin)
    sch.connect(r_g2b.pin_a, gnd_rg2b.pin)
    sch.connect(r_k2b.pin_a, gnd_rk2b.pin)
    sch.connect(c_k2b.pin_a, gnd_ck2b.pin)

    # === SPICE labels ===
    sch.label('input', at=v_in.pin_minus)
    sch.label('grid1a', at=xv1a.pin('G'))
    sch.label('plate1a', at=xv1a.pin('P'))
    sch.label('grid1b', at=xv1b.pin('G'))
    sch.label('plate1b', at=xv1b.pin('P'))
    sch.label('cathode_tail', at=r_tail.pin_b)
    sch.label('grid2a', at=xv2a.pin('G'))
    sch.label('plate2a', at=xv2a.pin('P'))
    sch.label('cathode2a', at=xv2a.pin('K'))
    sch.label('grid2b', at=xv2b.pin('G'))
    sch.label('plate2b', at=xv2b.pin('P'))
    sch.label('cathode2b', at=xv2b.pin('K'))
    sch.label('sec_a', at=xt1.pin('S1'))
    sch.label('sec_b', at=xt1.pin('S2'))

    sch.spice_directive('.op', at=_SPICE_DIRECTIVE_AT)

    return sch.save(path)


async def _export_netlist(schematic_path: Path, netlist_path: Path) -> Path:
    exporter = KicadCliSchematicExporter(_app_manager())
    return await exporter.export_spice_netlist(schematic_path, netlist_path)


@needs_kicad
async def test_facade_tube_pp_amp_writes_model_includes(
    tmp_path: Path,
) -> None:
    """Netlist содержит X1..X5 + .include для 6N2P / 6P14P / OPT_PP_6K6_8."""
    sch_path = _build_tube_pp_amp(tmp_path / 'tube_pp_amp.kicad_sch')
    netlist = await _export_netlist(sch_path, tmp_path / 'tube_pp_amp.cir')
    text = netlist.read_text()

    x_lines = [ln for ln in text.splitlines() if ln.startswith('X')]
    assert len(x_lines) >= 5, (
        f'expected ≥5 X-instances (2 LTP + 2 PP outputs + OPT), '
        f'got {len(x_lines)}: {x_lines}'
    )

    subckt_models = {ln.split()[-1] for ln in x_lines}
    assert '6N2P' in subckt_models, x_lines
    assert '6P14P' in subckt_models, x_lines
    assert 'OPT_PP_6K6_8' in subckt_models, x_lines

    assert '6N2P.lib' in text, text
    assert '6P14P.lib' in text, text
    assert 'OPT_PP_6K6_8.lib' in text, text

    # TWO 6N2P instances (LTP pair) AND TWO 6P14P instances (PP pair).
    n2p_lines = [ln for ln in x_lines if ln.endswith('6N2P')]
    assert len(n2p_lines) == 2, n2p_lines
    el84_lines = [ln for ln in x_lines if ln.endswith('6P14P')]
    assert len(el84_lines) == 2, el84_lines


@needs_kicad
async def test_facade_tube_pp_amp_topology(tmp_path: Path) -> None:
    """Verify LTP + PP + center-tap OPT topology in netlist."""
    sch_path = _build_tube_pp_amp(tmp_path / 'tube_pp_amp.kicad_sch')
    netlist = await _export_netlist(sch_path, tmp_path / 'tube_pp_amp.cir')
    lines = netlist.read_text().splitlines()

    # LTP plate-balance: two equal R_p1A=R_p1B at 47k.
    r_lines = [ln for ln in lines if ln.startswith('R')]
    r_47k = [ln for ln in r_lines if ' 47k' in ln]
    assert len(r_47k) == 2, (
        f'expected exactly 2× 47k plate loads (R_p1A=R_p1B), got: {r_47k}'
    )

    # R_tail 4.7k (common-mode cathode).
    r_4k7 = [ln for ln in r_lines if ' 4.7k' in ln]
    assert len(r_4k7) == 1, f'expected exactly 1× 4.7k R_tail, got: {r_4k7}'

    # Per-tube auto-bias: two 270Ω + two 220µF.
    r_270 = [
        ln for ln in r_lines if ' 270 ' in f' {ln} ' or ln.endswith(' 270')
    ]
    assert len(r_270) == 2, r_270
    c_lines = [ln for ln in lines if ln.startswith('C')]
    c_220u = [ln for ln in c_lines if ' 220u' in ln]
    assert len(c_220u) == 2, c_220u

    # LTP grid leaks: two 1Meg (R_g1A, R_g1B) + two 470k (R_g2a, R_g2b).
    r_1meg = [ln for ln in r_lines if ' 1Meg' in ln]
    assert len(r_1meg) == 2, r_1meg
    r_470k = [ln for ln in r_lines if ' 470k' in ln]
    assert len(r_470k) == 2, r_470k

    # OPT center-tap routed: OPT.PC must be on same net as B+ rail.
    opt_lines = [ln for ln in lines if ln.endswith('OPT_PP_6K6_8')]
    assert len(opt_lines) == 1, opt_lines
    opt_parts = opt_lines[0].split()
    assert len(opt_parts) == 7, opt_lines[0]
    opt_nodes = opt_parts[1:6]
    assert len(set(opt_nodes)) == 5, (
        f'OPT pins shorted: {opt_nodes}'
    )
    v_lines = [ln for ln in lines if ln.startswith('V')]
    v_bb_line = next(ln for ln in v_lines if ' 300' in ln)
    bplus_net = v_bb_line.split()[1]
    pc_net = opt_nodes[1]
    assert pc_net == bplus_net, (
        f'OPT.PC ({pc_net}) не на B+ rail ({bplus_net}): {opt_lines[0]}'
    )


@needs_kicad
@needs_ngspice
async def test_facade_tube_pp_amp_op_point_balanced_pp(
    tmp_path: Path,
) -> None:
    """DC op-point: обе 6П14П в active region, balanced; LTP splitter биазится корректно.

    Acceptance:
      * V_anode_q обеих ламп 6П14П ≈ B+ (OPT primary DCR small).
      * I_a_q per-tube ≈ 25-45 mA (6П14П PP 12W diss class A).
      * V_cathode_q ≈ 5-9 V (auto-bias I_a · R_k = 30mA · 270Ω ≈ 8V).
      * V_anode V2a ≈ V_anode V2b ±10% (balanced PP).
      * LTP splitter conducts: V_cathode_tail > 1V (R_tail · I_tail).
    """
    sch_path = _build_tube_pp_amp(tmp_path / 'tube_pp_amp.kicad_sch')
    netlist_path = await _export_netlist(
        sch_path, tmp_path / 'tube_pp_amp.cir',
    )

    simulator = NgspiceSimulator(_app_manager())
    result = await simulator.run(netlist_path, analysis=OpAnalysis())
    assert result.operating_points is not None, result

    nodes: dict[str, float] = {}
    for raw_key, value in result.operating_points.items():
        if raw_key.startswith('v(') and raw_key.endswith(')'):
            name = raw_key[2:-1].lstrip('/').lower()
            nodes[name] = value

    for node in (
        'plate2a', 'plate2b', 'cathode2a', 'cathode2b', 'cathode_tail',
    ):
        assert node in nodes, f'missing node {node}: {sorted(nodes)}'

    v_plate_a = nodes['plate2a']
    v_plate_b = nodes['plate2b']
    v_cath_a = nodes['cathode2a']
    v_cath_b = nodes['cathode2b']
    v_tail = nodes['cathode_tail']

    # 6П14П в active region: V_plate near B+, V_cath ~ 8V, I_a 20-50 mA.
    assert 270.0 <= v_plate_a <= 305.0, (
        f'V_plate2a_q out of range: {v_plate_a:.2f} V'
    )
    assert 270.0 <= v_plate_b <= 305.0, (
        f'V_plate2b_q out of range: {v_plate_b:.2f} V'
    )
    assert 4.0 <= v_cath_a <= 12.0, (
        f'V_cathode2a_q out of range: {v_cath_a:.2f} V'
    )
    assert 4.0 <= v_cath_b <= 12.0, (
        f'V_cathode2b_q out of range: {v_cath_b:.2f} V'
    )

    i_a_a_ma = v_cath_a / 0.270
    i_a_b_ma = v_cath_b / 0.270
    assert 20.0 <= i_a_a_ma <= 50.0, (
        f'I_a_q V2a out of target window: {i_a_a_ma:.2f} mA'
    )
    assert 20.0 <= i_a_b_ma <= 50.0, (
        f'I_a_q V2b out of target window: {i_a_b_ma:.2f} mA'
    )

    plate_mean = 0.5 * (v_plate_a + v_plate_b)
    plate_imbalance = abs(v_plate_a - v_plate_b) / plate_mean
    assert plate_imbalance < 0.10, (
        f'PP plate imbalance {plate_imbalance:.2%} > 10% '
        f'(V_plate_a={v_plate_a:.2f}, V_plate_b={v_plate_b:.2f})'
    )

    # LTP splitter conducts — V_cathode_tail > 1V (proves tube halves
    # carrying tail current через R_tail).
    assert v_tail > 1.0, (
        f'LTP splitter near cutoff: V_tail={v_tail:.3f} V '
        f'(< 1 V means I_tail < 0.2 mA, splitter starved)'
    )
