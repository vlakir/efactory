"""T107 acceptance: working schemas с custom Soviet tube snippets.

3 demo-фикстуры:
* **GU50** common-cathode pentode amp (RU power pentode, 25W rated)
* **6П45С** common-cathode beam tetrode amp (RU sweep tube, 35W rated)
* **6Н6П** common-cathode triode amp (RU dual triode, ~µ=20, use ½)

Каждая использует kustom snippet `Tubes_Soviet:<NAME>` + T006 SPICE
SUBCKT через `Sim.Library`/`Sim.Name` properties. Acceptance — ngspice
прогоняет схему и даёт реальное усиление на plate.

Topology: common-cathode R-loaded без OPT (как triode_amp_6p14p в T104
demo — стабильно работает, обходит W2 risk).
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

_REPO_ROOT = Path(__file__).resolve().parents[4]
_TUBE_DIR = _REPO_ROOT / 'data' / 'models' / 'tubes' / 'custom'


def _pentode_model(tube_id: str) -> SpiceModel:
    return SpiceModel(
        id=tube_id, name=tube_id,
        category=ComponentCategory.TUBE, subcategory='pentode',
        source=ModelSource.CUSTOM,
        file_path=_TUBE_DIR / f'{tube_id}.lib',
        subckt_pins=('P', 'G2', 'G', 'K'),
    )


def _triode_model(tube_id: str) -> SpiceModel:
    return SpiceModel(
        id=tube_id, name=tube_id,
        category=ComponentCategory.TUBE, subcategory='triode',
        source=ModelSource.CUSTOM,
        file_path=_TUBE_DIR / f'{tube_id}.lib',
        subckt_pins=('P', 'G', 'K'),
    )


def _app_manager() -> SubprocessAppManager:
    return SubprocessAppManager(NativePlatformLayer())


# ─────────────────────────────────────────────────────────────────────────
# Pentode common-cathode amp builder (для GU50, 6П45С).
# ─────────────────────────────────────────────────────────────────────────
def _build_pentode_amp(
    path: Path, *, tube_id: str, symbol: str,
    r_p_value: str = '4.7k', r_k_value: str = '270',
    vbb_value: str = '250',
) -> Path:
    sch = Schematic(f'pentode_amp_{tube_id.lower()}')
    v_bb = sch.add_v_dc(value=vbb_value, at=(50.8, 55.88))
    v_in = sch.add_v_ac(
        value='VSIN', at=(50.8, 80.01), amplitude=0.010, frequency=1000.0,
    )
    c_in = sch.add_capacitor(value='100n', at=(63.5, 74.93), rotation=90)
    r_g = sch.add_resistor(value='470k', at=(81.28, 85.09))
    r_p = sch.add_resistor(value=r_p_value, at=(101.6, 64.77))
    xv1 = sch.add_tube(
        spice_model=_pentode_model(tube_id),
        at=(101.6, 80.01),
        symbol=symbol,
    )
    r_k = sch.add_resistor(value=r_k_value, at=(99.06, 92.71))
    c_k = sch.add_capacitor(value='22u', at=(109.22, 92.71))
    gnd_vbb = sch.add_ground(at=(50.8, 64.77))
    gnd_vin = sch.add_ground(at=(50.8, 88.9))
    gnd_rg = sch.add_ground(at=(81.28, 91.44))
    gnd_rk = sch.add_ground(at=(99.06, 99.06))
    gnd_ck = sch.add_ground(at=(109.22, 99.06))
    flg = sch.add_pwr_flag(at=(45.72, 88.9), rotation=180)

    # B+ rail Y=50.8 → R_p stub + G2 stub
    sch.connect(v_bb.pin_minus, Position(x_mm=109.22, y_mm=50.8))
    sch.connect(Position(x_mm=101.6, y_mm=50.8), r_p.pin_b)
    sch.junction(at=(101.6, 50.8))
    sch.connect(Position(x_mm=109.22, y_mm=50.8), xv1.pin('G2'))

    # Grid wire (V_in → C_in → G)
    sch.connect(v_in.pin_minus, c_in.pin_a)
    sch.connect(c_in.pin_b, xv1.pin('G'))
    sch.junction(at=(81.28, 90.17))   # R_g.pin_b joins grid wire

    # Cathode rail
    sch.connect(xv1.pin('K'), c_k.pin_b)
    sch.junction(at=(99.06, 88.9))

    # GND
    sch.connect(v_bb.pin_plus, gnd_vbb.pin)
    sch.connect(v_in.pin_plus, gnd_vin.pin)
    sch.connect(r_g.pin_a, gnd_rg.pin)
    sch.connect(r_k.pin_a, gnd_rk.pin)
    sch.connect(c_k.pin_a, gnd_ck.pin)
    sch.connect(flg.pin, v_in.pin_plus)

    sch.label('input', at=v_in.pin_minus)
    sch.label('plate', at=xv1.pin('P'))

    sch.spice_directive('.tran 10u 30m uic', at=(50.8, 105.41))
    return sch.save(path)


# ─────────────────────────────────────────────────────────────────────────
# Triode common-cathode amp builder (для 6Н6П).
# ─────────────────────────────────────────────────────────────────────────
def _build_triode_amp(
    path: Path, *, tube_id: str, symbol: str,
    r_p_value: str = '47k', r_k_value: str = '1k',
    vbb_value: str = '250',
) -> Path:
    sch = Schematic(f'triode_amp_{tube_id.lower()}')
    v_bb = sch.add_v_dc(value=vbb_value, at=(50.8, 55.88))
    v_in = sch.add_v_ac(
        value='VSIN', at=(50.8, 80.01), amplitude=0.010, frequency=1000.0,
    )
    c_in = sch.add_capacitor(value='100n', at=(63.5, 74.93), rotation=90)
    r_g = sch.add_resistor(value='1Meg', at=(81.28, 85.09))
    r_p = sch.add_resistor(value=r_p_value, at=(101.6, 64.77))
    xv1 = sch.add_tube(
        spice_model=_triode_model(tube_id),
        at=(101.6, 80.01),
        symbol=symbol,
    )
    r_k = sch.add_resistor(value=r_k_value, at=(99.06, 92.71))
    c_k = sch.add_capacitor(value='22u', at=(109.22, 92.71))
    gnd_vbb = sch.add_ground(at=(50.8, 64.77))
    gnd_vin = sch.add_ground(at=(50.8, 88.9))
    gnd_rg = sch.add_ground(at=(81.28, 91.44))
    gnd_rk = sch.add_ground(at=(99.06, 99.06))
    gnd_ck = sch.add_ground(at=(109.22, 99.06))
    flg = sch.add_pwr_flag(at=(45.72, 88.9), rotation=180)

    # B+ rail → R_p stub
    sch.connect(v_bb.pin_minus, Position(x_mm=101.6, y_mm=50.8))
    sch.connect(Position(x_mm=101.6, y_mm=50.8), r_p.pin_b)

    # Plate wire (триод — нет G2)
    sch.connect(r_p.pin_a, xv1.pin('P'))

    # Grid
    sch.connect(v_in.pin_minus, c_in.pin_a)
    sch.connect(c_in.pin_b, xv1.pin('G'))
    sch.junction(at=(81.28, 90.17))

    # Cathode
    sch.connect(xv1.pin('K'), c_k.pin_b)
    sch.junction(at=(99.06, 88.9))

    # GND
    sch.connect(v_bb.pin_plus, gnd_vbb.pin)
    sch.connect(v_in.pin_plus, gnd_vin.pin)
    sch.connect(r_g.pin_a, gnd_rg.pin)
    sch.connect(r_k.pin_a, gnd_rk.pin)
    sch.connect(c_k.pin_a, gnd_ck.pin)
    sch.connect(flg.pin, v_in.pin_plus)

    sch.label('input', at=v_in.pin_minus)
    sch.label('plate', at=xv1.pin('P'))

    sch.spice_directive('.tran 10u 30m uic', at=(50.8, 105.41))
    return sch.save(path)


async def _run_tran_gain(schematic: Path, tmp_path: Path) -> float:
    am = _app_manager()
    netlist = await KicadCliSchematicExporter(am).export_spice_netlist(
        schematic, tmp_path / (schematic.stem + '.cir'),
    )
    result = await NgspiceSimulator(am).run(
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
    return vp_pp / vin_pp


# ────────── Test cases ──────────

@needs_kicad
@needs_ngspice
async def test_gu50_pentode_amp_amplifies(tmp_path: Path) -> None:
    """GU50 power pentode common-cathode — gain ≥ 5×."""
    sch_path = _build_pentode_amp(
        tmp_path / 'gu50.kicad_sch',
        tube_id='GU50', symbol='Tubes_Soviet:GU50',
    )
    text = sch_path.read_text(encoding='utf-8')
    assert '(lib_id "Tubes_Soviet:GU50")' in text

    gain = await _run_tran_gain(sch_path, tmp_path)
    assert gain >= 5.0, f'GU50 gain {gain:.1f}× ниже порога 5×'


@needs_kicad
@needs_ngspice
async def test_6p45s_beam_tetrode_amp_amplifies(tmp_path: Path) -> None:
    """6П45С beam tetrode common-cathode — gain ≥ 5×."""
    sch_path = _build_pentode_amp(
        tmp_path / '6p45s.kicad_sch',
        tube_id='6P45S', symbol='Tubes_Soviet:6P45S',
    )
    text = sch_path.read_text(encoding='utf-8')
    assert '(lib_id "Tubes_Soviet:6P45S")' in text

    gain = await _run_tran_gain(sch_path, tmp_path)
    assert gain >= 5.0, f'6P45S gain {gain:.1f}× ниже порога 5×'


@needs_kicad
@needs_ngspice
async def test_6n6p_triode_amp_amplifies(tmp_path: Path) -> None:
    """6Н6П low-µ triode common-cathode — gain ≥ 5× (µ≈20, ожидаем 10-15×)."""
    sch_path = _build_triode_amp(
        tmp_path / '6n6p.kicad_sch',
        tube_id='6N6P', symbol='Tubes_Soviet:6N6P',
    )
    text = sch_path.read_text(encoding='utf-8')
    assert '(lib_id "Tubes_Soviet:6N6P")' in text

    gain = await _run_tran_gain(sch_path, tmp_path)
    assert gain >= 5.0, f'6N6P gain {gain:.1f}× ниже порога 5×'
