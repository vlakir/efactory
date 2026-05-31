"""T153 Phase A.2 acceptance: NFB SE two-stage tube amp.

Двухкаскадный SE на 6Н1П (driver, Valve:ECC81 unit 1) + 6П14П (output,
Valve:EL84) + OPT 5k:8Ω, с global voltage feedback из вторички OPT в
катод 1-го каскада через Rfb + Cfb_block (DC-block 10µF series).

**Spec consistency note (T153 Phase A.2).** Spec § Analyze C5 предложил
два варианта обработки multi-loop в NFB SE tube amp: (a) bypass cap на
V1.K «закорачивает local cathode loop в AC, оставляя global» либо (b)
graph analyzer heuristic выбирает global loop. Вариант (a) physically
ошибочен — bypass cap на V1.K закорачивает И global feedback (Rfb
arrives at V1.K, тот же узел). Поэтому фикстура реализует подход (b):
V1.K **unbypassed**, обе петли существуют топологически (local cathode
degeneration на V1 + global voltage feedback через OPT), graph analyzer
в Phase C выберет «long» global. Spec C5 будет уточнён follow-up'ом.

Топология (left → right):

  V_in (10 mV @ 1 kHz) → C_in (100 nF) → R_g1 (1 MΩ) ‖ V1.G (6Н1П);
  V1.K → R_k1 (1.5 kΩ) → GND (без bypass cap → NFB активен на всех f);
  V1.P → R_p1 (100 kΩ) → B+;
  V1.P → C_c (22 nF) → R_g2 (470 kΩ) ‖ V2.G (6П14П);
  V2.K → R_k2 (130 Ω) ‖ C_k2 (100 µF) → GND (стандартный bypass для V2);
  V2.G2 → B+ (screen rail);
  V2.P → OPT.P1; OPT.P2 → B+;
  OPT.S1 → R_load (8 Ω) → OPT.S2;
  OPT.S1 → C_fb_block (10 µF) → R_fb (4.7 kΩ) → V1.K (global NFB tap).

Acceptance:
  * netlist содержит X1 (6N1P) + X2 (6P14P) + X3 (OPT_SE_5K_8) и
    .include для всех трёх .lib файлов.
  * ngspice TRAN: V(/sec_a) AC swing > 0 (lamps усиливают; абсолютная
    величина зависит от точки операции, главное — non-zero).
  * NFB-action: closed-loop V(/sec_a)/V(/input) < open-loop (без Rfb).
    Здесь acceptance проверяет факт NFB-демпфирования (gain_with_nfb <
    gain_threshold), open-loop reference считается отдельным
    sub-fixture'ом или в Phase B PM-test'е.
  * ERC: 0 errors (cosmetic warnings — lib_symbol_mismatch OK).
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
from domain.simulation import TranAnalysis
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
_TUBE_6N1P_LIB = (
    _REPO_ROOT / 'data' / 'models' / 'tubes' / 'custom' / '6N1P.lib'
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
    / 'OPT_SE_5K_8.lib'
)


def _tube_6n1p() -> SpiceModel:
    return SpiceModel(
        id='6N1P',
        name='6Н1П',
        category=ComponentCategory.TUBE,
        subcategory='triode',
        source=ModelSource.CUSTOM,
        file_path=_TUBE_6N1P_LIB,
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


def _opt_se_5k_8() -> SpiceModel:
    return SpiceModel(
        id='OPT_SE_5K_8',
        name='OPT_SE_5K_8',
        category=ComponentCategory.TRANSFORMER,
        subcategory='opt',
        source=ModelSource.GENERIC,
        file_path=_OPT_LIB,
        subckt_pins=('P1', 'P2', 'S1', 'S2'),
    )


# Layout (mm, Y-down) на KiCad-стандартной сетке 1.27 mm. Расширение
# se-amp layout справа: 6Н1П driver занимает «старое» место 6P14P
# (X≈88.9), 6P14P сдвинут на ~33 mm right (X≈121.92), OPT и R_load
# дальше. Cfb_block + Rfb лежат СЛЕВА-ВНИЗУ относительно V_in (X≈40-53,
# Y=105), feedback wire идёт горизонтально на Y=101.6 к V1.K rail —
# не пересекает V_in / C_in / R_g1 (все выше Y=98).

# === B+ rail Y и plate1-wire Y (общие horiz lines) ===
_BPLUS_RAIL_Y = 58.42  # горизонталь B+: V_BB → ... → OPT.P2 stub end
_PLATE1_WIRE_Y = 78.74  # V1.P → C_c (горизонталь между V1 и C_c)

# === Stage 0: power supply, input source, flag ===
_V_BB_AT = (50.8, 63.5)  # V1 VDC: pin_minus@(50.8,58.42)→B+ rail
_GND_VBB_AT = (50.8, 73.66)
_V_IN_AT = (50.8, 88.9)  # V2 VSIN: pin_minus@(50.8,83.82)→C_in, pin_plus→GND
_GND_VIN_AT = (50.8, 97.79)
_FLG_AT = (45.72, 97.79)

# === Stage 1: 6Н1П driver ===
_C_IN_AT = (63.5, 83.82)  # rotation=90: pin_a@(59.69,83.82), pin_b@(67.31,83.82)
_R_G1_AT = (78.74, 93.98)  # 1Meg: pin_a@(78.74,97.79)→GND, pin_b@(78.74,90.17)=V1.G
_GND_RG1_AT = (78.74, 101.6)
# Valve:ECC81 unit 1 для 6Н1П (low-µ analog, см. facade.py:151).
# Pin positions относительно tube center (88.9, 88.9):
#   '6' (A=plate):  ( 0.0,  -10.16) → (88.9, 78.74)
#   '7' (G=grid):   (-7.62,   0.0)  → (81.28, 88.9)
#   '8' (K=cathode):(-2.54,  10.16) → (86.36, 99.06)
_TUBE1_AT = (88.9, 88.9)
_R_P1_AT = (88.9, 68.58)  # 100k plate load: pin_a@(88.9,72.39)→V1.P, pin_b@(88.9,64.77)→B+
_R_K1_AT = (86.36, 105.41)  # 1.5k unbypassed: pin_a@(86.36,109.22)→GND, pin_b@(86.36,101.6)→V1.K
_GND_RK1_AT = (86.36, 113.03)

# === Stage 1-2 coupling ===
_C_C_AT = (104.14, 78.74)  # rot=90 coupling 22nF: pin_a@(100.33,78.74), pin_b@(107.95,78.74)

# === Stage 2: 6P14P output ===
_R_G2_AT = (114.3, 93.98)  # 470k: pin_a@(114.3,97.79)→GND, pin_b@(114.3,90.17)=V2.G
_GND_RG2_AT = (114.3, 101.6)
# Valve:EL84 для 6П14П (как в se-amp). Pin positions от center (121.92, 88.9):
#   '2' (G1):     (-7.62, 1.27)  → (114.3, 90.17)
#   '3' (K_G3):   (-2.54, 8.89)  → (119.38, 97.79)
#   '7' (A=plate):( 0.0, -11.43) → (121.92, 77.47)
#   '9' (G2):     ( 7.62, -1.27) → (129.54, 87.63)
_TUBE2_AT = (121.92, 88.9)
_R_K2_AT = (119.38, 101.6)  # 130: pin_a@(119.38,105.41)→GND, pin_b@(119.38,97.79)=V2.K
_C_K2_AT = (129.54, 101.6)  # 100µ bypass: pin_a@(129.54,105.41)→GND, pin_b@(129.54,97.79)→K rail
_GND_RK2_AT = (119.38, 109.22)
_GND_CK2_AT = (129.54, 109.22)

# === Stage 2 → OPT ===
# Transformer_1P_1S (как в se-amp). От center (147.32, 72.39):
#   P1 (primary top, plate end): (-10.16, -5.08) → (137.16, 67.31)
#   P2 (primary bottom, B+ end): (-10.16,  5.08) → (137.16, 77.47)
#   S1 (secondary bottom, hot): ( 10.16,  5.08) → (157.48, 77.47)
#   S2 (secondary top, gnd):    ( 10.16, -5.08) → (157.48, 67.31)
_OPT_AT = (147.32, 72.39)
_BPLUS_RAIL_END_X = 147.32  # B+ rail end (= X of OPT center, для OPT.P2 stub)
_PLATE2_WIRE_Y = 67.31  # plate2 routes к OPT.P1 — Y=67.31 (выше B+ rail Y=58.42)
_R_LOAD_AT = (170.18, 81.28)  # 8Ω: pin_a@(170.18,85.09), pin_b@(170.18,77.47)=OPT.S1

# === Feedback network (Rfb + Cfb_block) ===
# Layout: размещены В НИЖНЕМ-ЛЕВОМ углу под V_in / C_in. AC chain:
#   OPT.S1 (label 'sec_a') ← label-merge → Cfb_block.pin_b →
#   wire → Rfb.pin_b → wire к V1.K rail (junction с R_k1.pin_b).
# Rfb + Cfb_block ориентированы ГОРИЗОНТАЛЬНО (rot=90), feedback wire
# идёт Y=101.6 horizontally — НЕ пересекает V_in/C_in/R_g1 (те выше).
_CFB_BLOCK_AT = (40.64, 101.6)  # rot=90 10µ: pin_a@(36.83,101.6), pin_b@(44.45,101.6)
_RFB_AT = (60.96, 101.6)  # rot=90 4.7k: pin_a@(57.15,101.6), pin_b@(64.77,101.6)


def _app_manager() -> SubprocessAppManager:
    return SubprocessAppManager(NativePlatformLayer())


def _build_nfb_se_amp(path: Path) -> Path:  # noqa: PLR0915
    sch = Schematic('nfb_se_amp_6n1p_6p14p')

    v_bb = sch.add_v_dc(value='250', at=_V_BB_AT)
    v_in = sch.add_v_ac(
        value='VSIN',
        at=_V_IN_AT,
        amplitude=0.010,
        frequency=1000.0,
    )
    c_in = sch.add_capacitor(value='100n', at=_C_IN_AT, rotation=90)
    r_g1 = sch.add_resistor(value='1Meg', at=_R_G1_AT)
    xv1 = sch.add_tube(
        spice_model=_tube_6n1p(),
        at=_TUBE1_AT,
        symbol='Valve:ECC81',
    )
    r_p1 = sch.add_resistor(value='100k', at=_R_P1_AT)
    r_k1 = sch.add_resistor(value='1.5k', at=_R_K1_AT)
    c_c = sch.add_capacitor(value='22n', at=_C_C_AT, rotation=90)
    r_g2 = sch.add_resistor(value='470k', at=_R_G2_AT)
    xv2 = sch.add_tube(
        spice_model=_tube_6p14p(),
        at=_TUBE2_AT,
        symbol='Valve:EL84',
    )
    r_k2 = sch.add_resistor(value='130', at=_R_K2_AT)
    c_k2 = sch.add_capacitor(value='100u', at=_C_K2_AT)
    xt1 = sch.add_transformer(
        spice_model=_opt_se_5k_8(),
        at=_OPT_AT,
        symbol='Device:Transformer_1P_1S',
    )
    r_load = sch.add_resistor(value='8', at=_R_LOAD_AT)

    c_fb = sch.add_capacitor(value='10u', at=_CFB_BLOCK_AT, rotation=90)
    r_fb = sch.add_resistor(value='4.7k', at=_RFB_AT, rotation=90)

    gnd_vbb = sch.add_ground(at=_GND_VBB_AT)
    gnd_vin = sch.add_ground(at=_GND_VIN_AT)
    gnd_rg1 = sch.add_ground(at=_GND_RG1_AT)
    gnd_rk1 = sch.add_ground(at=_GND_RK1_AT)
    gnd_rg2 = sch.add_ground(at=_GND_RG2_AT)
    gnd_rk2 = sch.add_ground(at=_GND_RK2_AT)
    gnd_ck2 = sch.add_ground(at=_GND_CK2_AT)
    flg = sch.add_pwr_flag(at=_FLG_AT, rotation=180)

    # === B+ rail (Y=58.42) ===
    # V_BB.pin_minus → горизонталь rail → X=_BPLUS_RAIL_END_X (= OPT
    # центр). Junction'ы на rail где сходятся stub'ы: R_p1.pin_b (X=88.9),
    # OPT.P2 stub end (X=147.32), V2.G2 stub (X=129.54).
    sch.connect(
        v_bb.pin_minus,
        Position(x_mm=_BPLUS_RAIL_END_X, y_mm=_BPLUS_RAIL_Y),
    )
    # R_p1.pin_b (plate load top) → rail. R_p1.pin_b = (88.9, 64.77).
    # Wire (88.9, 64.77) → (88.9, 58.42) vertical stub.
    sch.connect(r_p1.pin_b, Position(x_mm=88.9, y_mm=_BPLUS_RAIL_Y))
    sch.junction(at=(88.9, _BPLUS_RAIL_Y))  # T: R_p1 stub on rail
    # V2.G2 screen stub: (129.54, 87.63) → (129.54, _BPLUS_RAIL_Y).
    sch.connect(
        xv2.pin('G2'),
        Position(x_mm=129.54, y_mm=_BPLUS_RAIL_Y),
    )
    sch.junction(at=(129.54, _BPLUS_RAIL_Y))  # T: G2 stub on rail
    # OPT.P2 stub L-route: rail (X=147.32) → DOWN to Y=77.47 → LEFT to P2.
    sch.connect(
        Position(x_mm=_BPLUS_RAIL_END_X, y_mm=_BPLUS_RAIL_Y),
        Position(x_mm=_BPLUS_RAIL_END_X, y_mm=77.47),
    )
    sch.connect(
        Position(x_mm=_BPLUS_RAIL_END_X, y_mm=77.47),
        xt1.pin('P2'),
    )

    # === Stage 1: V1.P plate connections ===
    # V1.P (88.9, 78.74) → R_p1.pin_a (88.9, 72.39): vertical stub.
    sch.connect(xv1.pin('P'), r_p1.pin_a)
    # V1.P (88.9, 78.74) → C_c.pin_a (100.33, 78.74): horizontal Y=78.74.
    # Junction at V1.P для T (plate + R_p1 + C_c).
    sch.connect(xv1.pin('P'), c_c.pin_a)
    sch.junction(at=xv1.pin("P"))

    # === Stage 1: V1.G grid (V_in → C_in → V1.G через R_g1 leak) ===
    sch.connect(v_in.pin_minus, c_in.pin_a)
    # C_in.pin_b (67.31, 83.82) → V1.G (81.28, 88.9). Manhattan corner
    # = (67.31, 88.9) или (81.28, 83.82). Возьмём первый: down then right.
    # Wait facade.connect делает «вертикаль → горизонталь» от start. От
    # start=(67.31, 83.82) к end=(81.28, 88.9): corner=(67.31, 88.9),
    # затем (67.31, 88.9)→(81.28, 88.9).
    sch.connect(c_in.pin_b, xv1.pin('G'))
    # R_g1.pin_b (78.74, 90.17) → V1.G (81.28, 88.9). Corner=(78.74, 88.9).
    sch.connect(r_g1.pin_b, xv1.pin('G'))
    sch.junction(at=xv1.pin("G"))  # T: V1.G + C_in wire + R_g1 wire

    # === Stage 1: V1.K cathode (R_k1 + Rfb feedback arrive) ===
    # V1.K (86.36, 99.06) → R_k1.pin_b (86.36, 101.6): vertical short.
    sch.connect(xv1.pin('K'), r_k1.pin_b)
    # Feedback arrives at V1.K rail: R_fb.pin_b (64.77, 101.6) →
    # R_k1.pin_b (86.36, 101.6): horizontal Y=101.6.
    sch.connect(r_fb.pin_b, r_k1.pin_b)
    sch.junction(at=r_k1.pin_b)  # T: V1.K wire + R_k1 + R_fb feedback

    # === Stage 1 → 2 coupling: C_c → R_g2 → V2.G ===
    # C_c.pin_b (107.95, 78.74) → V2.G (114.3, 90.17). Corner.
    sch.connect(c_c.pin_b, xv2.pin('G'))
    # R_g2.pin_b (114.3, 90.17) → V2.G (114.3, 90.17): same point.
    # Actually R_g2.pin_b is AT V2.G (overlap). Junction там.
    sch.junction(at=xv2.pin("G"))  # T: V2.G + R_g2 + C_c wire

    # === Stage 2: V2.K (cathode bypass standard) ===
    # V2.K (119.38, 97.79) ≡ R_k2.pin_b (119.38, 97.79) — overlap.
    # Wire к C_k2.pin_b (129.54, 97.79): horizontal Y=97.79.
    sch.connect(xv2.pin('K'), c_k2.pin_b)
    sch.junction(at=xv2.pin("K"))  # T: V2.K + R_k2 + C_k2 wire

    # === Stage 2: V2.P → OPT.P1 ===
    # V2.P (121.92, 77.47) → corner (121.92, 67.31) → OPT.P1 (137.16, 67.31).
    sch.connect(
        xv2.pin('P'),
        Position(x_mm=121.92, y_mm=_PLATE2_WIRE_Y),
    )
    sch.connect(
        Position(x_mm=121.92, y_mm=_PLATE2_WIRE_Y),
        xt1.pin('P1'),
    )

    # === Secondary loop: OPT.S1 → R_load → OPT.S2 ===
    sch.connect(xt1.pin('S1'), r_load.pin_b)
    # S2 (157.48, 67.31) → corner (170.18, 67.31) → R_load.pin_a (170.18, 85.09).
    sch.connect(
        xt1.pin('S2'),
        Position(x_mm=170.18, y_mm=67.31),
    )
    sch.connect(
        Position(x_mm=170.18, y_mm=67.31),
        r_load.pin_a,
    )

    # === Feedback chain: OPT.S1 (label 'sec_a') ← C_fb_block ← R_fb → V1.K
    # Под rotation=90 pin_a соответствует local (0, 3.81), pin_b — local
    # (0, -3.81). После CCW 90° rotation:
    #   C_fb at (40.64, 101.6): pin_a = (36.83, 101.6), pin_b = (44.45, 101.6).
    #   R_fb at (60.96, 101.6): pin_a = (57.15, 101.6), pin_b = (64.77, 101.6).
    # Series LEFT→RIGHT:
    #   sec_a label → C_fb.pin_a (X=36.83) [labeled]
    #   C_fb.pin_b (X=44.45) ─wire─ R_fb.pin_a (X=57.15) [middle]
    #   R_fb.pin_b (X=64.77) ─wire─ V1.K rail (X=86.36) [см. V1.K секцию выше]
    sch.connect(c_fb.pin_b, r_fb.pin_a)

    # === GND-стержни ===
    sch.connect(v_bb.pin_plus, gnd_vbb.pin)
    sch.connect(v_in.pin_plus, gnd_vin.pin)
    sch.connect(r_g1.pin_a, gnd_rg1.pin)
    sch.connect(r_k1.pin_a, gnd_rk1.pin)
    sch.connect(r_g2.pin_a, gnd_rg2.pin)
    sch.connect(r_k2.pin_a, gnd_rk2.pin)
    sch.connect(c_k2.pin_a, gnd_ck2.pin)
    sch.connect(flg.pin, v_in.pin_plus)

    # === SPICE-trace labels ===
    sch.label('input', at=v_in.pin_minus)
    sch.label('plate1', at=xv1.pin('P'))
    sch.label('plate2', at=xv2.pin('P'))
    sch.label('sec_a', at=xt1.pin('S1'))
    sch.label('sec_b', at=xt1.pin('S2'))
    # Feedback tap (C_fb_block.pin_a) labelled 'sec_a' → net merge с OPT.S1.
    sch.label('sec_a', at=c_fb.pin_a)

    # .tran с uic — SE-amp pattern: t_stop=80ms, t_start=10ms. С OPT
    # primary Lp=50H + Rp_dcr=200Ω имеем τ_L≈250ms; за 80ms ток в Lp
    # вырастает только до ~27% steady-state — тубы ещё не «сжаты»
    # OPT saturation'ом, AC behaviour корректен. Длиннее transient
    # (>150ms) приводит к нефизичному drift bias из-за Lp ramp.
    sch.spice_directive('.tran 10u 80m 10m uic', at=(50.8, 122.0))

    return sch.save(path)


async def _export_netlist(schematic_path: Path, netlist_path: Path) -> Path:
    exporter = KicadCliSchematicExporter(_app_manager())
    return await exporter.export_spice_netlist(schematic_path, netlist_path)


@needs_kicad
async def test_facade_nfb_se_amp_writes_three_subckt_includes(
    tmp_path: Path,
) -> None:
    """Netlist содержит X1 (6N1P) + X2 (6P14P) + X3 (OPT) и три .include."""
    sch_path = _build_nfb_se_amp(tmp_path / 'nfb_se_amp.kicad_sch')
    netlist = await _export_netlist(sch_path, tmp_path / 'nfb_se_amp.cir')
    text = netlist.read_text()

    x_lines = {
        ln.split()[0]: ln.split()[-1]
        for ln in text.splitlines()
        if ln.startswith('X')
    }
    # X1=6N1P, X2=6P14P, X3=OPT (auto-numbered by facade в порядке add_tube/
    # add_transformer; смотри _build_nfb_se_amp).
    assert x_lines.get('X1') == '6N1P', f'X1 missing or wrong:\n{text}'
    assert x_lines.get('X2') == '6P14P', f'X2 missing or wrong:\n{text}'
    assert x_lines.get('X3') == 'OPT_SE_5K_8', (
        f'X3 missing or wrong:\n{text}'
    )

    assert '6N1P.lib' in text, text
    assert '6P14P.lib' in text, text
    assert 'OPT_SE_5K_8.lib' in text, text


@needs_kicad
@needs_ngspice
async def test_facade_nfb_se_amp_tran_settles_and_amplifies(
    tmp_path: Path,
) -> None:
    """Двухкаскадный NFB SE — TRAN settles, V(/sec_a) показывает AC swing."""
    sch_path = _build_nfb_se_amp(tmp_path / 'nfb_se_amp.kicad_sch')
    netlist = await _export_netlist(sch_path, tmp_path / 'nfb_se_amp.cir')
    simulator = NgspiceSimulator(_app_manager())

    result = await simulator.run(
        netlist,
        TranAnalysis(t_step=1e-5, t_stop=80e-3),
    )
    assert result.time_series is not None
    ts = result.time_series

    # Берём последние 20% точек — после bias settling.
    n = len(ts.time)
    skip = int(n * 0.8)
    vin = ts.traces['v(/input)'][skip:]
    vsec = ts.traces['v(/sec_a)'][skip:]

    vin_pp = max(vin) - min(vin)
    vsec_pp = max(vsec) - min(vsec)
    assert vin_pp > 0.005, f'Input swing too low: {vin_pp}'
    # NFB снижает gain: ожидаем closed-loop ~ 3-5 V/V (β·AOL≈10 → AOL/11
    # от open-loop ~42 V/V). Acceptance: secondary swing **>** input
    # swing (>1× — то есть schematic фактически усиливает), и **<** 20×
    # open-loop (NFB активна, не отключена). 20× — soft upper bound с
    # запасом на model variance.
    gain = vsec_pp / vin_pp
    assert gain > 1.0, (
        f'NFB amp gain {gain:.2f}× ниже 1 — schematic неверен (нет '
        f'усиления / NFB замкнул сигнал)'
    )
    assert gain < 20.0, (
        f'NFB amp gain {gain:.2f}× выше 20 — NFB не работает / Rfb '
        f'разорван'
    )
