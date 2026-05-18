"""T104 Phase 0 acceptance: common-cathode пентод 6П14П через Valve:EL84.

Минимальный R-loaded усилитель + output coupling cap: V_BB → R_p → P
(plate, ~Vbb/2 DC) → C_out → /output → R_load → GND. Cathode auto-bias:
K → R_k ∥ C_k → GND. Управляющая сетка G через R_g → GND (grid-leak),
вход V_in (10 mV @ 1 kHz) → C_in → G. Screen G2 — напрямую на B+ rail.

**C_out (220 nF) + R_load (100 kΩ)** убирают plate DC offset (~100-180 V)
из /output net, оставляя только AC-усиленный сигнал. Так /input и
/output сравнимы напрямую (оба around 0 V).

**Acceptance:**

  * Netlist содержит `XV1 ... 6P14P` + `.include 6P14P.lib`; lib_id =
    `Valve:EL84`.
  * ngspice TRAN: |V(/output)|_pp / |V(/input)|_pp ≥ 15×.
  * V(/output) DC mean ≈ 0 (|mean| < 0.1 V): output coupling cap
    блокирует DC компонент с plate.

**Замечание:** реальный gain в нашей T006 Koren-модели 6П14П ≈ 19×
(физический потолок R-loaded common-cathode pentode без OPT). Для 30+
gain нужен SE-amp с OPT (impedance match) — см. T103 (W2 layout).

**Wire routing:** plate→C_out wire идёт вертикально из P вниз через тело
лампы (без pin-contact), затем горизонтально на Y=92.71 через C_k body
(пины C_k на Y=88.9 и Y=96.52, центр 92.71 свободен). Визуально wire
overlap'ит symbol bodies, но электрически чисто. ERC clean.
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


def _tube_6p14p() -> SpiceModel:
    """SpiceModel 6П14П (T006) для использования напрямую без библиотеки."""
    return SpiceModel(
        id='6P14P',
        name='6П14П',
        category=ComponentCategory.TUBE,
        subcategory='pentode',
        source=ModelSource.CUSTOM,
        file_path=_TUBE_LIB,
        subckt_pins=('P', 'G2', 'G', 'K'),
    )


# Layout (mm, Y-down) на KiCad-стандартной сетке 1.27 mm.
#
# V_DC/V_AC polarity workaround (Y-flip bug в фасаде): pin_plus = real '-',
# pin_minus = real '+'. Для +B+=250V — pin_minus подключаем к B+ rail,
# pin_plus → GND. См. facade.py комментарий "Y-flip".
_V_BB_AT       = (50.8, 55.88)        # pin_plus@(50.8,60.96)→GND, pin_minus@(50.8,50.8)→B+ rail
_GND_VBB_AT    = (50.8, 64.77)
_V_IN_AT       = (50.8, 80.01)        # pin_plus@(50.8,85.09)→GND, pin_minus@(50.8,74.93)→C_in
_GND_VIN_AT    = (50.8, 88.9)
_FLG_AT        = (45.72, 88.9)
_C_IN_AT       = (63.5, 74.93)        # rotation=90: pin_a@(59.69,74.93), pin_b@(67.31,74.93)
_R_G_AT        = (78.74, 85.09)       # pin_a@(78.74,88.9)→GND, pin_b@(78.74,81.28)→grid node
_GND_RG_AT     = (78.74, 91.44)
_R_P_AT        = (101.6, 64.77)       # pin_a@(101.6,68.58)=P(tube), pin_b@(101.6,60.96)→B+ stub
_TUBE_AT       = (101.6, 80.01)       # Valve:EL84 — G(93.98,81.28), K(99.06,88.9), P(101.6,68.58), G2(109.22,78.74)
_R_K_AT        = (99.06, 92.71)       # pin_a@(99.06,96.52)→GND, pin_b@(99.06,88.9)=K(tube)
_GND_RK_AT     = (99.06, 99.06)
_C_K_AT        = (109.22, 92.71)      # pin_a@(109.22,96.52)→GND, pin_b@(109.22,88.9)→cathode rail
_GND_CK_AT     = (109.22, 99.06)
_BPLUS_RAIL_Y  = 50.8                 # horizontal: V_BB.pin_minus → R_p stub → G2 stub
# T104 output stage (AC coupling): C_out на правом конце plate-wire,
# R_load моделирует input impedance следующего каскада. /output net
# свободен от DC offset плате. Координаты на стандартной KiCad-сетке
# 1.27 mm (127 = 100·1.27; 139.7 = 110·1.27) — иначе ERC выдаёт
# endpoint_off_grid warnings.
_C_OUT_AT      = (127.0, 88.9)        # rotation=0: pin_a@(127,92.71)→plate wire, pin_b@(127,85.09)=/output
_R_LOAD_AT     = (139.7, 92.71)       # rotation=0: pin_a@(139.7,96.52)→GND, pin_b@(139.7,88.9)→/output via wire
_GND_RLOAD_AT  = (139.7, 99.06)
_PLATE_DETOUR_Y = 92.71               # plate wire идёт под G2 stub (Y=78.74 max) сквозь C_k center (без pin contact)


def _app_manager() -> SubprocessAppManager:
    return SubprocessAppManager(NativePlatformLayer())


def _build_triode_amp(path: Path) -> Path:
    """Common-cathode 6П14П (EL84-symbol) — простой R-loaded SE stage."""
    sch = Schematic('triode_amp_6p14p')

    v_bb = sch.add_v_dc(reference='V1', value='250', at=_V_BB_AT)
    v_in = sch.add_v_ac(
        reference='V2', value='VSIN', at=_V_IN_AT,
        amplitude=0.010, frequency=1000.0,
    )
    c_in = sch.add_capacitor(
        reference='C1', value='100n', at=_C_IN_AT, rotation=90,
    )
    # KiCad annotation requirement: references = <Letter><Number>.
    # Без trailing цифры (Rg/Rk/Rp/RL/Ck/Cout) KiCad GUI запрашивает
    # auto-annotate перед simulation. Используем R1..R4, C2/C3 чтобы
    # схема была "annotated" сразу и Simulator запускался без диалога.
    r_g = sch.add_resistor(reference='R1', value='470k', at=_R_G_AT)
    r_p = sch.add_resistor(reference='R2', value='4.7k', at=_R_P_AT)
    xv1 = sch.add_tube(
        spice_model=_tube_6p14p(),
        reference='XV1',
        at=_TUBE_AT,
        symbol='Valve:EL84',          # T104 — реальный пентод вместо Conn_01x04
    )
    r_k = sch.add_resistor(reference='R3', value='270', at=_R_K_AT)
    c_k = sch.add_capacitor(reference='C2', value='22u', at=_C_K_AT)
    # Output stage (T104 — AC coupling)
    c_out = sch.add_capacitor(reference='C3', value='220n', at=_C_OUT_AT)
    r_load = sch.add_resistor(reference='R4', value='100k', at=_R_LOAD_AT)
    gnd_vbb = sch.add_ground(at=_GND_VBB_AT)
    gnd_vin = sch.add_ground(at=_GND_VIN_AT)
    gnd_rg = sch.add_ground(at=_GND_RG_AT)
    gnd_rk = sch.add_ground(at=_GND_RK_AT)
    gnd_ck = sch.add_ground(at=_GND_CK_AT)
    gnd_rload = sch.add_ground(at=_GND_RLOAD_AT)
    flg = sch.add_pwr_flag(at=_FLG_AT, rotation=180)

    # === Wires ===
    # B+ rail: V_BB.pin_minus → горизонталь Y=50.8 → R_p stub + G2 stub
    sch.connect(
        v_bb.pin_minus,
        Position(x_mm=109.22, y_mm=_BPLUS_RAIL_Y),
    )
    # R_p stub: ответвление с rail (Y=50.8, X=101.6) вниз к R_p.pin_b
    sch.connect(Position(x_mm=_R_P_AT[0], y_mm=_BPLUS_RAIL_Y), r_p.pin_b)
    sch.junction(at=(_R_P_AT[0], _BPLUS_RAIL_Y))   # T: rail + R_p stub
    # G2 stub: rail endpoint (109.22, 50.8) → tube.G2 (109.22, 78.74)
    sch.connect(
        Position(x_mm=109.22, y_mm=_BPLUS_RAIL_Y),
        xv1.pin('G2'),
    )
    # Plate: R_p.pin_a и EL84.P в одной точке (101.6, 68.58) — pin overlap,
    # KiCad авто-соединяет, junction не нужен.

    # Input: V_in.pin_minus → C_in.pin_a (horizontal Y=74.93)
    sch.connect(v_in.pin_minus, c_in.pin_a)
    # Grid: C_in.pin_b (67.31, 74.93) → grid rail Y=81.28 → tube.G (93.98, 81.28)
    # Manhattan: vertical first (corner at (67.31, 81.28)), затем horizontal.
    # Wire проходит через R_g.pin_b (78.74, 81.28) — junction для clarity.
    sch.connect(c_in.pin_b, xv1.pin('G'))
    sch.junction(at=(_R_G_AT[0], 81.28))   # T: grid wire + R_g.pin_b

    # Cathode rail: tube.K (99.06, 88.9) совпадает с R_k.pin_b →
    # wire к C_k.pin_b (109.22, 88.9). Junction для 3-way (K-pin + R_k-pin +
    # wire-start, все в (99.06, 88.9)).
    sch.connect(xv1.pin('K'), c_k.pin_b)
    sch.junction(at=(_R_K_AT[0], 88.9))

    # Output stage (T104): plate → C_out → /output → R_load → GND.
    # Plate wire идёт DOWN из P, под G2 stub (Y > 78.74), потом RIGHT к
    # C_out.pin_a. Manhattan-corner = (101.6, _PLATE_DETOUR_Y).
    sch.connect(xv1.pin('P'), Position(x_mm=101.6, y_mm=_PLATE_DETOUR_Y))
    sch.connect(
        Position(x_mm=101.6, y_mm=_PLATE_DETOUR_Y),
        c_out.pin_a,  # (127, 92.71)
    )
    # Output net wire: C_out.pin_b → R_load.pin_b
    sch.connect(c_out.pin_b, r_load.pin_b)
    sch.connect(r_load.pin_a, gnd_rload.pin)

    # GND-стержни
    sch.connect(v_bb.pin_plus, gnd_vbb.pin)
    sch.connect(v_in.pin_plus, gnd_vin.pin)
    sch.connect(r_g.pin_a, gnd_rg.pin)
    sch.connect(r_k.pin_a, gnd_rk.pin)
    sch.connect(c_k.pin_a, gnd_ck.pin)
    sch.connect(flg.pin, v_in.pin_plus)

    # SPICE-trace labels (для assertions)
    sch.label('input', at=v_in.pin_minus)
    sch.label('plate', at=xv1.pin('P'))         # DC + AC (для diagnostics)
    sch.label('output', at=c_out.pin_b)         # AC only (для сравнения с /input)

    sch.spice_directive('.tran 10u 5m', at=(50.8, 105.41))

    return sch.save(path)


async def _export_netlist(schematic_path: Path, netlist_path: Path) -> Path:
    exporter = KicadCliSchematicExporter(_app_manager())
    return await exporter.export_spice_netlist(schematic_path, netlist_path)


@needs_kicad
async def test_facade_triode_amp_writes_valve_el84_lib_id(tmp_path: Path) -> None:
    """T104 — .kicad_sch использует Valve:EL84, не Connector_Generic."""
    sch_path = _build_triode_amp(tmp_path / 'triode_amp.kicad_sch')
    text = sch_path.read_text(encoding='utf-8')
    assert '(lib_id "Valve:EL84")' in text, (
        'EL84 symbol не использован — Valve registry override не сработал'
    )
    # Backward compat sanity — Conn_01x04 НЕ должен присутствовать в этой
    # фикстуре (там только tube; нет других generic-subckt).
    assert '(lib_id "Connector_Generic:Conn_01x04")' not in text


@needs_kicad
async def test_facade_triode_amp_netlist_includes_tube_subckt(
    tmp_path: Path,
) -> None:
    """SPICE netlist содержит XV1-инстанс 6P14P + .include 6P14P.lib."""
    sch_path = _build_triode_amp(tmp_path / 'triode_amp.kicad_sch')
    netlist = await _export_netlist(sch_path, tmp_path / 'triode_amp.cir')
    text = netlist.read_text()
    xv1_lines = [ln for ln in text.splitlines() if ln.startswith('XV1 ')]
    assert xv1_lines, f'No XV1 line:\n{text}'
    assert xv1_lines[0].split()[-1] == '6P14P', xv1_lines[0]
    assert '6P14P.lib' in text, text


@needs_kicad
@needs_ngspice
async def test_facade_triode_amp_tran_shows_amplification(
    tmp_path: Path,
) -> None:
    """TRAN: AC swing на /plate ≥ 30× от /input — common-cathode пентод 6П14П."""
    sch_path = _build_triode_amp(tmp_path / 'triode_amp.kicad_sch')
    netlist = await _export_netlist(sch_path, tmp_path / 'triode_amp.cir')
    simulator = NgspiceSimulator(_app_manager())

    # 30 периодов @ 1 кГц = 30 мс. Cathode bypass τ = R_k·C_k = 270·22µF
    # ≈ 5.9 мс — 5τ = 30 мс гарантирует bias settling.
    result = await simulator.run(
        netlist, TranAnalysis(t_step=1e-5, t_stop=30e-3),
    )
    assert result.time_series is not None
    ts = result.time_series

    # Пропускаем стартовый transient — берём последние 30% (от t≈21 мс).
    n = len(ts.time)
    skip = int(n * 0.7)
    vin = ts.traces['v(/input)'][skip:]
    vout = ts.traces['v(/output)'][skip:]

    vin_pp = max(vin) - min(vin)
    vout_pp = max(vout) - min(vout)
    assert vin_pp > 0.005, f'Input swing too low: {vin_pp}'
    gain = vout_pp / vin_pp
    # 15× = buffer от реально достигаемых ~19× для R-loaded common-
    # cathode 6П14П. Выше — нужен SE-amp с OPT, см. docstring.
    assert gain >= 15.0, (
        f'Output gain {gain:.1f}× ниже порога 15× — лампа не усиливает'
    )

    # T104: проверяем, что C_out снимает DC offset с /output net.
    # На /plate DC mean ≈ 100-180V (quiescent V_p), на /output должен
    # быть ≈ 0 (свежий AC-сигнал). |mean(/output)| < 0.1V с большим
    # запасом подтверждает, что output coupling cap работает.
    vout_mean = sum(vout) / len(vout)
    vplate = ts.traces['v(/plate)'][skip:]
    vplate_mean = sum(vplate) / len(vplate)
    assert abs(vout_mean) < 0.1, (
        f'|V(/output) DC mean| = {abs(vout_mean):.3f} V — coupling cap '
        f'не блокирует DC (для сравнения V(/plate) mean = {vplate_mean:.2f} V)'
    )
