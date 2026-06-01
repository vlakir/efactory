"""T027 Phase B acceptance: Two-stage all-triode line preamp on 6Н2П.

Stage 1 — common-cathode voltage amplifier (Valve:ECC83 unit 1 половина
6Н2П): R_p1=100kΩ plate load, R_k1=1.5kΩ ‖ C_k1=22µF auto-bias с bypass.
Stage 2 — cathode follower (Valve:ECC83B unit 2 половина 6Н2П):
V1B.P → directly к B+ (НЕТ plate load — CF defining feature), V1B.K
→ R_k2=33kΩ cathode load **без bypass** (CF inherently degenerative).
C_out=0.47µF coupling к assumed next-stage Rin=100kΩ.

Топология (left → right):

  V_in (VSIN 10 mV @ 1 kHz) → C_in (100 nF) → R_g1 (1 MΩ) ‖ V1A.G;
  V1A.K → R_k1 (1.5 kΩ) ‖ C_k1 (22 µF) → GND (Stage 1 auto-bias);
  V1A.P → R_p1 (100 kΩ) → B+;
  V1A.P → C_couple (47 nF) → R_g2 (470 kΩ) ‖ V1B.G;
  V1B.P → B+ (Cathode-follower: NO plate load);
  V1B.K → R_k2 (33 kΩ) → GND (CF cathode load, NO bypass);
  V1B.K → C_out (0.47 µF) → R_load (100 kΩ) → GND.

Acceptance:
  * netlist содержит X1 + X2 (6N2P pair, same SUBCKT) + .include 6N2P.lib.
  * Topology asserts: R_p1=100k (Stage 1 plate load), R_k1=1.5k + C_k1=22u
    (Stage 1 bypass), Stage 2 — NO plate load для V1B (V1B.P напрямую
    к B+ rail), R_k2=33k без C_k2 (CF degeneration intentional).
  * ngspice op-point: V1A в active region (V_plate_q ~100-200V для R_p=100k,
    I_a ~1mA), V1B активен (V_plate ≈ B+, V_K positive для CF auto-bias).
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


# Layout (mm, Y-down, KiCad grid 1.27 mm). Two-stage cascade на одной
# горизонтали Y=88.9: V1A (Stage 1 CC) at X=88.9, V1B (Stage 2 CF) at
# X=121.92. Минимально расширяет SE-amp layout.

_BPLUS_RAIL_Y = 58.42
_PLATE1_WIRE_Y = 78.74  # V1A.P → C_couple (Stage 1 plate horizontal)

# === Stage 0: supplies & input ===
_V_BB_AT = (50.8, 63.5)
_GND_VBB_AT = (50.8, 73.66)
_V_IN_AT = (50.8, 88.9)
_GND_VIN_AT = (50.8, 97.79)
_FLG_AT = (45.72, 97.79)

# === Stage 1: 6Н2П common-cathode (V1A = ECC83 unit 1) ===
_C_IN_AT = (63.5, 83.82)
_R_G1_AT = (78.74, 93.98)  # 1Meg: pin_a@(78.74,97.79)→GND, pin_b@(78.74,90.17)→V1A.G
_GND_RG1_AT = (78.74, 101.6)
# V1A pin positions от center (88.9, 88.9):
#   '6' (P):  (88.9, 78.74)
#   '7' (G):  (81.28, 88.9)
#   '8' (K):  (86.36, 99.06)
_TUBE1A_AT = (88.9, 88.9)
_R_P1_AT = (88.9, 68.58)  # 100k: pin_a@(88.9,72.39)→V1A.P, pin_b@(88.9,64.77)→rail
_R_K1_AT = (86.36, 105.41)  # 1.5k: pin_a@(86.36,109.22)→GND, pin_b@(86.36,101.6)→V1A.K
_C_K1_AT = (96.52, 105.41)  # 22µ bypass: pin_a→GND, pin_b→K rail Y=101.6
_GND_RK1_AT = (86.36, 113.03)
_GND_CK1_AT = (96.52, 113.03)

# === Stage 1-2 coupling ===
_C_COUPLE_AT = (104.14, 78.74)  # rot=90: pin_a@(100.33,78.74), pin_b@(107.95,78.74)

# === Stage 2: 6Н2П cathode follower (V1B = ECC83B unit 2) ===
_R_G2_AT = (114.3, 93.98)  # 470k: pin_a→GND, pin_b@(114.3,90.17)→V1B.G
_GND_RG2_AT = (114.3, 101.6)
# V1B unit 2 pin positions от center (121.92, 88.9):
#   '1' (P):  (121.92, 78.74)
#   '2' (G):  (114.3, 88.9)
#   '3' (K):  (119.38, 99.06)
_TUBE1B_AT = (121.92, 88.9)
# NO R_p2 — Cathode Follower: V1B.P → directly к B+ rail.
_R_K2_AT = (119.38, 109.22)  # 33k CF cathode load, no bypass: pin_a@(119.38,113.03)→GND, pin_b@(119.38,105.41)→V1B.K rail
_GND_RK2_AT = (119.38, 116.84)

# === Output coupling + load ===
_C_OUT_AT = (132.08, 105.41)  # rot=90: pin_a@(128.27,105.41), pin_b@(135.89,105.41)
_R_LOAD_AT = (142.24, 109.22)  # 100k assumed next-stage Rin: pin_a@(142.24,113.03)→GND, pin_b@(142.24,105.41)→C_out output
_GND_RLOAD_AT = (142.24, 116.84)

# SPICE directive node.
_SPICE_DIRECTIVE_AT = (50.8, 125.0)


def _app_manager() -> SubprocessAppManager:
    return SubprocessAppManager(NativePlatformLayer())


def _build_tube_line_preamp(path: Path) -> Path:  # noqa: PLR0915
    """Builds tube-line-preamp reference fixture.

    Imported by `scripts/regenerate-templates.py` to bake the shipping
    template (`data/templates/tube-line-preamp/`).
    """
    sch = Schematic('tube_line_preamp_6n2p')

    # === Supplies & input ===
    v_bb = sch.add_v_dc(value='250', at=_V_BB_AT)
    v_in = sch.add_v_ac(
        value='VSIN',
        at=_V_IN_AT,
        amplitude=0.010,
        frequency=1000.0,
    )
    flg = sch.add_pwr_flag(at=_FLG_AT, rotation=180)

    # === Stage 1: CC ===
    c_in = sch.add_capacitor(value='100n', at=_C_IN_AT, rotation=90)
    r_g1 = sch.add_resistor(value='1Meg', at=_R_G1_AT)
    xv1a = sch.add_tube(
        spice_model=_tube_6n2p(),
        at=_TUBE1A_AT,
        symbol='Valve:ECC83',
    )
    r_p1 = sch.add_resistor(value='100k', at=_R_P1_AT)
    r_k1 = sch.add_resistor(value='1.5k', at=_R_K1_AT)
    c_k1 = sch.add_capacitor(value='22u', at=_C_K1_AT)

    # === Stage 1-2 coupling ===
    c_couple = sch.add_capacitor(value='47n', at=_C_COUPLE_AT, rotation=90)

    # === Stage 2: CF ===
    r_g2 = sch.add_resistor(value='470k', at=_R_G2_AT)
    xv1b = sch.add_tube(
        spice_model=_tube_6n2p(),
        at=_TUBE1B_AT,
        symbol='Valve:ECC83B',
    )
    r_k2 = sch.add_resistor(value='33k', at=_R_K2_AT)

    # === Output ===
    c_out = sch.add_capacitor(value='0.47u', at=_C_OUT_AT, rotation=90)
    r_load = sch.add_resistor(value='100k', at=_R_LOAD_AT)

    # === Grounds ===
    gnd_vbb = sch.add_ground(at=_GND_VBB_AT)
    gnd_vin = sch.add_ground(at=_GND_VIN_AT)
    gnd_rg1 = sch.add_ground(at=_GND_RG1_AT)
    gnd_rk1 = sch.add_ground(at=_GND_RK1_AT)
    gnd_ck1 = sch.add_ground(at=_GND_CK1_AT)
    gnd_rg2 = sch.add_ground(at=_GND_RG2_AT)
    gnd_rk2 = sch.add_ground(at=_GND_RK2_AT)
    gnd_rload = sch.add_ground(at=_GND_RLOAD_AT)

    # === B+ rail (Y=58.42) ===
    # V_BB.pin_minus → горизонталь rail. Junctions: R_p1.pin_b (88.9),
    # V1B.P stub end (X=121.92, via plate2 wire).
    _bplus_rail_end_x = 121.92
    sch.connect(
        v_bb.pin_minus,
        Position(x_mm=_bplus_rail_end_x, y_mm=_BPLUS_RAIL_Y),
    )
    sch.connect(r_p1.pin_b, Position(x_mm=88.9, y_mm=_BPLUS_RAIL_Y))
    sch.junction(at=(88.9, _BPLUS_RAIL_Y))
    # V1B.P (121.92, 78.74) → rail (121.92, 58.42) — Cathode Follower direct
    # plate-to-supply (NO plate load).
    sch.connect(
        xv1b.pin('P'),
        Position(x_mm=_bplus_rail_end_x, y_mm=_BPLUS_RAIL_Y),
    )
    sch.junction(at=(_bplus_rail_end_x, _BPLUS_RAIL_Y))

    # === Power-flag → V_in.pin_plus ===
    sch.connect(flg.pin, v_in.pin_plus)

    # === Stage 1 grid (V_in → C_in → R_g1 + V1A.G) ===
    sch.connect(v_in.pin_minus, c_in.pin_a)
    sch.connect(c_in.pin_b, Position(x_mm=67.31, y_mm=88.9))
    sch.connect(Position(x_mm=67.31, y_mm=88.9), xv1a.pin('G'))
    sch.connect(r_g1.pin_b, Position(x_mm=78.74, y_mm=88.9))
    sch.junction(at=(78.74, 88.9))

    # === Stage 1 plate (V1A.P → R_p1.pin_a + C_couple.pin_a) ===
    sch.connect(xv1a.pin('P'), r_p1.pin_a)
    sch.connect(xv1a.pin('P'), c_couple.pin_a)
    sch.junction(at=xv1a.pin('P'))

    # === Stage 1 cathode (V1A.K → R_k1 + C_k1) ===
    # V1A.K (86.36, 99.06) → cathode rail Y=101.6 → R_k1.pin_b + C_k1.pin_b.
    _cathode1_rail_y = 101.6
    sch.connect(xv1a.pin('K'), Position(x_mm=86.36, y_mm=_cathode1_rail_y))
    sch.junction(at=(86.36, _cathode1_rail_y))
    sch.connect(
        Position(x_mm=86.36, y_mm=_cathode1_rail_y),
        c_k1.pin_b,
    )
    # R_k1.pin_b (86.36, 101.6) — overlaps the rail endpoint at X=86.36.

    # === Stage 2 grid (C_couple → R_g2 + V1B.G) ===
    sch.connect(
        c_couple.pin_b,
        Position(x_mm=114.3, y_mm=78.74),
    )
    sch.connect(
        Position(x_mm=114.3, y_mm=78.74),
        Position(x_mm=114.3, y_mm=88.9),
    )
    sch.connect(
        Position(x_mm=114.3, y_mm=88.9),
        xv1b.pin('G'),
    )
    sch.connect(r_g2.pin_b, Position(x_mm=114.3, y_mm=90.17))
    sch.junction(at=(114.3, 90.17))

    # === Stage 2 cathode (V1B.K → R_k2 → GND; V1B.K → C_out → R_load → GND) ===
    # V1B.K (119.38, 99.06) → cathode2 rail Y=105.41 (lower than Stage 1
    # cathode rail to avoid interference) → R_k2.pin_b + C_out.pin_a.
    _cathode2_rail_y = 105.41
    sch.connect(xv1b.pin('K'), Position(x_mm=119.38, y_mm=_cathode2_rail_y))
    sch.junction(at=(119.38, _cathode2_rail_y))
    # R_k2.pin_b (119.38, 105.41) — overlaps cathode2 rail endpoint.
    # C_out.pin_a (128.27, 105.41) — same Y level, horizontal wire east.
    sch.connect(
        Position(x_mm=119.38, y_mm=_cathode2_rail_y),
        c_out.pin_a,
    )

    # === Output (C_out → R_load → GND) ===
    sch.connect(c_out.pin_b, r_load.pin_b)
    sch.connect(r_load.pin_a, gnd_rload.pin)

    # === Ground hookups ===
    sch.connect(v_bb.pin_plus, gnd_vbb.pin)
    sch.connect(v_in.pin_plus, gnd_vin.pin)
    sch.connect(r_g1.pin_a, gnd_rg1.pin)
    sch.connect(r_k1.pin_a, gnd_rk1.pin)
    sch.connect(c_k1.pin_a, gnd_ck1.pin)
    sch.connect(r_g2.pin_a, gnd_rg2.pin)
    sch.connect(r_k2.pin_a, gnd_rk2.pin)

    # === SPICE labels ===
    sch.label('input', at=v_in.pin_minus)
    sch.label('grid1', at=xv1a.pin('G'))
    sch.label('plate1', at=xv1a.pin('P'))
    sch.label('cathode1', at=xv1a.pin('K'))
    sch.label('grid2', at=xv1b.pin('G'))
    sch.label('plate2', at=xv1b.pin('P'))
    sch.label('cathode2', at=xv1b.pin('K'))
    sch.label('output', at=c_out.pin_b)

    sch.spice_directive('.op', at=_SPICE_DIRECTIVE_AT)

    return sch.save(path)


async def _export_netlist(schematic_path: Path, netlist_path: Path) -> Path:
    exporter = KicadCliSchematicExporter(_app_manager())
    return await exporter.export_spice_netlist(schematic_path, netlist_path)


@needs_kicad
async def test_facade_tube_line_preamp_writes_model_includes(
    tmp_path: Path,
) -> None:
    """Netlist contains X1+X2 (6N2P pair, same SUBCKT) + .include 6N2P.lib."""
    sch_path = _build_tube_line_preamp(tmp_path / 'tube_line_preamp.kicad_sch')
    netlist = await _export_netlist(sch_path, tmp_path / 'tube_line_preamp.cir')
    text = netlist.read_text()

    x_lines = [ln for ln in text.splitlines() if ln.startswith('X')]
    assert len(x_lines) == 2, (
        f'expected 2 X-instances (V1A CC + V1B CF), got {len(x_lines)}: {x_lines}'
    )
    for ln in x_lines:
        assert ln.endswith('6N2P'), ln

    assert '6N2P.lib' in text, text


@needs_kicad
async def test_facade_tube_line_preamp_topology(tmp_path: Path) -> None:
    """Verify CC + CF topology в netlist (CF distinctive: NO plate load V1B)."""
    sch_path = _build_tube_line_preamp(tmp_path / 'tube_line_preamp.kicad_sch')
    netlist = await _export_netlist(sch_path, tmp_path / 'tube_line_preamp.cir')
    lines = netlist.read_text().splitlines()

    # Stage 1: R_p1 = 100k (plate load), R_k1 = 1.5k + C_k1 = 22µ.
    r_lines = [ln for ln in lines if ln.startswith('R')]
    assert any(' 100k' in ln for ln in r_lines), 'no 100k R_p1 plate load'
    assert any(' 1.5k' in ln for ln in r_lines), 'no 1.5k R_k1'
    c_lines = [ln for ln in lines if ln.startswith('C')]
    assert any(' 22u' in ln for ln in c_lines), 'no 22µ C_k1 bypass'

    # Stage 2 CF defining property: NO plate load для V1B — V1B.P directly
    # на B+ rail. В netlist: V1B X-instance имеет P-node == B+ net.
    v_lines = [ln for ln in lines if ln.startswith('V')]
    v_bb_line = next(ln for ln in v_lines if ' 250' in ln)
    bplus_net = v_bb_line.split()[1]

    # Find V1B instance (second X line OR by /plate2 label).
    x_lines = [ln for ln in lines if ln.startswith('X') and ln.endswith('6N2P')]
    # X<ref> <P_node> <G_node> <K_node> 6N2P (3 pins).
    v1b_line = next(ln for ln in x_lines if '/plate2' in ln or '/grid2' in ln)
    v1b_parts = v1b_line.split()
    v1b_p_node = v1b_parts[1]
    assert v1b_p_node == bplus_net, (
        f'V1B.P not on B+ rail (CF requires direct supply); '
        f'V1B.P={v1b_p_node}, B+={bplus_net}, line={v1b_line}'
    )

    # Stage 2 R_k2 = 33k (CF cathode load).
    assert any(' 33k' in ln for ln in r_lines), 'no 33k R_k2 CF cathode load'

    # NO C_k2 bypass для CF — count 22µ caps should be exactly 1 (C_k1
    # for Stage 1 only).
    c_22u = [ln for ln in c_lines if ' 22u' in ln]
    assert len(c_22u) == 1, (
        f'expected exactly 1× 22µ (C_k1 only — CF has no bypass), '
        f'got: {c_22u}'
    )


@needs_kicad
@needs_ngspice
async def test_facade_tube_line_preamp_op_point_active(
    tmp_path: Path,
) -> None:
    """DC op-point: V1A в active region, V1B (CF) — V_K positive.

    Acceptance:
      * V1A.P (plate1) ≈ 100-200V (Stage 1 CC: V_a = V_BB - I_a · R_p1,
        I_a ≈ 0.5-1.5 mA → V_a ≈ 100-200V).
      * V1A.K (cathode1) ≈ 1-3V (auto-bias).
      * V1B.P (plate2) ≈ B+ (CF — direct supply).
      * V1B.K (cathode2) ≈ 30-100V positive (CF auto-bias через large R_k2).
      * V_grid_q (grid1, grid2) близко к 0 (capacitor-coupled inputs).
    """
    sch_path = _build_tube_line_preamp(tmp_path / 'tube_line_preamp.kicad_sch')
    netlist_path = await _export_netlist(
        sch_path, tmp_path / 'tube_line_preamp.cir',
    )

    simulator = NgspiceSimulator(_app_manager())
    result = await simulator.run(netlist_path, analysis=OpAnalysis())
    assert result.operating_points is not None, result

    nodes: dict[str, float] = {}
    for raw_key, value in result.operating_points.items():
        if raw_key.startswith('v(') and raw_key.endswith(')'):
            name = raw_key[2:-1].lstrip('/').lower()
            nodes[name] = value

    for node in ('plate1', 'cathode1', 'plate2', 'cathode2'):
        assert node in nodes, f'missing node {node}: {sorted(nodes)}'

    v_plate1 = nodes['plate1']
    v_cath1 = nodes['cathode1']
    v_plate2 = nodes['plate2']
    v_cath2 = nodes['cathode2']

    # Stage 1 CC: V_a_q in active region (not cutoff/saturation).
    assert 80.0 <= v_plate1 <= 220.0, (
        f'V_plate1 (Stage 1 CC) out of active region: {v_plate1:.2f} V '
        f'(expected 100-200V for V_BB=250, R_p=100k, I_a≈0.5-1.5mA)'
    )
    assert 0.5 <= v_cath1 <= 5.0, (
        f'V_cathode1 (Stage 1 auto-bias) implausible: {v_cath1:.2f} V'
    )

    # Stage 2 CF: V_plate2 ≈ B+ (no plate load), V_cathode positive
    # large value (CF auto-bias через R_k2=33k).
    assert 245.0 <= v_plate2 <= 250.0, (
        f'V_plate2 (CF — direct supply) not at B+: {v_plate2:.2f} V '
        f'(expected ≈ 250V)'
    )
    assert 30.0 <= v_cath2 <= 150.0, (
        f'V_cathode2 (CF auto-bias) out of range: {v_cath2:.2f} V '
        f'(expected 30-100V for I_a·R_k2 with R_k=33k)'
    )
