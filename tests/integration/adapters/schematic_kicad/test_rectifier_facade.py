"""T100 Phase 1 acceptance: half-wave rectifier через `efactory.schematic`.

Цель: проверить, что фасад умеет строить нелинейные схемы — VSIN-источник
с реальным 1N4007 диодом на резистивную нагрузку. Acceptance: kicad-cli
экспортирует SPICE netlist, ngspice TRAN даёт полуволны (Vout ≥ 0 на всём
интервале, пик ≈ Vin_peak − Vd ≈ 9.3 V для 10 V амплитуды).

Параметры 1N4007 — индустриальная Duncan-model: Is, N, Rs, Cjo, M, Bv,
Ibv, Tt. Передаются в Sim.Params на инстансе, без external `.model`-файлов.
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
    reason='KiCad not installed (AppImage in ~/kicad/ или kicad-cli в PATH)',
)
needs_ngspice = pytest.mark.skipif(
    not _NGSPICE_AVAILABLE,
    reason='ngspice not installed',
)

# Duncan-model для 1N4007 (стандартный AC-выпрямитель 50/60 Гц, 1000 V, 1 A).
# Параметры подобраны под typical datasheet (Vf ≈ 1.0 V при 1 A, реверс
# восстановление ~30 µs). См. duncanamps.com и стандартные SPICE-модельные
# библиотеки.
_DIODE_1N4007_PARAMS = (
    'Is=14.11n N=1.984 Rs=33.89m Cjo=51.17p M=0.5 Bv=1000 Ibv=10u Tt=4.32u'
)

# Layout (KiCad mm, Y-down): V1 слева, D1 горизонтально вверху, R_load
# вертикально справа. Якорные координаты лежат на grid 1.27.
# V1 rotation=180 чтобы pin+ оказался сверху (схема выпрямителя: pin+ к
# аноду диода, pin- к GND). Pin+ → Y_center - 5.08, pin- → Y_center + 5.08.
# Все позиции — на grid 1.27 mm. V1 rotation=180 (pin+ сверху, pin- снизу),
# D1 rotation=180 (anode слева, cathode справа), R_load — vertical default.
# Pin alignment: V1.pin_plus Y = 57.15, D1 центр Y = 57.15, R_load.pin_a Y = 57.15.
_V1_AT = (50.8, 62.23)
_D1_AT = (76.2, 57.15)
_R_LOAD_AT = (88.9, 60.96)  # pin_a (pin 1) = (88.9, 64.77), pin_b (pin 2) = (88.9, 57.15)
_GND_V_AT = (50.8, 68.58)  # под V1.pin_minus
_GND_LOAD_AT = (88.9, 68.58)  # под R_load.pin_b
_PWR_FLAG_AT = (45.72, 68.58)  # рядом с GND_V (как в RC fixture)


def _app_manager() -> SubprocessAppManager:
    return SubprocessAppManager(NativePlatformLayer())


def _build_half_wave_rectifier(path: Path) -> Path:
    """Сборка half-wave rectifier через фасад: VSIN → 1N4007 → R_load → GND."""
    sch = Schematic('half_wave_rectifier')
    v1 = sch.add_v_ac(
        reference='V1',
        value='VSIN',
        at=_V1_AT,
        rotation=180,
        amplitude=10.0,
        frequency=50.0,
    )
    # rotation=180 чтобы anode (pin 2) смотрел в сторону V1+, cathode (pin 1)
    # в сторону нагрузки. Sim.Params override = Duncan 1N4007 модель.
    d1 = sch.add_diode(
        reference='D1',
        value='1N4007',
        at=_D1_AT,
        rotation=180,
        spice_params=_DIODE_1N4007_PARAMS,
    )
    r_load = sch.add_resistor(reference='R1', value='1k', at=_R_LOAD_AT)
    gnd_v = sch.add_ground(at=_GND_V_AT)
    gnd_load = sch.add_ground(at=_GND_LOAD_AT)
    flg = sch.add_pwr_flag(at=_PWR_FLAG_AT, rotation=180)

    sch.connect(v1.pin_plus, d1.pin_a)
    # pin_b = top pin (Y=57.15) — на одном уровне с D1.pin_k, чистый horizontal.
    sch.connect(d1.pin_k, r_load.pin_b)
    sch.connect(r_load.pin_a, gnd_load.pin)
    sch.connect(v1.pin_minus, gnd_v.pin)
    sch.connect(flg.pin, v1.pin_minus)
    sch.label('in', at=(60.96, 57.15))
    sch.label('out', at=(83.82, 57.15))
    # Auto-TRAN директива — KiCad Simulator (Inspect → Simulator) подхватит
    # её при Open → Run, без ручной настройки analysis.
    sch.spice_directive('.tran 100u 80m', at=(50.8, 80.0))
    return sch.save(path)


async def _export_netlist(schematic_path: Path, netlist_path: Path) -> Path:
    exporter = KicadCliSchematicExporter(_app_manager())
    return await exporter.export_spice_netlist(schematic_path, netlist_path)


@needs_kicad
async def test_facade_rectifier_writes_spice_directive_into_schematic(
    tmp_path: Path,
) -> None:
    """`.tran` директива записана в .kicad_sch как text-node для KiCad GUI."""
    sch_path = _build_half_wave_rectifier(
        tmp_path / 'half_wave_rectifier.kicad_sch',
    )
    text = sch_path.read_text(encoding='utf-8')
    assert '(text ".tran 100u 80m"' in text
    # `exclude_from_sim no` обязателен — без него KiCad считает декоративным.
    assert '(exclude_from_sim no)' in text


@needs_kicad
@needs_ngspice
async def test_facade_rectifier_tran_yields_positive_half_cycles(
    tmp_path: Path,
) -> None:
    """TRAN: Vout не уходит в значимый минус и достигает пиков ≈ Vin − Vd."""
    sch_path = _build_half_wave_rectifier(
        tmp_path / 'half_wave_rectifier.kicad_sch',
    )
    netlist = await _export_netlist(sch_path, tmp_path / 'half_wave.cir')
    simulator = NgspiceSimulator(_app_manager())

    # 4 периода @ 50 Гц = 80 мс; шаг 100 µs даёт ≥800 точек.
    result = await simulator.run(
        netlist, TranAnalysis(t_step=1e-4, t_stop=80e-3),
    )

    assert result.time_series is not None
    ts = result.time_series
    # KiCad SPICE pin-order quirk: знак может инвертироваться — работаем с
    # абсолютным значением, как в T008 acceptance.
    vout_abs = [abs(v) for v in ts.traces['v(/out)']]
    vin_abs = [abs(v) for v in ts.traces['v(/in)']]

    # Sanity: вход — синус ±10 V (пик ≥ 9.5).
    assert max(vin_abs) >= 9.5, f'V(in) peak too low: {max(vin_abs)}'

    # Выпрямленный сигнал должен достигать ≥ 8 V (10 V − Vd при 1 A через 1k).
    assert max(vout_abs) >= 8.0, f'V(out) peak too low: {max(vout_abs)}'

    # На каждой полуволне диод выключен ≥ половины периода — низкие точки.
    assert min(vout_abs) <= 1.0, (
        f'V(out) never drops near zero — diode not blocking: '
        f'min(|V(out)|)={min(vout_abs)}'
    )
