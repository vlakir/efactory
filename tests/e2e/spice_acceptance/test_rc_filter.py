"""T008 Phase 5 acceptance: RC-фильтр через полный pipeline.

Покрывает T008 §4 Success criteria для RC-фильтра (OP / TRAN / AC).
SE-amp и rectifier фикстуры — отложены в T100 (после интеграции
`kicad-sch-api`, чтобы не делать руками s-expr для tube symbols).
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
from adapters.outbound.subprocess_apps.app_manager import (
    SubprocessAppManager,
)
from domain.simulation import AcAnalysis, OpAnalysis, TranAnalysis

_RC_FIXTURE = (
    Path(__file__).resolve().parents[2] / 'fixtures' / 'rc_filter.kicad_sch'
)

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
    reason='ngspice not installed (apt install ngspice / brew install ngspice)',
)


def _app_manager() -> SubprocessAppManager:
    return SubprocessAppManager(NativePlatformLayer())


async def _export_rc_netlist(tmp_path: Path) -> Path:
    exporter = KicadCliSchematicExporter(_app_manager())
    netlist_out = tmp_path / 'rc_filter.cir'
    return await exporter.export_spice_netlist(_RC_FIXTURE, netlist_out)


@needs_kicad
@needs_ngspice
async def test_rc_filter_op_yields_unit_voltage_on_input_and_output(
    tmp_path: Path,
) -> None:
    """OP: DC 1V → V(in)=V(out)=1V (ток через ёмкость в DC = 0)."""
    netlist = await _export_rc_netlist(tmp_path)
    simulator = NgspiceSimulator(_app_manager())

    result = await simulator.run(netlist, OpAnalysis())

    assert result.operating_points is not None
    op = result.operating_points
    # KiCad SPICE pin-order quirk инвертирует знак — проверяем magnitude.
    assert abs(op['v(/in)']) == pytest.approx(1.0, abs=1e-6)
    assert abs(op['v(/out)']) == pytest.approx(1.0, abs=1e-6)


@needs_kicad
@needs_ngspice
async def test_rc_filter_tran_holds_dc_steady_across_time(
    tmp_path: Path,
) -> None:
    """TRAN: DC source → V(in)/V(out) держатся постоянными во времени."""
    netlist = await _export_rc_netlist(tmp_path)
    simulator = NgspiceSimulator(_app_manager())

    result = await simulator.run(
        netlist,
        TranAnalysis(t_step=1e-4, t_stop=1e-3),
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
async def test_rc_filter_ac_yields_minus_three_db_at_cutoff(
    tmp_path: Path,
) -> None:
    """AC: на fc = 1 / (2π·R·C) ≈ 159 Hz → |H(fc)| ≈ 1/√2 ≈ 0.707."""
    netlist = await _export_rc_netlist(tmp_path)
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
    # Теоретически |H(fc)| = 1/√2 ≈ 0.7071. Допуск ±5%.
    assert magnitude == pytest.approx(0.7071, rel=0.05)


@needs_kicad
@needs_ngspice
async def test_rc_filter_ac_yields_unity_gain_far_below_cutoff(
    tmp_path: Path,
) -> None:
    """AC: на f << fc → |H(f)| ≈ 1 (passband)."""
    netlist = await _export_rc_netlist(tmp_path)
    simulator = NgspiceSimulator(_app_manager())

    result = await simulator.run(
        netlist,
        AcAnalysis(sweep='dec', n_points=10, f_start=1.0, f_stop=1e5),
    )

    assert result.ac_sweep is not None
    ac = result.ac_sweep
    # На f=1Hz (<< 159Hz) magnitude должна быть ~1.
    re = ac.traces_real['v(/out)'][0]
    im = ac.traces_imag['v(/out)'][0]
    magnitude = math.hypot(re, im)
    assert magnitude == pytest.approx(1.0, abs=0.01)
