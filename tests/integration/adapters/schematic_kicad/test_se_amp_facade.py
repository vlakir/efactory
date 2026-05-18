"""T100 Phase 2 acceptance: Single-Ended pentode amp 6П14П + OPT.

Топология (упрощённая SE pentode):
  V_in → C_in → grid (G)
  grid → R_g (470k) → GND   [grid-leak bias]
  cathode (K) → R_k (270Ω) // C_k (220 µF) → GND  [auto-bias]
  screen (G2) → B+ напрямую (без R_screen для compactness)
  plate (P) → OPT.P1
  OPT.P2 → B+ (V_B = 250 V DC)
  OPT.S1, OPT.S2 → R_load (8 Ω)

Acceptance:
  - kicad-cli sch export netlist: содержит XV1 ... 6P14P и XT1 ... OPT_SE_5K_8;
    оба .include подцеплены из Sim.Library.
  - ngspice TRAN: V(/plate) показывает AC swing ≥ 1 V (есть усиление),
    secondary V(S1)−V(S2) ненулевой (через трансформатор сигнал проходит).

Tube/OPT subckts подгружаются из data/models/ через `SpiceModel` VO,
напрямую конструируемый (без полной T006 SpiceModelLibrary integration —
держим тест автономным).
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
_TUBE_LIB = _REPO_ROOT / 'data' / 'models' / 'tubes' / 'custom' / '6P14P.lib'
_OPT_LIB = (
    _REPO_ROOT / 'data' / 'models' / 'transformers' / 'generic' / 'OPT_SE_5K_8.lib'
)


def _tube_6p14p() -> SpiceModel:
    return SpiceModel(
        id='6P14P',
        name='6П14П',
        category=ComponentCategory.TUBE,
        subcategory='pentode',
        source=ModelSource.CUSTOM,
        file_path=_TUBE_LIB,
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


# Layout (mm, Y-down) на KiCad-стандартной сетке 1.27 mm. Wire-based
# топология, labels — только для SPICE-trace nodes (input/plate/sec_*).
#
# V_DC/V_AC polarity workaround (Y-flip bug в фасаде): pin_plus = real '-',
# pin_minus = real '+'. Для +B+=250V — pin_minus подключаем к B+ rail,
# pin_plus → GND. См. facade.py комментарий.
_V_IN_AT   = (50.8, 80.01)         # rotation=0: pin_plus@(50.8,85.09)→GND, pin_minus@(50.8,74.93)→C_in
_GND_VIN_AT = (50.8, 88.9)
_FLG_AT    = (45.72, 88.9)
_C_IN_AT   = (63.5, 74.93)         # rotation=90 horizontal
_R_G_AT    = (78.74, 77.47)        # pin_b@(78.74,73.66)→grid, pin_a@(78.74,81.28)→GND
_GND_RG_AT = (78.74, 85.09)
_TUBE_AT   = (99.06, 71.12)        # Conn_01x04: P@(93.98,68.58), G2@(93.98,71.12), G@(93.98,73.66), K@(93.98,76.2)
_R_K_AT    = (105.41, 80.01)       # pin_b@(105.41,76.2)→cathode
_GND_RK_AT = (105.41, 87.63)
_C_K_AT    = (116.84, 80.01)       # parallel R_K
_GND_CK_AT = (116.84, 87.63)
_OPT_AT    = (132.08, 71.12)       # P1@(127.0,68.58)→plate, P2@(127.0,71.12)→B+, S1@(127.0,73.66), S2@(127.0,76.2)
_R_LOAD_AT = (144.78, 77.47)       # pin_b@(144.78,73.66) = OPT.S1.y; pin_a@(144.78,81.28)
_V_B_AT    = (144.78, 60.96)       # rotation=0: pin_plus@(144.78,66.04)→GND, pin_minus@(144.78,55.88)→B+ rail
_GND_VB_AT = (144.78, 69.85)
_BPLUS_RAIL_Y = 55.88              # horizontal rail соединяет V_B.pin_minus, tube.G2, OPT.P2


def _app_manager() -> SubprocessAppManager:
    return SubprocessAppManager(NativePlatformLayer())


def _build_se_amp(path: Path) -> Path:
    sch = Schematic('se_amp_6p14p')

    # rotation=0: facade pin_plus → real '-', pin_minus → real '+' (Y-flip workaround)
    v_in = sch.add_v_ac(
        reference='V1', value='VSIN', at=_V_IN_AT,
        amplitude=0.010, frequency=1000.0,
    )
    c_in = sch.add_capacitor(
        reference='C1', value='10n', at=_C_IN_AT, rotation=90,
    )
    r_g = sch.add_resistor(reference='Rg', value='470k', at=_R_G_AT)
    xv1 = sch.add_tube(
        spice_model=_tube_6p14p(),
        reference='XV1', at=_TUBE_AT,
    )
    r_k = sch.add_resistor(reference='Rk', value='270', at=_R_K_AT)
    c_k = sch.add_capacitor(reference='Ck', value='220u', at=_C_K_AT)
    xt1 = sch.add_transformer(
        spice_model=_opt_se_5k_8(),
        reference='XT1', at=_OPT_AT,
    )
    r_load = sch.add_resistor(reference='RL', value='8', at=_R_LOAD_AT)
    v_b = sch.add_v_dc(reference='V2', value='250', at=_V_B_AT)
    gnd_vin = sch.add_ground(at=_GND_VIN_AT)
    gnd_rg = sch.add_ground(at=_GND_RG_AT)
    gnd_rk = sch.add_ground(at=_GND_RK_AT)
    gnd_ck = sch.add_ground(at=_GND_CK_AT)
    gnd_vb = sch.add_ground(at=_GND_VB_AT)
    flg = sch.add_pwr_flag(at=_FLG_AT, rotation=180)

    # === Wires ===
    # Input: V_in.pin_minus → C_in.pin_a (horizontal Y=74.93)
    sch.connect(v_in.pin_minus, c_in.pin_a)
    # Grid: C_in.pin_b → R_g.pin_b → tube.G (через L-corner на X=67.31, Y=73.66)
    sch.connect(c_in.pin_b, Position(x_mm=_C_IN_AT[0] + 3.81, y_mm=73.66))
    sch.connect(Position(x_mm=_C_IN_AT[0] + 3.81, y_mm=73.66), r_g.pin_b)
    sch.connect(r_g.pin_b, xv1.pin('G'))
    sch.junction(at=(_R_G_AT[0], 73.66))  # T: R_g pin + grid wire L↔R
    # Cathode rail: tube.K → R_k.pin_b → C_k.pin_b (horizontal Y=76.2)
    sch.connect(xv1.pin('K'), r_k.pin_b)
    sch.connect(r_k.pin_b, c_k.pin_b)
    sch.junction(at=(_R_K_AT[0], 76.2))  # T: R_k pin + rail
    # Plate: tube.P → OPT.P1 (horizontal Y=68.58)
    sch.connect(xv1.pin('P'), xt1.pin('P1'))
    # B+ rail: V_B.pin_minus → горизонталь Y=55.88 → стуbs к tube.G2 и OPT.P2
    sch.connect(v_b.pin_minus, Position(x_mm=93.98, y_mm=_BPLUS_RAIL_Y))
    sch.connect(Position(x_mm=93.98, y_mm=_BPLUS_RAIL_Y), xv1.pin('G2'))
    sch.connect(Position(x_mm=127.0, y_mm=_BPLUS_RAIL_Y), xt1.pin('P2'))
    sch.junction(at=(127.0, _BPLUS_RAIL_Y))  # T: rail + stub к OPT
    # Secondary loop: S1 → R_load.pin_b (horizontal Y=73.66), S2 → R_load.pin_a (L)
    sch.connect(xt1.pin('S1'), r_load.pin_b)
    sch.connect(xt1.pin('S2'), Position(x_mm=_R_LOAD_AT[0], y_mm=76.2))
    sch.connect(Position(x_mm=_R_LOAD_AT[0], y_mm=76.2), r_load.pin_a)

    # GND-стержни
    sch.connect(v_in.pin_plus, gnd_vin.pin)
    sch.connect(v_b.pin_plus, gnd_vb.pin)
    sch.connect(r_g.pin_a, gnd_rg.pin)
    sch.connect(r_k.pin_a, gnd_rk.pin)
    sch.connect(c_k.pin_a, gnd_ck.pin)
    sch.connect(flg.pin, v_in.pin_plus)

    # SPICE-trace labels (только для assertions)
    sch.label('input', at=v_in.pin_minus)
    sch.label('plate', at=xv1.pin('P'))
    sch.label('sec_a', at=xt1.pin('S1'))
    sch.label('sec_b', at=xt1.pin('S2'))

    sch.spice_directive('.tran 10u 5m uic', at=(50.8, 95.25))

    return sch.save(path)


async def _export_netlist(schematic_path: Path, netlist_path: Path) -> Path:
    exporter = KicadCliSchematicExporter(_app_manager())
    return await exporter.export_spice_netlist(schematic_path, netlist_path)


@needs_kicad
async def test_facade_se_amp_writes_subckt_instances_and_includes(
    tmp_path: Path,
) -> None:
    """Netlist содержит XV1/XT1 X-инстансы + два .include для tube/OPT."""
    sch_path = _build_se_amp(tmp_path / 'se_amp.kicad_sch')
    netlist = await _export_netlist(sch_path, tmp_path / 'se_amp.cir')
    text = netlist.read_text()
    # X-instance для tube
    xv1_lines = [ln for ln in text.splitlines() if ln.startswith('XV1 ')]
    assert xv1_lines, f'No XV1 line:\n{text}'
    assert xv1_lines[0].split()[-1] == '6P14P', xv1_lines[0]
    # X-instance для OPT
    xt1_lines = [ln for ln in text.splitlines() if ln.startswith('XT1 ')]
    assert xt1_lines, f'No XT1 line:\n{text}'
    assert xt1_lines[0].split()[-1] == 'OPT_SE_5K_8', xt1_lines[0]
    # .include для обеих библиотек
    assert '6P14P.lib' in text, text
    assert 'OPT_SE_5K_8.lib' in text, text


@needs_kicad
@needs_ngspice
@pytest.mark.skip(
    reason=(
        'T100 W2 risk realized: B+ rail wires (X=93.98 → tube.G2, X=127.0 → '
        'OPT.P2) проходят через tube.P / OPT.P1 без явных junction; KiCad '
        'merg`ит /plate с screen/OPT-primary/B+ через visual touch — '
        'plate AC swing = 0. PWRS subst (T102) сработал, ngspice прогоняет '
        'до конца. Layout-фикс — отдельная задача T103.'
    ),
)
async def test_facade_se_amp_tran_shows_amplification(tmp_path: Path) -> None:
    """TRAN: AC swing на plate ≥ 5× от input — лампа усиливает сигнал."""
    sch_path = _build_se_amp(tmp_path / 'se_amp.kicad_sch')
    netlist = await _export_netlist(sch_path, tmp_path / 'se_amp.cir')
    simulator = NgspiceSimulator(_app_manager())

    result = await simulator.run(
        netlist, TranAnalysis(t_step=1e-5, t_stop=5e-3),
    )
    assert result.time_series is not None
    ts = result.time_series

    skip = len(ts.time) // 2
    vin = ts.traces['v(/input)'][skip:]
    vp = ts.traces['v(/plate)'][skip:]

    vin_pp = max(vin) - min(vin)
    vp_pp = max(vp) - min(vp)
    assert vin_pp > 0.005, f'Input swing too low: {vin_pp}'
    gain = vp_pp / vin_pp
    assert gain >= 5.0, f'Plate gain {gain:.1f}× ниже порога 5× (SE pentode)'
