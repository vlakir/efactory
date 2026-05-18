"""T100 Phase 0 acceptance: RC-фильтр через `efactory.schematic` фасад.

Reproducing fixture `tests/fixtures/rc_filter.kicad_sch` (T008 baseline)
through the new programmatic API. Acceptance — ngspice OP/TRAN/AC
матчатся с T008 (see `tests/e2e/spice_acceptance/test_rc_filter.py`):

  * OP: |V(/in)| = |V(/out)| = 1 V  (ёмкость в DC = разрыв).
  * TRAN: V(/in)/V(/out) держатся 1V на всём интервале.
  * AC: |H(fc)| ≈ 0.7071 на fc = 1 / (2π·R·C) ≈ 159 Hz.

Координаты компонентов взяты из существующей фикстуры — Phase 0 это
рефакторинг «hardcoded → API», не дизайн с нуля.
"""

from __future__ import annotations

import math
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
from domain.simulation import AcAnalysis, OpAnalysis, TranAnalysis

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


def _app_manager() -> SubprocessAppManager:
    return SubprocessAppManager(NativePlatformLayer())


def _build_rc_filter(path: Path) -> Path:
    """Собрать RC-фильтр через фасад и сохранить в `path`.

    Координаты те же, что в `tests/fixtures/rc_filter.kicad_sch`,
    чтобы упростить визуальное сличение и не зависеть от
    placement-эвристики Phase 0.
    """
    sch = Schematic('rc_filter')
    v1 = sch.add_v_dc(reference='V1', value='1', at=(50.8, 62.23), rotation=180)
    r1 = sch.add_resistor(
        reference='R1', value='1k', at=(88.9, 55.88), rotation=90,
    )
    c1 = sch.add_capacitor(
        reference='C1', value='1u', at=(114.3, 55.88), rotation=90,
    )
    gnd_v = sch.add_ground(at=(50.8, 68.58))
    gnd_c = sch.add_ground(at=(118.11, 68.58))
    sch.connect(v1.pin_plus, r1.pin_a)
    sch.connect(r1.pin_b, c1.pin_a)
    sch.connect(c1.pin_b, gnd_c.pin)
    sch.connect(v1.pin_minus, gnd_v.pin)
    # PWR_FLAG на уровне GND (rotation 180 — стрелка вниз) → удовлетворяет
    # ERC `power_pin_not_driven`. Layout согласован с user-perfected fixture.
    flg = sch.add_pwr_flag(at=(45.72, 68.58), rotation=180)
    sch.connect(flg.pin, v1.pin_minus)
    sch.label('in', at=(68.58, 55.88))
    sch.label('out', at=(101.6, 55.88))
    return sch.save(path)


async def _export_netlist(schematic_path: Path, netlist_path: Path) -> Path:
    exporter = KicadCliSchematicExporter(_app_manager())
    return await exporter.export_spice_netlist(schematic_path, netlist_path)


@needs_kicad
@needs_ngspice
async def test_facade_rc_op_yields_unit_voltage(tmp_path: Path) -> None:
    """OP через сгенерированный фасадом schematic → V(in)=V(out)=1V."""
    sch_path = _build_rc_filter(tmp_path / 'rc_filter.kicad_sch')
    netlist = await _export_netlist(sch_path, tmp_path / 'rc_filter.cir')
    simulator = NgspiceSimulator(_app_manager())

    result = await simulator.run(netlist, OpAnalysis())

    assert result.operating_points is not None
    op = result.operating_points
    # KiCad SPICE pin-order quirk инвертирует знак — magnitude (see T008).
    assert abs(op['v(/in)']) == pytest.approx(1.0, abs=1e-6)
    assert abs(op['v(/out)']) == pytest.approx(1.0, abs=1e-6)


@needs_kicad
@needs_ngspice
async def test_facade_rc_tran_holds_dc_steady(tmp_path: Path) -> None:
    """TRAN через фасад: DC источник → V(in)/V(out) постоянны."""
    sch_path = _build_rc_filter(tmp_path / 'rc_filter.kicad_sch')
    netlist = await _export_netlist(sch_path, tmp_path / 'rc_filter.cir')
    simulator = NgspiceSimulator(_app_manager())

    result = await simulator.run(
        netlist, TranAnalysis(t_step=1e-4, t_stop=1e-3),
    )

    assert result.time_series is not None
    ts = result.time_series
    assert len(ts.time) > 3
    for v_in, v_out in zip(
        ts.traces['v(/in)'], ts.traces['v(/out)'], strict=True,
    ):
        assert abs(v_in) == pytest.approx(1.0, abs=1e-3)
        assert abs(v_out) == pytest.approx(1.0, abs=1e-3)


@needs_kicad
@needs_ngspice
async def test_facade_rc_ac_yields_minus_three_db_at_cutoff(
    tmp_path: Path,
) -> None:
    """AC через фасад: на fc = 1 / (2π·R·C) ≈ 159 Hz → |H| ≈ 1/√2."""
    sch_path = _build_rc_filter(tmp_path / 'rc_filter.kicad_sch')
    netlist = await _export_netlist(sch_path, tmp_path / 'rc_filter.cir')
    simulator = NgspiceSimulator(_app_manager())

    result = await simulator.run(
        netlist,
        AcAnalysis(sweep='dec', n_points=20, f_start=1.0, f_stop=1e5),
    )

    assert result.ac_sweep is not None
    ac = result.ac_sweep
    fc = 1.0 / (2 * math.pi * 1e3 * 1e-6)
    idx = min(range(len(ac.frequency)), key=lambda i: abs(ac.frequency[i] - fc))
    re = ac.traces_real['v(/out)'][idx]
    im = ac.traces_imag['v(/out)'][idx]
    magnitude = math.hypot(re, im)
    assert magnitude == pytest.approx(0.7071, rel=0.05)


@needs_kicad
@needs_ngspice
async def test_facade_rc_ac_unity_gain_far_below_cutoff(tmp_path: Path) -> None:
    """AC через фасад: на f=1Hz (<< fc=159Hz) → |H| ≈ 1 (passband)."""
    sch_path = _build_rc_filter(tmp_path / 'rc_filter.kicad_sch')
    netlist = await _export_netlist(sch_path, tmp_path / 'rc_filter.cir')
    simulator = NgspiceSimulator(_app_manager())

    result = await simulator.run(
        netlist,
        AcAnalysis(sweep='dec', n_points=10, f_start=1.0, f_stop=1e5),
    )

    assert result.ac_sweep is not None
    ac = result.ac_sweep
    re = ac.traces_real['v(/out)'][0]
    im = ac.traces_imag['v(/out)'][0]
    magnitude = math.hypot(re, im)
    assert magnitude == pytest.approx(1.0, abs=0.01)
