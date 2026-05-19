"""T100 Phase 2 acceptance: SE pentode amp 6П14П + OPT_SE_5K_8.

T103 re-layout (2026-05-19): переписана топология после W2 risk
realized в T102 (старый layout сливал /plate с screen/OPT.P1/P2/B+
через wire-crossings без junction'ов). Новый подход:

  * EL84 (T104 Valve:EL84 symbol — anode/grid/cathode geometry, не
    Conn_01x04 stand-in).
  * OPT **выше** лампы (Y = 70), плата (P, top of EL84 на Y=77.47)
    соединяется с OPT.P1 через короткий L-route, идущий ВВЕРХ над
    B+ rail (Y=58.42) — не пересекает rail или stub'ы.
  * B+ rail кончается at X=115 (после OPT). G2 stub идёт rail-end →
    DOWN → LEFT к G2 pin (96.52, 87.63) — не пересекает plate wire.

Топология:
  V_in (10 mV @ 1 kHz) → C_in → grid; grid → R_g → GND (grid leak);
  cathode → R_k (270Ω) ∥ C_k (22µF) → GND (auto-bias);
  screen G2 → B+ напрямую через rail-stub;
  plate → OPT.P1; OPT.P2 → B+;
  OPT.S1/S2 → R_load (8 Ω) loop.

Acceptance:
  * netlist содержит X1 ... 6P14P + X2 ... OPT_SE_5K_8; оба .include.
  * ngspice TRAN: V(/plate) AC swing ≥ 5× от V(/input) (T103 threshold).
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
_TUBE_LIB = _REPO_ROOT / 'data' / 'models' / 'tubes' / 'custom' / '6P14P.lib'
_OPT_LIB = (
    _REPO_ROOT
    / 'data'
    / 'models'
    / 'transformers'
    / 'generic'
    / 'OPT_SE_5K_8.lib'
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


# Layout (mm, Y-down) на KiCad-стандартной сетке 1.27 mm.
# Vertical layering: B+ rail сверху (Y=58.42), затем OPT (Y=70),
# затем EL84 (Y=88.9) с plate (Y=77.47) выходящим UP к OPT, наконец
# cathode bias снизу (R_k/C_k Y~101). Плата соединяется с OPT.P1 через
# Y=67.46 (выше B+ rail), что исключает пересечения с любыми stub'ами.

_V_BB_AT       = (50.8, 63.5)         # rotation=0: pin_minus@(50.8,58.42)→B+ rail, pin_plus@(50.8,68.58)→GND
_GND_VBB_AT    = (50.8, 73.66)
_V_IN_AT       = (50.8, 88.9)         # pin_plus@(50.8,93.98)→GND, pin_minus@(50.8,83.82)→C_in
_GND_VIN_AT    = (50.8, 97.79)
_FLG_AT        = (45.72, 97.79)
_C_IN_AT       = (63.5, 83.82)        # rotation=90: pin_a@(59.69,83.82), pin_b@(67.31,83.82)
_R_G_AT        = (81.28, 93.98)       # pin_a@(81.28,97.79)→GND, pin_b@(81.28,90.17)=EL84.G
_GND_RG_AT     = (81.28, 101.6)
_TUBE_AT       = (88.9, 88.9)         # Valve:EL84 — G(81.28,90.17), K(86.36,97.79), P(88.9,77.47), G2(96.52,87.63)
_R_K_AT        = (86.36, 101.6)       # pin_a@(86.36,105.41)→GND, pin_b@(86.36,97.79)=EL84.K
_GND_RK_AT     = (86.36, 109.22)
_C_K_AT        = (96.52, 101.6)       # pin_a@(96.52,105.41)→GND, pin_b@(96.52,97.79)→cathode rail
_GND_CK_AT     = (96.52, 109.22)
_OPT_AT        = (115.57, 72.39)      # Transformer_1P_1S (T103 follow-up 2026-05-19, красивый symbol):
                                       # P1(105.41,67.31) primary-top, P2(105.41,77.47) primary-bottom,
                                       # S1(125.73,77.47) secondary-bottom, S2(125.73,67.31) secondary-top
_R_LOAD_AT     = (133.35, 81.28)      # rotation=0 vertical: pin_b(133.35,77.47)=OPT.S1.Y, pin_a(133.35,85.09)→GND

_BPLUS_RAIL_Y     = 58.42              # горизонталь B+: V_BB.pin_minus → X=115.57 (за OPT центром)
_BPLUS_RAIL_END_X = 115.57             # endpoint = X_opt, откуда G2 stub L-route
_PLATE_WIRE_Y     = 67.31              # plate routes к OPT.P1 — Y=67.31 (=53·1.27, on-grid)
# T103 follow-up (2026-05-19): AC-probe для visualization в KiCad
# Simulator. C_probe coupling cap + R_probe pulldown → /output_probe net
# несёт только AC компонент plate-сигнала (без 250V DC offset). На
# симуляции V(/plate) рисуется как DC ramp 0→250V с invisible ripples;
# V(/output_probe) показывает чистый AC swing вокруг 0V — наглядно.
_C_PROBE_AT       = (134.62, 49.53)    # vertical: pin_a@(134.62,53.34), pin_b@(134.62,45.72)
_R_PROBE_AT       = (134.62, 64.77)    # vertical: pin_a@(134.62,68.58)→GND, pin_b@(134.62,60.96)→/output_probe
_GND_RPROBE_AT    = (134.62, 72.39)


def _app_manager() -> SubprocessAppManager:
    return SubprocessAppManager(NativePlatformLayer())


def _build_se_amp(path: Path) -> Path:
    sch = Schematic('se_amp_6p14p')

    # T104 auto-numbering: V1, V2, C1, R1, X1 (tube), R2, C2, X2 (OPT), R3
    v_bb = sch.add_v_dc(value='250', at=_V_BB_AT)                       # V1
    v_in = sch.add_v_ac(                                                # V2
        value='VSIN', at=_V_IN_AT, amplitude=0.010, frequency=1000.0,
    )
    c_in = sch.add_capacitor(value='100n', at=_C_IN_AT, rotation=90)    # C1
    r_g = sch.add_resistor(value='470k', at=_R_G_AT)                    # R1
    xv1 = sch.add_tube(                                                 # X1
        spice_model=_tube_6p14p(), at=_TUBE_AT, symbol='Valve:EL84',
    )
    r_k = sch.add_resistor(value='270', at=_R_K_AT)                     # R2
    c_k = sch.add_capacitor(value='22u', at=_C_K_AT)                    # C2
    xt1 = sch.add_transformer(                                          # X2
        spice_model=_opt_se_5k_8(), at=_OPT_AT,
        symbol='Device:Transformer_1P_1S',
    )
    r_load = sch.add_resistor(value='8', at=_R_LOAD_AT)                 # R3
    # T103 follow-up: AC-probe для GUI visualization (C_probe + R_probe).
    # Через label-based net naming подключаем plate net к C_probe.pin_b
    # (вместо физического wire — pin лежит далеко от plate wire,
    # label proxy чище).
    # τ_probe = R·C = 1M·1n = 1 ms (короткий — за t_start=10ms = 10τ
    # успевает settled на 99.995%). AC attenuation @ 1 kHz: Xc=159k,
    # |H| = R/√(R²+Xc²) = 0.988 → 1.2% loss, OK для probe.
    # Минимальная нагрузка на plate (1M >> Z_out_pentode ≈ 38k).
    c_probe = sch.add_capacitor(value='1n', at=_C_PROBE_AT)             # C3
    r_probe = sch.add_resistor(value='1Meg', at=_R_PROBE_AT)            # R4
    gnd_vbb = sch.add_ground(at=_GND_VBB_AT)
    gnd_vin = sch.add_ground(at=_GND_VIN_AT)
    gnd_rg = sch.add_ground(at=_GND_RG_AT)
    gnd_rk = sch.add_ground(at=_GND_RK_AT)
    gnd_ck = sch.add_ground(at=_GND_CK_AT)
    gnd_rprobe = sch.add_ground(at=_GND_RPROBE_AT)
    flg = sch.add_pwr_flag(at=_FLG_AT, rotation=180)

    # === B+ rail (Y=58.42) ===
    # V_BB.pin_minus → горизонталь rail → endpoint X=115.57 (= OPT центр)
    sch.connect(
        v_bb.pin_minus,
        Position(x_mm=_BPLUS_RAIL_END_X, y_mm=_BPLUS_RAIL_Y),
    )
    # OPT.P2 stub (L-route): rail (115.57, 58.42) → DOWN (115.57, 77.47) →
    # LEFT к OPT.P2 (105.41, 77.47). X=115.57 = OPT центр (no pin там),
    # горизонталь Y=77.47 пересекает только OPT body (no electrical
    # contact). Не использовать X=105.41 vertically — это X OPT.P1 и
    # шорт plate↔B+.
    sch.connect(
        Position(x_mm=_BPLUS_RAIL_END_X, y_mm=_BPLUS_RAIL_Y),
        Position(x_mm=_BPLUS_RAIL_END_X, y_mm=77.47),
    )
    sch.connect(
        Position(x_mm=_BPLUS_RAIL_END_X, y_mm=77.47),
        xt1.pin('P2'),
    )
    # G2 stub L-route: rail-mid X=96.52 (= G2 X) → DOWN → G2 pin.
    sch.connect(
        Position(x_mm=96.52, y_mm=_BPLUS_RAIL_Y),
        xv1.pin('G2'),
    )
    sch.junction(at=(96.52, _BPLUS_RAIL_Y))   # T on rail для G2 stub

    # === Plate wire (Y=67.31, ВЫШЕ rail) ===
    # EL84.P (88.9, 77.47) → corner (88.9, 67.31) → OPT.P1 (105.41, 67.31).
    # Вертикаль X=88.9 не пересекает G2 stub (X=96.52) и P2 stub (X=115.57).
    # Горизонталь Y=67.31 — anything между X=88.9-105.41? Tube body
    # extends to ~X=96.5 — wire visually проходит через body но без
    # pin contact (G2 pin at Y=87.63, plate at Y=77.47, neither Y=67.31).
    sch.connect(xv1.pin('P'), Position(x_mm=88.9, y_mm=_PLATE_WIRE_Y))
    sch.connect(
        Position(x_mm=88.9, y_mm=_PLATE_WIRE_Y),
        xt1.pin('P1'),
    )

    # === Grid wire (V_in → C_in → R_g/G_node) ===
    sch.connect(v_in.pin_minus, c_in.pin_a)
    # C_in.pin_b (67.31, 83.82) → R_g.pin_b/G (81.28, 90.17). Manhattan
    # corner = (67.31, 90.17). Horizontal Y=90.17 в X-диапазоне 67.31→81.28
    # — не пересекает R_g body (X=81.28, but endpoint), не пересекает
    # tube pins (G at X=81.28 endpoint).
    sch.connect(c_in.pin_b, xv1.pin('G'))
    sch.junction(at=(_R_G_AT[0], 90.17))   # T: R_g.pin_b + G pin + wire end

    # === Cathode rail (Y=97.79) ===
    # K (86.36, 97.79) overlaps with R_k.pin_b; wire к C_k.pin_b (96.52,97.79)
    sch.connect(xv1.pin('K'), c_k.pin_b)
    sch.junction(at=(_R_K_AT[0], 97.79))   # T: K + R_k.pin_b + wire start

    # === Secondary loop (R_load between S1 и S2) ===
    # Transformer_1P_1S secondary справа OPT: S1(125.73, 77.47),
    # S2(125.73, 67.31). R_load (133.35, 81.28): pin_b(133.35, 77.47),
    # pin_a(133.35, 85.09). Прямые wire'ы без conflict'ов.
    # S1 (125.73, 77.47) → R_load.pin_b (133.35, 77.47): horizontal Y=77.47.
    sch.connect(xt1.pin('S1'), r_load.pin_b)
    # S2 (125.73, 67.31) → R_load.pin_a (133.35, 85.09): L-route, corner
    # справа OPT (133.35, 67.31). Вертикаль X=133.35 от Y=67.31 до 85.09
    # не пересекает S1 (X=125.73) и R_load body — OK.
    sch.connect(
        xt1.pin('S2'),
        Position(x_mm=133.35, y_mm=67.31),
    )
    sch.connect(
        Position(x_mm=133.35, y_mm=67.31),
        r_load.pin_a,
    )

    # === AC-probe (T103 follow-up): C_probe AC-couple plate → /output_probe ===
    # Wire: C_probe.pin_a (134.62, 53.34) → R_probe.pin_b (134.62, 60.96).
    sch.connect(c_probe.pin_a, r_probe.pin_b)
    sch.connect(r_probe.pin_a, gnd_rprobe.pin)
    # Label '/plate' на C_probe.pin_b — net merge с EL84.P /plate net.
    sch.label('plate', at=c_probe.pin_b)

    # === GND-стержни ===
    sch.connect(v_bb.pin_plus, gnd_vbb.pin)
    sch.connect(v_in.pin_plus, gnd_vin.pin)
    sch.connect(r_g.pin_a, gnd_rg.pin)
    sch.connect(r_k.pin_a, gnd_rk.pin)
    sch.connect(c_k.pin_a, gnd_ck.pin)
    sch.connect(flg.pin, v_in.pin_plus)

    # === SPICE-trace labels ===
    sch.label('input', at=v_in.pin_minus)
    sch.label('plate', at=xv1.pin('P'))
    sch.label('output_probe', at=c_probe.pin_a)       # AC-only после C_probe
    sch.label('sec_a', at=xt1.pin('S1'))
    sch.label('sec_b', at=xt1.pin('S2'))

    # .tran с uic — ngspice использует initial conditions (нули) и
    # интегрирует TRAN. Без uic SPICE-bias point sometimes diverges для
    # SE-amp (OPT primary как DC short между plate и B+, лампа auto-bias
    # через R_k — non-trivial nonlinear solve). τ_Ck = 270·22µF ≈ 5.9 ms;
    # t_stop = 80 ms = ~14τ — больше для надёжного settling с uic-start.
    # t_start = 10 ms — ngspice выводит данные только после 10 ms
    # (= 10τ_probe), переходный процесс /output_probe не попадает в
    # waveform-output, KiCad Simulator рисует только steady-state AC.
    sch.spice_directive('.tran 10u 80m 10m uic', at=(50.8, 115.57))

    return sch.save(path)


async def _export_netlist(schematic_path: Path, netlist_path: Path) -> Path:
    exporter = KicadCliSchematicExporter(_app_manager())
    return await exporter.export_spice_netlist(schematic_path, netlist_path)


@needs_kicad
async def test_facade_se_amp_writes_subckt_instances_and_includes(
    tmp_path: Path,
) -> None:
    """Netlist содержит X1/X2 X-инстансы + два .include для tube/OPT."""
    sch_path = _build_se_amp(tmp_path / 'se_amp.kicad_sch')
    netlist = await _export_netlist(sch_path, tmp_path / 'se_amp.cir')
    text = netlist.read_text()
    # X-instance для tube
    x1_lines = [ln for ln in text.splitlines() if ln.startswith('X1 ')]
    assert x1_lines, f'No X1 line:\n{text}'
    assert x1_lines[0].split()[-1] == '6P14P', x1_lines[0]
    # X-instance для OPT
    x2_lines = [ln for ln in text.splitlines() if ln.startswith('X2 ')]
    assert x2_lines, f'No X2 line:\n{text}'
    assert x2_lines[0].split()[-1] == 'OPT_SE_5K_8', x2_lines[0]
    # .include для обеих библиотек
    assert '6P14P.lib' in text, text
    assert 'OPT_SE_5K_8.lib' in text, text


@needs_kicad
@needs_ngspice
async def test_facade_se_amp_tran_shows_amplification(tmp_path: Path) -> None:
    """T103 acceptance: AC swing на /plate ≥ 5× от /input — лампа усиливает."""
    sch_path = _build_se_amp(tmp_path / 'se_amp.kicad_sch')
    netlist = await _export_netlist(sch_path, tmp_path / 'se_amp.cir')
    simulator = NgspiceSimulator(_app_manager())

    result = await simulator.run(
        netlist, TranAnalysis(t_step=1e-5, t_stop=80e-3),
    )
    assert result.time_series is not None
    ts = result.time_series

    # Берём последние 20% точек — после bias settling (>5τ).
    n = len(ts.time)
    skip = int(n * 0.8)
    vin = ts.traces['v(/input)'][skip:]
    vp = ts.traces['v(/plate)'][skip:]

    vin_pp = max(vin) - min(vin)
    vp_pp = max(vp) - min(vp)
    assert vin_pp > 0.005, f'Input swing too low: {vin_pp}'
    gain = vp_pp / vin_pp
    assert gain >= 5.0, (
        f'Plate gain {gain:.1f}× ниже порога 5× (SE pentode)'
    )
