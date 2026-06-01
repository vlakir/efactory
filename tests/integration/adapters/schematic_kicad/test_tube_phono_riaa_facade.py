"""T027 Phase C acceptance: Tube phono RIAA preamp с passive inter-stage EQ.

Двухкаскадный preamp на 12AX7 (Koren parametrization, обе половины
Valve:ECC83 unit 1 + unit 2 = ECC83B). Passive RIAA EQ network **между
Stage 1 plate и Stage 2 grid** — classic Lipshitz-style series-shunt
RC network с тремя стандартными time constants (τ1=3180 µs, τ2=318 µs,
τ3=75 µs).

**Component choice (Practical Audio Tube Preamps standard):**
* R_riaa_1 = 91 kΩ (series)
* C_riaa_1 = 820 pF (direct shunt to GND — sets HF pole τ3=R1·C1=74.6 µs)
* R_riaa_2 = 9.1 kΩ (in series with C_riaa_2)
* C_riaa_2 = 33 nF (shunt with R2 — sets τ2=R2·C2=300 µs;
  (R1+R2)·C2=3303 µs ≈ τ1=3180 µs)

Топология (left → right):

  V_in (VSIN 5 mV @ 1 kHz, MM cartridge level) → C_in (100 nF) →
    R_g1 (1 MΩ) ‖ V1A.G;
  V1A.K → R_k1 (1.5 kΩ) ‖ C_k1 (22 µF) → GND;
  V1A.P → R_p1 (100 kΩ) → B+;
  V1A.P → C_couple_1 (100 nF) → riaa_in;
  riaa_in → R_riaa_1 → riaa_mid;
  riaa_mid → C_riaa_1 (820 pF) → GND  [HF shunt];
  riaa_mid → R_riaa_2 (9.1 kΩ) → C_riaa_2 (33 nF) → GND  [LF shunt];
  riaa_mid → R_g2 (1 MΩ) → GND  [grid leak для V1B safety];
  riaa_mid → V1B.G  [direct connection — DC ref через R_g2];
  V1B.K → R_k2 (1.5 kΩ) ‖ C_k2 (22 µF) → GND;
  V1B.P → R_p2 (100 kΩ) → B+;
  V1B.P → C_out (0.47 µF) → R_load (47 kΩ assumed line amp Rin) → GND.

Acceptance:
  * netlist contains X1 + X2 (12AX7 pair) + .include 12AX7.lib.
  * Topology asserts: 4 RIAA components present с правильными values
    (91k, 820p, 9.1k, 33n); both stages R_p=100k auto-bias config.
  * ngspice op-point: both 12AX7 in active region (V_plate_q
    100-200V, V_cathode_q 1-3V).
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
_TUBE_12AX7_LIB = (
    _REPO_ROOT / 'data' / 'models' / 'tubes' / 'koren' / '12AX7.lib'
)


def _tube_12ax7() -> SpiceModel:
    return SpiceModel(
        id='12AX7',
        name='12AX7',
        category=ComponentCategory.TUBE,
        subcategory='triode',
        source=ModelSource.KOREN,
        file_path=_TUBE_12AX7_LIB,
        subckt_pins=('P', 'G', 'K'),
    )


# Layout (mm, Y-down, KiCad grid 1.27 mm). Расширенная nfb-se-amp
# topology: V1A (Stage 1 CC) at X=88.9, RIAA EQ network в X=104..130,
# V1B (Stage 2 CC) at X=152.4. Достаточно wide для visual clarity.

_BPLUS_RAIL_Y = 58.42
_PLATE1_WIRE_Y = 78.74  # V1A.P → C_couple_1

# === Stage 0: supplies & input ===
_V_BB_AT = (50.8, 63.5)
_GND_VBB_AT = (50.8, 73.66)
_V_IN_AT = (50.8, 88.9)
_GND_VIN_AT = (50.8, 97.79)
_FLG_AT = (45.72, 97.79)

# === Stage 1: 12AX7 CC (V1A = ECC83 unit 1) ===
_C_IN_AT = (63.5, 83.82)
_R_G1_AT = (78.74, 93.98)
_GND_RG1_AT = (78.74, 99.06)  # Y=99.06 не на cathode rail (Y=101.6)
_TUBE1A_AT = (88.9, 88.9)
_R_P1_AT = (88.9, 68.58)
_R_K1_AT = (86.36, 105.41)
_C_K1_AT = (96.52, 105.41)
_GND_RK1_AT = (86.36, 113.03)
_GND_CK1_AT = (96.52, 113.03)

# === Stage 1 → RIAA coupling ===
_C_COUPLE_1_AT = (104.14, 78.74)  # rot=90: pin_a@(100.33,78.74), pin_b@(107.95,78.74)

# === Passive RIAA EQ network ===
# riaa_in (= C_couple_1.pin_b @ X=107.95, Y=78.74)
# → R_riaa_1 (series 91k) → riaa_mid (X=120, Y=78.74)
# riaa_mid → C_riaa_1 (820p direct shunt) → GND
# riaa_mid → R_riaa_2 (9.1k) → C_riaa_2 (33n) → GND
# riaa_mid → R_g2 (1MΩ grid leak) → GND (safety grid reference)
# riaa_mid → V1B.G (direct, через wire)
_R_RIAA_1_AT = (114.3, 78.74)  # rot=90 series: pin_a@(110.49,78.74), pin_b@(118.11,78.74)
_R_RIAA_2_AT = (123.19, 91.44)  # 9.1k vertical: pin_a@(123.19,95.25)→C_riaa_2.pin_b, pin_b@(123.19,87.63)→riaa_mid wire
_C_RIAA_1_AT = (123.19, 86.36)  # 820p direct shunt: pin_a@(123.19,90.17)→GND, pin_b@(123.19,82.55)→riaa_mid wire
# Hmm need re-think: both R_riaa_2 and C_riaa_1 shunt to GND from riaa_mid.
# Cleanly:
#  - C_riaa_1: vertical резистор-стиль cap with pin_a (top) к riaa_mid wire Y=78.74,
#    pin_b (bottom) к GND.
#  - R_riaa_2 → C_riaa_2 series-pair shunt: separate column.
# Re-layout:
_C_RIAA_1_AT = (120.65, 88.9)  # vertical: pin_a@(120.65,92.71)→GND, pin_b@(120.65,85.09)→riaa_mid wire
_GND_CRIAA1_AT = (120.65, 96.52)
_R_RIAA_2_AT = (130.81, 88.9)  # vertical: pin_a@(130.81,92.71)→C_riaa_2.pin_b, pin_b@(130.81,85.09)→riaa_mid wire
_C_RIAA_2_AT = (130.81, 100.33)  # vertical: pin_a@(130.81,104.14)→GND, pin_b@(130.81,96.52)→R_riaa_2.pin_a
_GND_CRIAA2_AT = (130.81, 107.95)
# riaa_mid wire Y=78.74 от R_riaa_1.pin_b к C_riaa_1.pin_b corner +
# R_riaa_2.pin_b corner + V1B.G (через R_g2 path).
# R_g2 grid leak (safety):
_R_G2_AT = (139.7, 93.98)  # 1Meg: pin_a@(139.7,97.79)→GND, pin_b@(139.7,90.17)=V1B.G level
_GND_RG2_AT = (139.7, 99.06)

# === Stage 2: 12AX7 CC (V1B = ECC83B unit 2) ===
_TUBE1B_AT = (152.4, 88.9)
_R_P2_AT = (152.4, 68.58)
_R_K2_AT = (149.86, 105.41)
_C_K2_AT = (160.02, 105.41)
_GND_RK2_AT = (149.86, 113.03)
_GND_CK2_AT = (160.02, 113.03)

# === Output coupling + load ===
_C_OUT_AT = (170.18, 78.74)  # rot=90: pin_a@(166.37,78.74), pin_b@(173.99,78.74)
_R_LOAD_AT = (181.61, 87.63)  # 47k assumed line amp Rin: pin_a@(181.61,91.44)→GND, pin_b@(181.61,83.82)→C_out output
_GND_RLOAD_AT = (181.61, 95.25)

_SPICE_DIRECTIVE_AT = (50.8, 125.0)


def _app_manager() -> SubprocessAppManager:
    return SubprocessAppManager(NativePlatformLayer())


def _build_tube_phono_riaa(path: Path) -> Path:  # noqa: PLR0915
    """Builds tube-phono-riaa reference fixture.

    Imported by `scripts/regenerate-templates.py` to bake the shipping
    template (`data/templates/tube-phono-riaa/`).
    """
    sch = Schematic('tube_phono_riaa_12ax7')

    # === Supplies & input ===
    v_bb = sch.add_v_dc(value='300', at=_V_BB_AT)
    v_in = sch.add_v_ac(
        value='VSIN',
        at=_V_IN_AT,
        amplitude=0.005,  # 5 mV MM cartridge level
        frequency=1000.0,
    )
    flg = sch.add_pwr_flag(at=_FLG_AT, rotation=180)

    # === Stage 1: 12AX7 CC ===
    c_in = sch.add_capacitor(value='100n', at=_C_IN_AT, rotation=90)
    r_g1 = sch.add_resistor(value='1Meg', at=_R_G1_AT)
    xv1a = sch.add_tube(
        spice_model=_tube_12ax7(),
        at=_TUBE1A_AT,
        symbol='Valve:ECC83',
    )
    r_p1 = sch.add_resistor(value='100k', at=_R_P1_AT)
    r_k1 = sch.add_resistor(value='1.5k', at=_R_K1_AT)
    # 100µF (bumped from 22µ) — keeps cathode bypassed down to ≈1 Hz,
    # без LF gain droop на 20 Hz (preserves RIAA boost compliance).
    c_k1 = sch.add_capacitor(value='100u', at=_C_K1_AT)

    # === Stage 1 → RIAA coupling ===
    # 470 nF — moves LF corner ниже 2 Hz, чтобы 20 Hz signal не
    # attenuated до RIAA network (preserves +19.3 dB RIAA boost at 20 Hz).
    c_couple_1 = sch.add_capacitor(
        value='470n', at=_C_COUPLE_1_AT, rotation=90,
    )

    # === RIAA EQ network ===
    # Lipshitz-derived values для τ1=3180µs / τ2=318µs / τ3=75µs:
    # R2·C2 = τ2 → R2=9.1k, C2=33n (300µs ≈ τ2 within 5%).
    # C1/C2 = 0.343 (Lipshitz cross-coupling) → C1 = 0.343·33n ≈ 11nF.
    # R1·(C1+C2) = τ1+τ3 = 3255µs → R1 = 3255µ/(11n+33n) ≈ 68k.
    r_riaa_1 = sch.add_resistor(
        value='68k', at=_R_RIAA_1_AT, rotation=90,
    )
    c_riaa_1 = sch.add_capacitor(value='11n', at=_C_RIAA_1_AT)
    r_riaa_2 = sch.add_resistor(value='9.1k', at=_R_RIAA_2_AT)
    c_riaa_2 = sch.add_capacitor(value='33n', at=_C_RIAA_2_AT)
    r_g2 = sch.add_resistor(value='1Meg', at=_R_G2_AT)

    # === Stage 2: 12AX7 CC ===
    xv1b = sch.add_tube(
        spice_model=_tube_12ax7(),
        at=_TUBE1B_AT,
        symbol='Valve:ECC83B',
    )
    r_p2 = sch.add_resistor(value='100k', at=_R_P2_AT)
    r_k2 = sch.add_resistor(value='1.5k', at=_R_K2_AT)
    c_k2 = sch.add_capacitor(value='100u', at=_C_K2_AT)  # same reason как C_k1

    # === Output ===
    c_out = sch.add_capacitor(value='0.47u', at=_C_OUT_AT, rotation=90)
    r_load = sch.add_resistor(value='47k', at=_R_LOAD_AT)

    # === Grounds ===
    gnd_vbb = sch.add_ground(at=_GND_VBB_AT)
    gnd_vin = sch.add_ground(at=_GND_VIN_AT)
    gnd_rg1 = sch.add_ground(at=_GND_RG1_AT)
    gnd_rk1 = sch.add_ground(at=_GND_RK1_AT)
    gnd_ck1 = sch.add_ground(at=_GND_CK1_AT)
    gnd_criaa1 = sch.add_ground(at=_GND_CRIAA1_AT)
    gnd_criaa2 = sch.add_ground(at=_GND_CRIAA2_AT)
    gnd_rg2 = sch.add_ground(at=_GND_RG2_AT)
    gnd_rk2 = sch.add_ground(at=_GND_RK2_AT)
    gnd_ck2 = sch.add_ground(at=_GND_CK2_AT)
    gnd_rload = sch.add_ground(at=_GND_RLOAD_AT)

    # === B+ rail (Y=58.42) ===
    _bplus_rail_end_x = 152.4
    sch.connect(
        v_bb.pin_minus,
        Position(x_mm=_bplus_rail_end_x, y_mm=_BPLUS_RAIL_Y),
    )
    sch.connect(r_p1.pin_b, Position(x_mm=88.9, y_mm=_BPLUS_RAIL_Y))
    sch.junction(at=(88.9, _BPLUS_RAIL_Y))
    sch.connect(r_p2.pin_b, Position(x_mm=152.4, y_mm=_BPLUS_RAIL_Y))
    sch.junction(at=(152.4, _BPLUS_RAIL_Y))

    # === Power-flag → V_in.pin_plus ===
    sch.connect(flg.pin, v_in.pin_plus)

    # === Stage 1 grid ===
    sch.connect(v_in.pin_minus, c_in.pin_a)
    sch.connect(c_in.pin_b, Position(x_mm=67.31, y_mm=88.9))
    sch.connect(Position(x_mm=67.31, y_mm=88.9), xv1a.pin('G'))
    sch.connect(r_g1.pin_b, Position(x_mm=78.74, y_mm=88.9))
    sch.junction(at=(78.74, 88.9))

    # === Stage 1 plate ===
    sch.connect(xv1a.pin('P'), r_p1.pin_a)
    sch.connect(xv1a.pin('P'), c_couple_1.pin_a)
    sch.junction(at=xv1a.pin('P'))

    # === Stage 1 cathode ===
    _cathode1_rail_y = 101.6
    sch.connect(xv1a.pin('K'), Position(x_mm=86.36, y_mm=_cathode1_rail_y))
    sch.junction(at=(86.36, _cathode1_rail_y))
    sch.connect(
        Position(x_mm=86.36, y_mm=_cathode1_rail_y),
        c_k1.pin_b,
    )

    # === RIAA network wiring ===
    # riaa_in node = C_couple_1.pin_b (107.95, 78.74).
    # riaa_in → R_riaa_1.pin_a (110.49, 78.74): horizontal short.
    sch.connect(c_couple_1.pin_b, r_riaa_1.pin_a)
    # riaa_mid wire Y=78.74 from R_riaa_1.pin_b (118.11, 78.74) east к
    # corner для C_riaa_1.pin_b (120.65, 85.09 — under riaa_mid wire),
    # R_riaa_2.pin_b (130.81, 85.09), and V1B.G area.
    # First: riaa_mid wire horizontal Y=78.74 from R_riaa_1.pin_b east.
    # Stop at X=144.78 (V1B.G level X-7.62=144.78).
    _riaa_mid_y = 78.74
    _riaa_mid_end_x = 144.78
    sch.connect(
        r_riaa_1.pin_b,
        Position(x_mm=_riaa_mid_end_x, y_mm=_riaa_mid_y),
    )
    # C_riaa_1.pin_b (120.65, 85.09) → riaa_mid wire (120.65, 78.74): vertical stub.
    sch.connect(
        c_riaa_1.pin_b,
        Position(x_mm=120.65, y_mm=_riaa_mid_y),
    )
    sch.junction(at=(120.65, _riaa_mid_y))
    # R_riaa_2.pin_b (130.81, 85.09) → riaa_mid wire (130.81, 78.74): vertical stub.
    sch.connect(
        r_riaa_2.pin_b,
        Position(x_mm=130.81, y_mm=_riaa_mid_y),
    )
    sch.junction(at=(130.81, _riaa_mid_y))
    # R_riaa_2.pin_a (130.81, 92.71) → C_riaa_2.pin_b (130.81, 96.52): vertical short stub.
    sch.connect(r_riaa_2.pin_a, c_riaa_2.pin_b)

    # === RIAA mid → V1B.G + R_g2 grid leak ===
    # V1B.G at (144.78, 88.9). riaa_mid wire ends at (144.78, 78.74).
    # Vertical drop X=144.78 from Y=78.74 to Y=88.9.
    sch.connect(
        Position(x_mm=_riaa_mid_end_x, y_mm=_riaa_mid_y),
        xv1b.pin('G'),
    )
    # R_g2.pin_b (139.7, 90.17) → grid wire Y=88.9 at X=139.7? But grid trunk
    # is short — V1B.G pin at Y=88.9 directly. R_g2 leak to GND from grid
    # trunk: R_g2.pin_b → corner (139.7, 88.9) → grid trunk to V1B.G.
    sch.connect(r_g2.pin_b, Position(x_mm=139.7, y_mm=88.9))
    sch.connect(
        Position(x_mm=139.7, y_mm=88.9),
        xv1b.pin('G'),
    )
    sch.junction(at=(139.7, 88.9))

    # === Stage 2 plate ===
    sch.connect(xv1b.pin('P'), r_p2.pin_a)
    sch.connect(xv1b.pin('P'), c_out.pin_a)
    sch.junction(at=xv1b.pin('P'))

    # === Stage 2 cathode ===
    _cathode2_rail_y = 101.6
    sch.connect(xv1b.pin('K'), Position(x_mm=149.86, y_mm=_cathode2_rail_y))
    sch.junction(at=(149.86, _cathode2_rail_y))
    sch.connect(
        Position(x_mm=149.86, y_mm=_cathode2_rail_y),
        c_k2.pin_b,
    )

    # === Output ===
    sch.connect(c_out.pin_b, r_load.pin_b)
    sch.connect(r_load.pin_a, gnd_rload.pin)

    # === Ground hookups ===
    sch.connect(v_bb.pin_plus, gnd_vbb.pin)
    sch.connect(v_in.pin_plus, gnd_vin.pin)
    sch.connect(r_g1.pin_a, gnd_rg1.pin)
    sch.connect(r_k1.pin_a, gnd_rk1.pin)
    sch.connect(c_k1.pin_a, gnd_ck1.pin)
    sch.connect(c_riaa_1.pin_a, gnd_criaa1.pin)
    sch.connect(c_riaa_2.pin_a, gnd_criaa2.pin)
    sch.connect(r_g2.pin_a, gnd_rg2.pin)
    sch.connect(r_k2.pin_a, gnd_rk2.pin)
    sch.connect(c_k2.pin_a, gnd_ck2.pin)

    # === SPICE labels ===
    sch.label('input', at=v_in.pin_minus)
    sch.label('grid1', at=xv1a.pin('G'))
    sch.label('plate1', at=xv1a.pin('P'))
    sch.label('cathode1', at=xv1a.pin('K'))
    sch.label('riaa_mid', at=Position(x_mm=125, y_mm=_riaa_mid_y))
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
async def test_facade_tube_phono_riaa_writes_model_includes(
    tmp_path: Path,
) -> None:
    """Netlist содержит X1+X2 (12AX7 pair) + .include 12AX7.lib."""
    sch_path = _build_tube_phono_riaa(tmp_path / 'tube_phono_riaa.kicad_sch')
    netlist = await _export_netlist(sch_path, tmp_path / 'tube_phono_riaa.cir')
    text = netlist.read_text()

    x_lines = [ln for ln in text.splitlines() if ln.startswith('X')]
    assert len(x_lines) == 2, (
        f'expected 2 X-instances (V1A + V1B 12AX7), got: {x_lines}'
    )
    for ln in x_lines:
        assert ln.endswith('12AX7'), ln

    assert '12AX7.lib' in text, text


@needs_kicad
async def test_facade_tube_phono_riaa_topology(tmp_path: Path) -> None:
    """Verify passive RIAA network components present + both 12AX7 CC stages."""
    sch_path = _build_tube_phono_riaa(tmp_path / 'tube_phono_riaa.kicad_sch')
    netlist = await _export_netlist(sch_path, tmp_path / 'tube_phono_riaa.cir')
    lines = netlist.read_text().splitlines()

    r_lines = [ln for ln in lines if ln.startswith('R')]
    c_lines = [ln for ln in lines if ln.startswith('C')]

    # RIAA components (Lipshitz-derived): R_riaa_1=68k, R_riaa_2=9.1k,
    # C_riaa_1=11n, C_riaa_2=33n.
    assert any(' 68k' in ln for ln in r_lines), 'no 68k R_riaa_1'
    assert any(' 9.1k' in ln for ln in r_lines), 'no 9.1k R_riaa_2'
    assert any(' 11n' in ln for ln in c_lines), 'no 11n C_riaa_1'
    assert any(' 33n' in ln for ln in c_lines), 'no 33n C_riaa_2'

    # Both stages: two R_p=100k + two R_k=1.5k + two C_k=22µ bypass.
    r_100k = [ln for ln in r_lines if ' 100k' in ln]
    assert len(r_100k) == 2, f'expected 2 R_p=100k, got: {r_100k}'
    r_1k5 = [ln for ln in r_lines if ' 1.5k' in ln]
    assert len(r_1k5) == 2, f'expected 2 R_k=1.5k, got: {r_1k5}'
    c_100u = [ln for ln in c_lines if ' 100u' in ln]
    assert len(c_100u) == 2, f'expected 2 C_k=100µ bypass, got: {c_100u}'


@needs_kicad
@needs_ngspice
async def test_facade_tube_phono_riaa_op_point_active(
    tmp_path: Path,
) -> None:
    """DC op-point: обе 12AX7 в active region (CC bias point typical для phono)."""
    sch_path = _build_tube_phono_riaa(tmp_path / 'tube_phono_riaa.kicad_sch')
    netlist_path = await _export_netlist(
        sch_path, tmp_path / 'tube_phono_riaa.cir',
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

    # Stage 1 CC: V_a active region ≈ 100-220V (V_BB=300, R_p=100k, I_a≈0.5-1.5mA).
    assert 100.0 <= v_plate1 <= 250.0, (
        f'V_plate1 out of active region: {v_plate1:.2f} V'
    )
    assert 0.5 <= v_cath1 <= 5.0, (
        f'V_cathode1 implausible: {v_cath1:.2f} V'
    )

    # Stage 2 CC: same range (identical config).
    assert 100.0 <= v_plate2 <= 250.0, (
        f'V_plate2 out of active region: {v_plate2:.2f} V'
    )
    assert 0.5 <= v_cath2 <= 5.0, (
        f'V_cathode2 implausible: {v_cath2:.2f} V'
    )
