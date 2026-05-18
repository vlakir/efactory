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

# Layout (mm, Y-down). Соединения — через KiCad net labels (KiCad склеивает
# net'ы с одинаковым label name), а не через wires — это устраняет риск
# Manhattan-collision'ов между wire-сегментами разных net'ов.
#
# V_DC/V_AC polarity workaround: фасадный pin_plus возвращает symbol pin
# '1', а в реальной KiCad-schematic с Y-flip pin '1' оказывается на pin
# '-' терминале. Чтобы получить положительный Vcc, label "Vcc" вешаем
# на pin_minus (= real '+'), GND — на pin_plus (= real '-'). См.
# комментарий про Y-flip в facade.py.
_V_VCC_AT = (50.0, 70.0)          # rotation=0: pin_plus at (50,75.08), pin_minus (50,64.92)
_V_IN_AT = (50.0, 95.0)
_C_IN_AT = (70.0, 95.0)           # horizontal coupling cap (rotation=90)
_R_B1_AT = (90.0, 80.0)
_R_B2_AT = (90.0, 110.0)
_Q1_AT = (110.0, 95.0)            # Q_NPN: B=(104.92,95), C=(112.54,89.92), E=(112.54,100.08)
_R_C_AT = (140.0, 80.0)
_R_E_AT = (140.0, 110.0)
_C_E_AT = (155.0, 110.0)
_GND_V_AT = (50.0, 80.0)          # под V1.pin_plus (= real '-')
_GND_VIN_AT = (50.0, 105.0)
_GND_B2_AT = (90.0, 120.0)
_GND_E_AT = (140.0, 120.0)
_GND_CE_AT = (155.0, 120.0)
_FLG_AT = (45.0, 105.0)


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
    c_in = sch.add_capacitor(
        reference='C1', value='1u', at=_C_IN_AT, rotation=90,
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
    c_e = sch.add_capacitor(
        reference='C2', value='100u', at=_C_E_AT,
    )
    gnd_v = sch.add_ground(at=_GND_V_AT)
    gnd_vin = sch.add_ground(at=_GND_VIN_AT)
    gnd_b = sch.add_ground(at=_GND_B2_AT)
    gnd_e = sch.add_ground(at=_GND_E_AT)
    gnd_ce = sch.add_ground(at=_GND_CE_AT)
    flg = sch.add_pwr_flag(at=_FLG_AT, rotation=180)

    # === Short wires to GND-symbols (single-segment vertical) ===
    # V1.pin_plus = real '-' → GND (workaround Y-flip polarity, см. above)
    sch.connect(v_cc.pin_plus, gnd_v.pin)
    sch.connect(v_in.pin_plus, gnd_vin.pin)
    sch.connect(r_b2.pin_a, gnd_b.pin)
    sch.connect(r_e.pin_a, gnd_e.pin)
    sch.connect(c_e.pin_a, gnd_ce.pin)
    sch.connect(flg.pin, v_in.pin_plus)

    # === Net labels (KiCad склеивает net'ы по имени) ===
    # Vcc rail — pin_minus = real '+' → Vcc supply
    sch.label('Vcc', at=v_cc.pin_minus)
    sch.label('Vcc', at=r_b1.pin_b)
    sch.label('Vcc', at=r_c.pin_b)
    # Vinput — pin_minus = real '+' (AC, направление не критично, но keep консистенция)
    sch.label('Vinput', at=v_in.pin_minus)
    sch.label('Vinput', at=c_in.pin_a)
    # Vbase (C_in.right → Q1.B + R_B1.bottom + R_B2.top)
    sch.label('Vbase', at=c_in.pin_b)
    sch.label('Vbase', at=q1.pin_b)
    sch.label('Vbase', at=r_b1.pin_a)
    sch.label('Vbase', at=r_b2.pin_b)
    # Vcollector (Q1.C → R_C.bottom)
    sch.label('Vcollector', at=q1.pin_c)
    sch.label('Vcollector', at=r_c.pin_a)
    # Vemitter (Q1.E → R_E.top → C_E.top)
    sch.label('Vemitter', at=q1.pin_e)
    sch.label('Vemitter', at=r_e.pin_b)
    sch.label('Vemitter', at=c_e.pin_b)

    # .model card + .tran директива
    sch.spice_directive(_BJT_2N3904_MODEL, at=(40, 130))
    sch.spice_directive('.tran 10u 5m', at=(40, 138))

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
    vin = ts.traces['v(/vinput)'][skip:]
    vc = ts.traces['v(/vcollector)'][skip:]

    vin_pp = max(vin) - min(vin)
    vc_pp = max(vc) - min(vc)
    assert vin_pp > 0.005, f'Input swing too low: {vin_pp}'
    gain = vc_pp / vin_pp
    assert gain >= 30.0, f'Gain {gain:.1f}× ниже порога 30× (common-emitter)'
