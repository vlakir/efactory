"""T105 acceptance: 6Н2П через Valve:ECC81 (dual-triode pin-compatible).

Демонстрирует:
* extended Valve registry (T105) — ECC81 теперь в registry; маппинг
  советских ламп → western symbol (6Н2П → 12AT7/ECC81 — pinout
  идентичен 12AX7/ECC83, отличается µ в T006 SPICE-модели).
* SPICE-симуляция любой ½ dual-triode-модели T006 через выбранную
  Valve-symbol.

Топология: common-cathode без OPT (избегаем W2 / OPT bias issues).

**Замечание (T105 Phase 1 deferred):** ECC83 = derived `(extends ECC81)`
не работает в текущей реализации (pins NC после lib_symbol резолва).
Writer умеет auto-load parent, но KiCad pin resolution для derived
требует ещё чего-то. Откладывается на T105 Phase 1.
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
        subckt_pins=('P', 'G', 'K'),  # ½ dual triode — 3 pins
    )


def _app_manager() -> SubprocessAppManager:
    return SubprocessAppManager(NativePlatformLayer())


def _build_triode_amp_6n2p(path: Path) -> Path:
    """Common-cathode 6Н2П через Valve:ECC83 (½ dual triode).

    Топология аналогична T104 EL84-amp: V_in→C_in→G; V_BB→R_p→P;
    K→R_k∥C_k→GND. Без OPT.
    """
    sch = Schematic('triode_amp_6n2p')
    # Layout — proven из triode_amp_facade (T104), adjusted pin coords
    # для ECC83 (A=6 top, G=7 left, K=8 bottom).
    v_bb = sch.add_v_dc(value='250', at=(50.8, 55.88))
    v_in = sch.add_v_ac(
        value='VSIN', at=(50.8, 80.01), amplitude=0.010, frequency=1000.0,
    )
    c_in = sch.add_capacitor(value='100n', at=(63.5, 74.93), rotation=90)
    r_g = sch.add_resistor(value='1Meg', at=(81.28, 85.09))
    r_p = sch.add_resistor(value='100k', at=(101.6, 64.77))
    # 6Н2П через Valve:ECC83 (½ dual triode). Pin coords:
    # A=6 (0, -10.16), G=7 (-7.62, 0), K=8 (-2.54, +10.16).
    # Centered at (101.6, 80.01): A@(101.6, 69.85), G@(93.98, 80.01),
    # K@(99.06, 90.17).
    xv1 = sch.add_tube(
        spice_model=_tube_6n2p(), at=(101.6, 80.01),
        symbol='Valve:ECC81',
    )
    r_k = sch.add_resistor(value='1.5k', at=(99.06, 93.98))
    c_k = sch.add_capacitor(value='22u', at=(109.22, 93.98))
    gnd_vbb = sch.add_ground(at=(50.8, 64.77))
    gnd_vin = sch.add_ground(at=(50.8, 88.9))
    gnd_rg = sch.add_ground(at=(81.28, 91.44))
    gnd_rk = sch.add_ground(at=(99.06, 101.6))
    gnd_ck = sch.add_ground(at=(109.22, 101.6))
    flg = sch.add_pwr_flag(at=(45.72, 88.9), rotation=180)

    # B+ rail: V_BB.pin_minus → горизонталь Y=50.8 → R_p stub
    sch.connect(v_bb.pin_minus, Position(x_mm=101.6, y_mm=50.8))
    sch.connect(Position(x_mm=101.6, y_mm=50.8), r_p.pin_b)

    # Plate: R_p.pin_a (101.6, 68.58) → ECC83.A (101.6, 69.85). Small
    # vertical gap (1.27mm) — wire фасадом, no junction.
    sch.connect(r_p.pin_a, xv1.pin('P'))

    # Grid: V_in.pin_minus (50.8, 74.93) → C_in.pin_a (59.69, 74.93)
    # → C_in.pin_b (67.31, 74.93) → ECC83.G (93.98, 80.01).
    sch.connect(v_in.pin_minus, c_in.pin_a)
    sch.connect(c_in.pin_b, xv1.pin('G'))
    # R_g.pin_b (81.28, 81.28) — на grid wire Y=80.01? Нет — Y=81.28
    # (R_g.pin_b at 85.09-3.81). Need to align grid wire к R_g.pin_b.
    # Грид wire L: (67.31, 74.93) → (67.31, 80.01) → (93.98, 80.01).
    # R_g.pin_b Y=81.28 не на Y=80.01 — wire идёт мимо. Стуbom вверх к
    # R_g нужно.
    sch.connect(r_g.pin_b, xv1.pin('G'))   # отдельный wire, junction в G

    # Cathode: ECC83.K (99.06, 90.17) совпадает с R_k.pin_b (99.06, 90.17)
    sch.connect(xv1.pin('K'), c_k.pin_b)

    # GND стержни
    sch.connect(v_bb.pin_plus, gnd_vbb.pin)
    sch.connect(v_in.pin_plus, gnd_vin.pin)
    sch.connect(r_g.pin_a, gnd_rg.pin)
    sch.connect(r_k.pin_a, gnd_rk.pin)
    sch.connect(c_k.pin_a, gnd_ck.pin)
    sch.connect(flg.pin, v_in.pin_plus)

    sch.label('input', at=v_in.pin_minus)
    sch.label('plate', at=xv1.pin('P'))

    sch.spice_directive('.tran 10u 30m uic', at=(50.8, 110.0))
    return sch.save(path)


@needs_kicad
def test_facade_6n2p_uses_valve_ecc81(tmp_path: Path) -> None:
    """T105 — 6Н2П через Valve:ECC81 (registry entry для триода)."""
    sch_path = _build_triode_amp_6n2p(tmp_path / 'amp.kicad_sch')
    text = sch_path.read_text(encoding='utf-8')
    assert '(lib_id "Valve:ECC81")' in text
    assert '(symbol "Valve:ECC81"' in text   # embedded в lib_symbols


@needs_kicad
async def test_facade_6n2p_netlist_includes_subckt_with_x_prefix(
    tmp_path: Path,
) -> None:
    """X1 ... 6N2P в netlist + .include 6N2P.lib (T105 + T104 auto-numbering)."""
    sch_path = _build_triode_amp_6n2p(tmp_path / 'amp.kicad_sch')
    exporter = KicadCliSchematicExporter(_app_manager())
    netlist = await exporter.export_spice_netlist(
        sch_path, tmp_path / 'amp.cir',
    )
    text = netlist.read_text()
    x1_lines = [ln for ln in text.splitlines() if ln.startswith('X1 ')]
    assert x1_lines, f'No X1 line:\n{text}'
    assert x1_lines[0].split()[-1] == '6N2P', x1_lines[0]
    assert '6N2P.lib' in text


@needs_kicad
@needs_ngspice
async def test_facade_6n2p_tran_shows_amplification(tmp_path: Path) -> None:
    """ngspice TRAN: 6Н2П (high-µ ~100) даёт gain ≥ 10× на plate."""
    sch_path = _build_triode_amp_6n2p(tmp_path / 'amp.kicad_sch')
    exporter = KicadCliSchematicExporter(_app_manager())
    netlist = await exporter.export_spice_netlist(
        sch_path, tmp_path / 'amp.cir',
    )
    simulator = NgspiceSimulator(_app_manager())
    result = await simulator.run(
        netlist, TranAnalysis(t_step=1e-5, t_stop=30e-3),
    )
    assert result.time_series is not None
    ts = result.time_series
    n = len(ts.time); skip = int(n * 0.7)
    vin = ts.traces['v(/input)'][skip:]
    vp = ts.traces['v(/plate)'][skip:]
    vin_pp = max(vin) - min(vin)
    vp_pp = max(vp) - min(vp)
    assert vin_pp > 0.005, f'Input swing too low: {vin_pp}'
    gain = vp_pp / vin_pp
    # 6Н2П triode с Rp=100k common-cathode — теор. gain до 50×, threshold
    # 10× даёт надёжный buffer.
    assert gain >= 10.0, f'Gain {gain:.1f}× ниже 10× для 6Н2П'
