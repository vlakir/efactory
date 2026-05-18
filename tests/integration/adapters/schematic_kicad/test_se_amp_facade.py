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


# Layout (mm, Y-down). Workaround Y-flip polarity у V_DC/V_AC: фасадный
# pin_plus = real '-', pin_minus = real '+'. Для положительного B+ 250V
# — Vb-label на pin_minus, GND на pin_plus. См. facade.py комментарий.
_V_IN_AT = (40.0, 90.0)            # rotation=0: pin_plus (40,95.08), pin_minus (40,84.92)
_C_IN_AT = (55.0, 84.92)           # horizontal cap соединяет к pin_minus = real '+'
_TUBE_AT = (95.0, 90.0)
_R_G_AT = (70.0, 100.0)
_R_K_AT = (105.0, 100.0)
_C_K_AT = (115.0, 100.0)
_V_B_AT = (155.0, 50.0)            # rotation=0: pin_plus (155,55.08)=real '-', pin_minus (155,44.92)=real '+'
_OPT_AT = (135.0, 90.0)
_R_LOAD_AT = (165.0, 90.0)
_GND_VIN_AT = (40.0, 100.0)        # под V_in.pin_plus (95.08)
_GND_RG_AT = (70.0, 115.0)
_GND_RK_AT = (105.0, 115.0)
_GND_CK_AT = (115.0, 115.0)
_GND_VB_AT = (155.0, 62.0)         # под V_B.pin_plus (55.08) = real '-'
_FLG_AT = (35.0, 100.0)


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

    # === Short wires к GND-symbols (V1/V_B pin_plus = real '-' идёт на GND) ===
    sch.connect(v_in.pin_plus, gnd_vin.pin)
    sch.connect(v_b.pin_plus, gnd_vb.pin)
    sch.connect(r_g.pin_b, gnd_rg.pin)
    sch.connect(r_k.pin_b, gnd_rk.pin)
    sch.connect(c_k.pin_b, gnd_ck.pin)
    sch.connect(flg.pin, v_in.pin_plus)

    # === Net labels (KiCad склеивает по имени) ===
    # input net (V_in.pin_minus = real '+' → C_in.left)
    sch.label('input', at=v_in.pin_minus)
    sch.label('input', at=c_in.pin_a)
    # grid net (C_in.right → tube.G → R_g.top)
    sch.label('grid', at=c_in.pin_b)
    sch.label('grid', at=xv1.pin('G'))
    sch.label('grid', at=r_g.pin_a)
    # cathode net (tube.K → R_k.top → C_k.top)
    sch.label('cathode', at=xv1.pin('K'))
    sch.label('cathode', at=r_k.pin_a)
    sch.label('cathode', at=c_k.pin_a)
    # B+ rail (V_B.pin_minus = real '+' → tube.G2 → OPT.P2)
    sch.label('Bplus', at=v_b.pin_minus)
    sch.label('Bplus', at=xv1.pin('G2'))
    sch.label('Bplus', at=xt1.pin('P2'))
    # plate net (tube.P → OPT.P1)
    sch.label('plate', at=xv1.pin('P'))
    sch.label('plate', at=xt1.pin('P1'))
    # secondary loop (OPT.S1 → R_load.top, OPT.S2 → R_load.bottom)
    sch.label('sec_a', at=xt1.pin('S1'))
    sch.label('sec_a', at=r_load.pin_b)
    sch.label('sec_b', at=xt1.pin('S2'))
    sch.label('sec_b', at=r_load.pin_a)

    # .tran директива для KiCad Simulator
    sch.spice_directive('.tran 10u 5m uic', at=(40, 130))

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
        'T006 tube models используют PSpice-extension PWRS(); '
        'ngspice 45 без compat-mode (psa) не распознаёт. Отдельная задача '
        'на patching T006 .lib (PWRS → sgn()*pwr()) — см. BACKLOG T102.'
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
