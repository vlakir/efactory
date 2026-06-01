"""T166 acceptance: 6Н30П-EB SE-amp sanity check.

Simple common-cathode SE preamp fixture для верификации ngspice SPICE
simulation. 6Н30П-EB — Sovtek/EH dual-triode, low-µ (~15) high-current
(~30 mA) for high-end audiophile driver / line stage (Audio Note Kondo,
BAT VK-30 reference).

Topology: V_in → C_in → V1.G; V_BB → R_p → V1.P; V1.K → R_k ‖ C_k → GND.

Acceptance:
  * netlist contains X1 ... 6N30P_EB + .include 6N30P_EB.lib.
  * ngspice TRAN: V_plate AC swing ≥ 3× от V_in (low-µ ~15 triode amp
    — gain bound limited by μ; 3× threshold safe).
  * OP-point V1 в active region.
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
from domain.simulation import OpAnalysis, TranAnalysis
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
    / 'data' / 'models' / 'tubes' / 'custom' / '6N30P_EB.lib'
)


def _tube_6n30p_eb() -> SpiceModel:
    return SpiceModel(
        id='6N30P_EB',
        name='6Н30П-EB',
        category=ComponentCategory.TUBE,
        subcategory='triode',
        source=ModelSource.CUSTOM,
        file_path=_TUBE_LIB,
        subckt_pins=('P', 'G', 'K'),
    )


def _app_manager() -> SubprocessAppManager:
    return SubprocessAppManager(NativePlatformLayer())


def _build_6n30p_eb_se_amp(path: Path) -> Path:
    """Common-cathode SE amp на 6Н30П-EB через Valve:ECC88 (½ dual triode).

    6Н30П-EB low-µ high-current bias: V_BB=200V, R_p=4.7k, R_k=82 ‖ C_k=22µ.
    Expected Q-point: V_a≈50-100V, V_K≈2-3V, I_a≈20-35mA (high-current).
    """
    sch = Schematic('se_amp_6n30p_eb')

    v_bb = sch.add_v_dc(value='200', at=(50.8, 55.88))
    v_in = sch.add_v_ac(
        value='VSIN', at=(50.8, 80.01), amplitude=0.010, frequency=1000.0,
    )
    c_in = sch.add_capacitor(value='100n', at=(63.5, 74.93), rotation=90)
    r_g = sch.add_resistor(value='1Meg', at=(81.28, 85.09))
    r_p = sch.add_resistor(value='4.7k', at=(101.6, 64.77))
    xv1 = sch.add_tube(
        spice_model=_tube_6n30p_eb(), at=(101.6, 80.01),
        symbol='Valve:ECC88',
    )
    r_k = sch.add_resistor(value='82', at=(99.06, 93.98))
    c_k = sch.add_capacitor(value='22u', at=(109.22, 93.98))
    gnd_vbb = sch.add_ground(at=(50.8, 64.77))
    gnd_vin = sch.add_ground(at=(50.8, 88.9))
    gnd_rg = sch.add_ground(at=(81.28, 91.44))
    gnd_rk = sch.add_ground(at=(99.06, 101.6))
    gnd_ck = sch.add_ground(at=(109.22, 101.6))
    flg = sch.add_pwr_flag(at=(45.72, 88.9), rotation=180)

    sch.connect(v_bb.pin_minus, Position(x_mm=101.6, y_mm=50.8))
    sch.connect(Position(x_mm=101.6, y_mm=50.8), r_p.pin_b)
    sch.connect(r_p.pin_a, xv1.pin('P'))
    sch.connect(v_in.pin_minus, c_in.pin_a)
    sch.connect(c_in.pin_b, xv1.pin('G'))
    sch.connect(r_g.pin_b, xv1.pin('G'))
    sch.connect(xv1.pin('K'), c_k.pin_b)
    sch.connect(v_bb.pin_plus, gnd_vbb.pin)
    sch.connect(v_in.pin_plus, gnd_vin.pin)
    sch.connect(r_g.pin_a, gnd_rg.pin)
    sch.connect(r_k.pin_a, gnd_rk.pin)
    sch.connect(c_k.pin_a, gnd_ck.pin)
    sch.connect(flg.pin, v_in.pin_plus)

    sch.label('input', at=v_in.pin_minus)
    sch.label('plate', at=xv1.pin('P'))
    sch.label('cathode', at=xv1.pin('K'))

    sch.spice_directive('.tran 10u 30m uic', at=(50.8, 110.0))
    return sch.save(path)


@needs_kicad
async def test_facade_6n30p_eb_netlist_includes_subckt(
    tmp_path: Path,
) -> None:
    """X1 ... 6N30P_EB в netlist + .include 6N30P_EB.lib."""
    sch_path = _build_6n30p_eb_se_amp(tmp_path / 'amp.kicad_sch')
    exporter = KicadCliSchematicExporter(_app_manager())
    netlist = await exporter.export_spice_netlist(
        sch_path, tmp_path / 'amp.cir',
    )
    text = netlist.read_text()
    x1_lines = [ln for ln in text.splitlines() if ln.startswith('X1 ')]
    assert x1_lines, f'No X1 line:\n{text}'
    assert x1_lines[0].split()[-1] == '6N30P_EB', x1_lines[0]
    assert '6N30P_EB.lib' in text


@needs_kicad
@needs_ngspice
async def test_facade_6n30p_eb_op_point_active_region(
    tmp_path: Path,
) -> None:
    """DC OP-point: 6Н30П-EB в active region (high-current bias)."""
    sch_path = _build_6n30p_eb_se_amp(tmp_path / 'amp.kicad_sch')
    exporter = KicadCliSchematicExporter(_app_manager())
    netlist = await exporter.export_spice_netlist(
        sch_path, tmp_path / 'amp.cir',
    )
    simulator = NgspiceSimulator(_app_manager())
    result = await simulator.run(netlist, analysis=OpAnalysis())
    assert result.operating_points is not None

    nodes = {}
    for k, v in result.operating_points.items():
        if k.startswith('v(') and k.endswith(')'):
            nodes[k[2:-1].lstrip('/').lower()] = v

    assert 'plate' in nodes, nodes
    assert 'cathode' in nodes, nodes
    v_plate = nodes['plate']
    v_cath = nodes['cathode']

    # 6Н30П-EB high-current → V_plate lower (more drop across R_p).
    # V_BB=200, R_p=4.7k, I_a≈20-35mA → V_drop=94-164V → V_a=36-106V.
    assert 30.0 <= v_plate <= 150.0, (
        f'V_plate out of active region: {v_plate:.2f} V'
    )
    # V_cathode ≈ I_a · R_k = 25mA·82Ω ≈ 2V (auto-bias).
    assert 0.5 <= v_cath <= 5.0, (
        f'V_cathode auto-bias implausible: {v_cath:.2f} V'
    )

    # I_a estimate: V_drop / R_p = (V_BB - V_plate) / 4.7k mA.
    i_a_ma = (200.0 - v_plate) / 4.7
    assert 15.0 <= i_a_ma <= 50.0, (
        f'I_a_q out of high-current window: {i_a_ma:.2f} mA '
        f'(expected 20-40 mA для 6Н30П-EB low-µ tube)'
    )


@needs_kicad
@needs_ngspice
async def test_facade_6n30p_eb_tran_shows_amplification(
    tmp_path: Path,
) -> None:
    """ngspice TRAN: 6Н30П-EB (low-µ ~15) gain ≥ 3× на plate."""
    sch_path = _build_6n30p_eb_se_amp(tmp_path / 'amp.kicad_sch')
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
    n = len(ts.time)
    skip = int(n * 0.7)
    vin = ts.traces['v(/input)'][skip:]
    vp = ts.traces['v(/plate)'][skip:]
    vin_pp = max(vin) - min(vin)
    vp_pp = max(vp) - min(vp)
    assert vin_pp > 0.005, f'Input swing too low: {vin_pp}'
    gain = vp_pp / vin_pp
    # 6Н30П-EB μ=15 → CC gain bound ~10-15× в ideal. Threshold 3× safe
    # для low-µ tube.
    assert gain >= 3.0, f'Gain {gain:.1f}× ниже 3× для 6Н30П-EB'
