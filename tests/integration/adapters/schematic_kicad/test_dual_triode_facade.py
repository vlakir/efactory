"""T105 Phase 1 acceptance: multi-unit dual-triode (обе halves в одной схеме).

Демонстрирует:
* Self-contained `Valve:ECC83` (без `(extends ...)` — T105 Phase 0
  показал, что pin resolution для derived не работает; в Phase 1
  copy-renamed ECC81 → self-contained ECC83).
* Multi-unit instancing — оба triode-halves ECC83 (`unit=1` через
  `Valve:ECC83` и `unit=2` через `Valve:ECC83B` registry-keys) в одной
  schematic как X1 и X2 — KiCad визуально показывает их как halves
  единого dual-triode (same lib_id).
* SPICE-wise: каждый half — independent `XN` subckt-instance (T006
  6N2P SUBCKT — single triode P/G/K). Cascaded preamp 6Н2П: 2 stage's
  усиления.
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
    not _KICAD_AVAILABLE, reason='KiCad not installed',
)
needs_ngspice = pytest.mark.skipif(
    not _NGSPICE_AVAILABLE, reason='ngspice not installed',
)

_TUBE_LIB = (
    Path(__file__).resolve().parents[4]
    / 'data' / 'models' / 'tubes' / 'custom' / '6N2P.lib'
)


def _tube_6n2p() -> SpiceModel:
    return SpiceModel(
        id='6N2P', name='6Н2П',
        category=ComponentCategory.TUBE, subcategory='triode',
        source=ModelSource.CUSTOM,
        file_path=_TUBE_LIB,
        subckt_pins=('P', 'G', 'K'),
    )


def _app_manager() -> SubprocessAppManager:
    return SubprocessAppManager(NativePlatformLayer())


def _build_cascaded_dual_triode(path: Path) -> Path:
    """Two-stage cascaded preamp на обоих halves ECC83 (6Н2П)."""
    sch = Schematic('cascaded_dual_triode')

    # Layout (mm, Y-down, 1.27 grid):
    #   Stage 1: V_in → C_in1 → R_g1 → ECC83-A grid; A → R_p1 → B+
    #   Stage 2: ECC83-A plate → C_couple → R_g2 → ECC83-B grid;
    #            B-plate → R_p2 → B+
    v_bb = sch.add_v_dc(value='250', at=(50.8, 50.8))
    v_in = sch.add_v_ac(
        value='VSIN', at=(50.8, 80.01), amplitude=0.010, frequency=1000.0,
    )
    c_in = sch.add_capacitor(value='100n', at=(63.5, 74.93), rotation=90)
    r_g1 = sch.add_resistor(value='1Meg', at=(81.28, 85.09))
    r_p1 = sch.add_resistor(value='100k', at=(100.33, 53.34))
    # Stage 1 — half A (Valve:ECC83, unit 1): pins A=6 top, G=7 left,
    # K=8 bottom. ECC83 at (100.33, 71.12): A@(100.33, 60.96),
    # G@(92.71, 71.12), K@(97.79, 81.28).
    xv1a = sch.add_tube(
        spice_model=_tube_6n2p(), at=(100.33, 71.12),
        symbol='Valve:ECC83',
    )
    r_k1 = sch.add_resistor(value='1.5k', at=(97.79, 85.09))
    c_k1 = sch.add_capacitor(value='22u', at=(105.41, 85.09))
    # Inter-stage coupling cap A.plate → B.grid
    c_couple = sch.add_capacitor(value='10n', at=(120.65, 60.96), rotation=90)
    r_g2 = sch.add_resistor(value='470k', at=(135.89, 85.09))
    r_p2 = sch.add_resistor(value='100k', at=(154.94, 53.34))
    # Stage 2 — half B (Valve:ECC83B, unit 2): pins A=1 top, G=2 left,
    # K=3 bottom. ECC83-B at (154.94, 71.12): A@(154.94, 60.96),
    # G@(147.32, 71.12), K@(152.4, 81.28).
    xv1b = sch.add_tube(
        spice_model=_tube_6n2p(), at=(154.94, 71.12),
        symbol='Valve:ECC83B',
    )
    r_k2 = sch.add_resistor(value='1.5k', at=(152.4, 85.09))
    c_k2 = sch.add_capacitor(value='22u', at=(160.02, 85.09))
    # Output
    c_out = sch.add_capacitor(value='1n', at=(173.99, 60.96), rotation=90)
    r_load = sch.add_resistor(value='1Meg', at=(189.23, 71.12))

    gnd_vbb = sch.add_ground(at=(50.8, 59.69))
    gnd_vin = sch.add_ground(at=(50.8, 88.9))
    gnd_rg1 = sch.add_ground(at=(81.28, 91.44))
    gnd_rk1 = sch.add_ground(at=(97.79, 92.71))
    gnd_ck1 = sch.add_ground(at=(105.41, 92.71))
    gnd_rg2 = sch.add_ground(at=(135.89, 91.44))
    gnd_rk2 = sch.add_ground(at=(152.4, 92.71))
    gnd_ck2 = sch.add_ground(at=(160.02, 92.71))
    gnd_rload = sch.add_ground(at=(189.23, 78.74))
    flg = sch.add_pwr_flag(at=(45.72, 88.9), rotation=180)

    # B+ rail Y=45.72 (high up). V_BB.pin_minus → горизонталь до X=155.
    sch.connect(v_bb.pin_minus, Position(x_mm=154.94, y_mm=45.72))
    # R_p1 stub до rail
    sch.connect(Position(x_mm=100.33, y_mm=45.72), r_p1.pin_b)
    sch.junction(at=(100.33, 45.72))
    # R_p2 stub до rail
    sch.connect(Position(x_mm=154.94, y_mm=45.72), r_p2.pin_b)

    # Stage 1 plate: R_p1.pin_a (100.33, 57.15) ← но pin_a по pattern:
    # R at (100.33, 53.34), rotation=0: pin_a (100.33, 57.15), pin_b
    # (100.33, 49.53). Plate of tube ECC83-A at (100.33, 60.96).
    # Wire R_p1.pin_a → ECC83-A plate.
    sch.connect(r_p1.pin_a, xv1a.pin('P'))

    # Input: V_in.pin_minus → C_in.pin_a → C_in.pin_b → R_g1.pin_b/G(A)
    sch.connect(v_in.pin_minus, c_in.pin_a)
    # Grid wire stage 1: C_in.pin_b (67.31, 74.93) → ECC83-A.G (92.71, 71.12)
    # Manhattan L-route
    sch.connect(c_in.pin_b, Position(x_mm=67.31, y_mm=71.12))
    sch.connect(
        Position(x_mm=67.31, y_mm=71.12),
        xv1a.pin('G'),
    )
    # R_g1 stub to grid wire: R_g1.pin_b (81.28, 81.28) — но нужно
    # привязаться к grid Y=71.12. Wire R_g1.pin_b → grid corner.
    sch.connect(
        r_g1.pin_b,
        Position(x_mm=81.28, y_mm=71.12),
    )
    sch.junction(at=(81.28, 71.12))   # T: R_g1 + grid wire

    # Stage 1 cathode rail: K_A (97.79, 81.28) → R_k1.pin_b и C_k1.pin_b
    sch.connect(xv1a.pin('K'), c_k1.pin_b)
    sch.junction(at=(97.79, 81.28))   # T: K_A + R_k1.pin_b + wire

    # Inter-stage coupling: plate_A (100.33, 60.96) → C_couple.pin_a
    # (116.84, 60.96) → C_couple.pin_b (124.46, 60.96) → R_g2.pin_b /
    # ECC83-B.G (147.32, 71.12)
    # Plate_A → C_couple.pin_a: horizontal Y=60.96 X=100.33 → 116.84
    sch.connect(xv1a.pin('P'), c_couple.pin_a)
    # C_couple.pin_b → ECC83-B.G via L-route (через corner (124.46, 71.12))
    sch.connect(c_couple.pin_b, Position(x_mm=124.46, y_mm=71.12))
    sch.connect(
        Position(x_mm=124.46, y_mm=71.12),
        xv1b.pin('G'),
    )
    # R_g2 stub to grid_B wire
    sch.connect(r_g2.pin_b, Position(x_mm=135.89, y_mm=71.12))
    sch.junction(at=(135.89, 71.12))

    # Stage 2 plate: R_p2.pin_a → ECC83-B.P
    sch.connect(r_p2.pin_a, xv1b.pin('P'))

    # Stage 2 cathode: K_B → R_k2.pin_b и C_k2.pin_b
    sch.connect(xv1b.pin('K'), c_k2.pin_b)
    sch.junction(at=(152.4, 81.28))

    # Output: plate_B → C_out → R_load → GND
    sch.connect(xv1b.pin('P'), c_out.pin_a)
    sch.connect(c_out.pin_b, r_load.pin_b)

    # GND-стержни
    sch.connect(v_bb.pin_plus, gnd_vbb.pin)
    sch.connect(v_in.pin_plus, gnd_vin.pin)
    sch.connect(r_g1.pin_a, gnd_rg1.pin)
    sch.connect(r_k1.pin_a, gnd_rk1.pin)
    sch.connect(c_k1.pin_a, gnd_ck1.pin)
    sch.connect(r_g2.pin_a, gnd_rg2.pin)
    sch.connect(r_k2.pin_a, gnd_rk2.pin)
    sch.connect(c_k2.pin_a, gnd_ck2.pin)
    sch.connect(r_load.pin_a, gnd_rload.pin)
    sch.connect(flg.pin, v_in.pin_plus)

    sch.label('input', at=v_in.pin_minus)
    sch.label('plate_a', at=xv1a.pin('P'))
    sch.label('plate_b', at=xv1b.pin('P'))
    sch.label('output', at=c_out.pin_b)

    sch.spice_directive('.tran 10u 30m uic', at=(50.8, 105.41))
    return sch.save(path)


@needs_kicad
def test_dual_triode_two_units_in_one_schematic(tmp_path: Path) -> None:
    """T105 Phase 1: оба halves ECC83 — same lib_id, different unit."""
    sch_path = _build_cascaded_dual_triode(tmp_path / 'cascade.kicad_sch')
    text = sch_path.read_text(encoding='utf-8')
    # Оба instances ссылаются на ОДНУ KiCad library entry Valve:ECC83
    el_ecc83 = text.count('(lib_id "Valve:ECC83")')
    assert el_ecc83 == 2, f'expected 2 Valve:ECC83 instances, got {el_ecc83}'
    # Unit 1 + Unit 2 — в каждом instance
    assert text.count('(unit 1)') >= 2  # X1 unit 1 + instances block
    assert text.count('(unit 2)') >= 2  # X2 unit 2 + instances block
    # Lib_symbols section содержит self-contained ECC83 (НЕ extends).
    assert '(symbol "Valve:ECC83"' in text
    assert '(extends "' not in text, (
        'ECC83 должен быть self-contained — никаких (extends ...)'
    )


@needs_kicad
async def test_dual_triode_netlist_has_two_subckt_instances(
    tmp_path: Path,
) -> None:
    """Netlist содержит X1 ... 6N2P + X2 ... 6N2P (2 instance того же SUBCKT)."""
    sch_path = _build_cascaded_dual_triode(tmp_path / 'cascade.kicad_sch')
    exporter = KicadCliSchematicExporter(_app_manager())
    netlist = await exporter.export_spice_netlist(
        sch_path, tmp_path / 'cascade.cir',
    )
    text = netlist.read_text()
    x1_lines = [ln for ln in text.splitlines() if ln.startswith('X1 ')]
    x2_lines = [ln for ln in text.splitlines() if ln.startswith('X2 ')]
    assert x1_lines and x1_lines[0].split()[-1] == '6N2P'
    assert x2_lines and x2_lines[0].split()[-1] == '6N2P'
    assert '6N2P.lib' in text


@needs_kicad
@needs_ngspice
async def test_dual_triode_tran_two_stage_amplifies(tmp_path: Path) -> None:
    """ngspice TRAN: cascaded 2 stages 6Н2П даёт композитный gain (≥ stage1×3)."""
    sch_path = _build_cascaded_dual_triode(tmp_path / 'cascade.kicad_sch')
    exporter = KicadCliSchematicExporter(_app_manager())
    netlist = await exporter.export_spice_netlist(
        sch_path, tmp_path / 'cascade.cir',
    )
    simulator = NgspiceSimulator(_app_manager())
    result = await simulator.run(
        netlist, TranAnalysis(t_step=1e-5, t_stop=30e-3),
    )
    assert result.time_series is not None
    ts = result.time_series
    n = len(ts.time); skip = int(n * 0.7)
    vin = ts.traces['v(/input)'][skip:]
    plate_b = ts.traces['v(/plate_b)'][skip:]
    vin_pp = max(vin) - min(vin)
    plate_b_pp = max(plate_b) - min(plate_b)
    assert vin_pp > 0.005, f'Input swing too low: {vin_pp}'
    # Single 6Н2П stage gives ~50× в нашей topology (T105 Phase 0
    # showed 19×, with bigger Rp до 50×). Cascaded — теоретически
    # ~50×50 = 2500×, но clipping ограничит. Threshold 100× — safe.
    gain = plate_b_pp / vin_pp
    assert gain >= 100.0, f'Cascade gain {gain:.0f}× ниже 100×'
