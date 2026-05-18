"""T100 Phase 2 acceptance: common-emitter BJT amplifier через фасад.

Минимальный AC-усилитель на 2N3904: voltage-divider bias + bypassed emitter
resistor. Acceptance: kicad-cli sch erc/export, ngspice TRAN, AC swing на
коллекторе ≥ 30× от входного — типичное усиление common-emitter с bypass
cap при Rc=4.7k, Ic≈2 mA (r_e ≈ 13 Ω → gain ≈ Rc/r_e ≈ 360, но снижается
сопротивлением источника, делителем и load — в реальности 50-200×, мы
проверяем порог 30).

Layout пристроен под Q_NPN pin convention (B left, C top-right, E bottom-right).
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


# 2N3904 Gummel-Poon model — стандартная Motorola spec (Bf=300, Vaf=74).
_BJT_2N3904_MODEL = (
    '.model 2N3904 NPN(Is=6.734f Xti=3 Eg=1.11 Vaf=74.03 Bf=416.4 '
    'Ne=1.259 Ise=6.734f Ikf=66.78m Xtb=1.5 Br=0.7371 Nc=2 Isc=0 '
    'Ikr=0 Rc=1 Cjc=3.638p Mjc=0.3085 Vjc=0.75 Fc=0.5 Cje=4.493p '
    'Mje=0.2593 Vje=0.75 Tr=239.5n Tf=301.2p Itf=0.4 Vtf=4 Xtf=2 Rb=10)'
)

# Layout (mm, Y-down). Все позиции на KiCad-стандартной сетке 1.27 mm.
# Топология wire-based: компоненты соединены реальными проводниками
# (Manhattan), labels только для SPICE-trace nodes (`input`/`output`).
#
# V_DC/V_AC polarity workaround (Y-flip bug в фасаде, см. facade.py): наш
# pin_plus возвращает symbol pin '1', а реальный '+' терминал в KiCad
# схеме — это symbol pin '2' = наш pin_minus. Чтобы получить Vcc=+12V,
# pin_minus подключаем к Vcc rail, pin_plus — к GND.
_V_VCC_AT = (50.8, 55.88)         # rotation=0: pin_plus@(50.8,60.96)→GND, pin_minus@(50.8,50.8)→Vcc rail
_GND_V_AT = (50.8, 64.77)
_V_IN_AT = (50.8, 80.01)          # pin_plus@(50.8,85.09)→GND, pin_minus@(50.8,74.93)→C_in
_GND_VIN_AT = (50.8, 88.9)
_FLG_AT = (45.72, 88.9)
_C_IN_AT = (63.5, 74.93)          # rotation=90: pin_a@(59.69,74.93), pin_b@(67.31,74.93)
_R_B1_AT = (78.74, 64.77)         # pin_b@(78.74,60.96)→Vcc, pin_a@(78.74,68.58)→base node
_R_B2_AT = (78.74, 80.01)         # pin_b@(78.74,76.2)→base node, pin_a@(78.74,83.82)→GND
_GND_B_AT = (78.74, 87.63)
_Q1_AT = (99.06, 73.66)           # B@(93.98,73.66), C@(101.6,68.58), E@(101.6,78.74)
_R_C_AT = (121.92, 64.77)         # pin_b@(121.92,60.96)→Vcc, pin_a@(121.92,68.58)→Q1.C
_R_E_AT = (121.92, 82.55)         # pin_b@(121.92,78.74)→Q1.E, pin_a@(121.92,86.36)→GND
_C_E_AT = (134.62, 82.55)         # pin_b@(134.62,78.74)→Q1.E (parallel R_E), pin_a@(134.62,86.36)→GND
_GND_E_AT = (121.92, 90.17)
_GND_CE_AT = (134.62, 90.17)
_VCC_RAIL_Y = 50.8                # horizontal rail соединяет V1.pin_minus, R_B1.pin_b, R_C.pin_b
_VCC_RAIL_X_END = 121.92          # до X=R_C


def _app_manager() -> SubprocessAppManager:
    return SubprocessAppManager(NativePlatformLayer())


def _build_common_emitter(path: Path) -> Path:
    """Common-emitter BJT amp на 2N3904 — net labels вместо wire-pathfinding."""
    sch = Schematic('common_emitter_bjt')

    # rotation=0 (canonical): facade pin_plus at lower Y = real '-',
    # pin_minus at upper Y = real '+'. Labels/wires свапнуты ниже.
    v_cc = sch.add_v_dc(reference='V1', value='12', at=_V_VCC_AT)
    v_in = sch.add_v_ac(
        reference='V2', value='VSIN', at=_V_IN_AT,
        amplitude=0.010, frequency=1000.0,
    )
    # C_in 100nF — τ_in = R_div_eff·C ≈ 1.4 ms (<< t_stop 5ms).
    c_in = sch.add_capacitor(
        reference='C1', value='100n', at=_C_IN_AT, rotation=90,
    )
    r_b1 = sch.add_resistor(reference='R1', value='47k', at=_R_B1_AT)
    r_b2 = sch.add_resistor(reference='R2', value='10k', at=_R_B2_AT)
    q1 = sch.add_bjt(
        reference='Q1', value='2N3904',
        polarity='NPN', model_name='2N3904',
        at=_Q1_AT, rotation=0,
    )
    r_c = sch.add_resistor(reference='R3', value='4.7k', at=_R_C_AT)
    r_e = sch.add_resistor(reference='R4', value='1k', at=_R_E_AT)
    # C_E 10μF — bypass adequate (|Xc|≈16Ω << R_E=1k @ 1kHz), τ ≈ 10ms.
    c_e = sch.add_capacitor(
        reference='C2', value='10u', at=_C_E_AT,
    )
    gnd_v = sch.add_ground(at=_GND_V_AT)
    gnd_vin = sch.add_ground(at=_GND_VIN_AT)
    gnd_b = sch.add_ground(at=_GND_B_AT)
    gnd_e = sch.add_ground(at=_GND_E_AT)
    gnd_ce = sch.add_ground(at=_GND_CE_AT)
    flg = sch.add_pwr_flag(at=_FLG_AT, rotation=180)

    # === Wires ===
    # Vcc rail: V1.pin_minus → горизонталь Y=50.8 → vertical stubs к R_B1.pin_b и R_C.pin_b
    sch.connect(v_cc.pin_minus, Position(x_mm=_VCC_RAIL_X_END, y_mm=_VCC_RAIL_Y))
    sch.connect(Position(x_mm=_R_B1_AT[0], y_mm=_VCC_RAIL_Y), r_b1.pin_b)
    sch.connect(Position(x_mm=_R_C_AT[0], y_mm=_VCC_RAIL_Y), r_c.pin_b)
    sch.junction(at=(_R_B1_AT[0], _VCC_RAIL_Y))  # T-junction Vcc rail + stub

    # Base node: R_B1.pin_a — R_B2.pin_b (вертикаль X=78.74), плюс stubs к Q1.B и C_in
    sch.connect(r_b1.pin_a, r_b2.pin_b)
    sch.connect(Position(x_mm=_R_B1_AT[0], y_mm=_Q1_AT[1]), q1.pin_b)
    sch.connect(Position(x_mm=_R_B1_AT[0], y_mm=_C_IN_AT[1]), c_in.pin_b)
    sch.junction(at=(_R_B1_AT[0], _Q1_AT[1]))      # T: vertical base wire + horiz к Q1.B
    sch.junction(at=(_R_B1_AT[0], _C_IN_AT[1]))    # T: vertical + horiz к C_in

    # Input: V_in.pin_minus → C_in.pin_a (single horizontal Y=74.93)
    sch.connect(v_in.pin_minus, c_in.pin_a)

    # Collector: Q1.C → R_C.pin_a (horizontal Y=68.58)
    sch.connect(q1.pin_c, r_c.pin_a)

    # Emitter rail: Q1.E → R_E.pin_b → C_E.pin_b (horizontal Y=78.74)
    sch.connect(q1.pin_e, r_e.pin_b)
    sch.connect(r_e.pin_b, c_e.pin_b)
    sch.junction(at=(_R_E_AT[0], _Q1_AT[1] + 5.08))  # T: R_E pin + emitter wire + C_E wire

    # GND-стержни
    sch.connect(v_cc.pin_plus, gnd_v.pin)
    sch.connect(v_in.pin_plus, gnd_vin.pin)
    sch.connect(r_b2.pin_a, gnd_b.pin)
    sch.connect(r_e.pin_a, gnd_e.pin)
    sch.connect(c_e.pin_a, gnd_ce.pin)
    sch.connect(flg.pin, v_in.pin_plus)

    # SPICE-trace labels (только на нужные net'ы)
    sch.label('input', at=v_in.pin_minus)
    sch.label('output', at=q1.pin_c)

    sch.spice_directive(_BJT_2N3904_MODEL, at=(50.8, 99.06))
    # БЕЗ `uic` — даём ngspice найти DC bias point (.op), иначе transient
    # 5ms не успевает осесть в steady state (C_in/C_E settling) и сигнал
    # на выходе — артефакт переходного процесса. C_in=100n, C_E=10μF
    # дают τ << t_stop, settling меньше 1ms.
    sch.spice_directive('.tran 10u 5m', at=(50.8, 104.14))

    return sch.save(path)


async def _export_netlist(schematic_path: Path, netlist_path: Path) -> Path:
    exporter = KicadCliSchematicExporter(_app_manager())
    return await exporter.export_spice_netlist(schematic_path, netlist_path)


@needs_kicad
async def test_facade_common_emitter_writes_q1_instance_and_model(
    tmp_path: Path,
) -> None:
    """SPICE netlist содержит Q1-инстанс 2N3904 + .model card."""
    sch_path = _build_common_emitter(tmp_path / 'ce.kicad_sch')
    netlist = await _export_netlist(sch_path, tmp_path / 'ce.cir')
    text = netlist.read_text()
    # Q1 — три node (C/B/E порядок) и model name
    assert ' 2N3904' in text, text
    assert '.model 2N3904 NPN' in text, text
    # Должен присутствовать Q1 с указанием модели в конце строки
    q_lines = [ln for ln in text.splitlines() if ln.startswith('Q1 ')]
    assert q_lines, f'No Q1 line in netlist:\n{text}'
    assert q_lines[0].split()[-1] == '2N3904', q_lines[0]


@needs_kicad
@needs_ngspice
async def test_facade_common_emitter_amplifies_signal(tmp_path: Path) -> None:
    """TRAN: AC swing на collector ≥ 30× от входного — common-emitter gain."""
    sch_path = _build_common_emitter(tmp_path / 'ce.kicad_sch')
    netlist = await _export_netlist(sch_path, tmp_path / 'ce.cir')
    simulator = NgspiceSimulator(_app_manager())

    # 5 периодов @ 1 kHz = 5 мс; шаг 10 мкс даёт 500 точек.
    result = await simulator.run(
        netlist, TranAnalysis(t_step=1e-5, t_stop=5e-3),
    )
    assert result.time_series is not None
    ts = result.time_series

    # Возьмём последние 80% точек — пропускаем стартовый transient.
    n = len(ts.time)
    skip = int(n * 0.2)
    vin = ts.traces['v(/input)'][skip:]
    vc = ts.traces['v(/output)'][skip:]

    vin_pp = max(vin) - min(vin)
    vc_pp = max(vc) - min(vc)
    assert vin_pp > 0.005, f'Input swing too low: {vin_pp}'
    gain = vc_pp / vin_pp
    assert gain >= 30.0, f'Gain {gain:.1f}× ниже порога 30× (common-emitter)'
