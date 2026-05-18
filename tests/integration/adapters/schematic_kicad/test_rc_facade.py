"""T100 Phase 0 acceptance: RC-фильтр через `efactory.schematic` фасад.

Reproducing through the new programmatic API. Acceptance — ngspice
OP/TRAN/AC матчатся с baseline T008 (см.
`tests/e2e/spice_acceptance/test_rc_filter.py`):

  * OP: |V(/in)| = |V(/out)| = 1 V  (ёмкость в DC = разрыв).
  * TRAN: V(/in)/V(/out) держатся 1V на всём интервале.
  * AC: |H(fc)| ≈ 0.7071 на fc = 1 / (2π·R·C) ≈ 159 Hz.

С T100 Phase 3 фасад-builder вынесен в `tests/conftest.py` (фикстура
`rc_filter_schematic_path`); старая ручная фикстура
`tests/fixtures/rc_filter.kicad_sch` удалена.
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


async def _export_netlist(schematic_path: Path, netlist_path: Path) -> Path:
    exporter = KicadCliSchematicExporter(_app_manager())
    return await exporter.export_spice_netlist(schematic_path, netlist_path)


@needs_kicad
@needs_ngspice
async def test_facade_rc_op_yields_unit_voltage(
    rc_filter_schematic_path: Path,
    tmp_path: Path,
) -> None:
    """OP через сгенерированный фасадом schematic → V(in)=V(out)=1V."""
    netlist = await _export_netlist(
        rc_filter_schematic_path, tmp_path / 'rc_filter.cir',
    )
    simulator = NgspiceSimulator(_app_manager())

    result = await simulator.run(netlist, OpAnalysis())

    assert result.operating_points is not None
    op = result.operating_points
    # KiCad SPICE pin-order quirk инвертирует знак — magnitude (see T008).
    assert abs(op['v(/in)']) == pytest.approx(1.0, abs=1e-6)
    assert abs(op['v(/out)']) == pytest.approx(1.0, abs=1e-6)


@needs_kicad
@needs_ngspice
async def test_facade_rc_tran_holds_dc_steady(
    rc_filter_schematic_path: Path,
    tmp_path: Path,
) -> None:
    """TRAN через фасад: DC источник → V(in)/V(out) постоянны."""
    netlist = await _export_netlist(
        rc_filter_schematic_path, tmp_path / 'rc_filter.cir',
    )
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
    rc_filter_schematic_path: Path,
    tmp_path: Path,
) -> None:
    """AC через фасад: на fc = 1 / (2π·R·C) ≈ 159 Hz → |H| ≈ 1/√2."""
    netlist = await _export_netlist(
        rc_filter_schematic_path, tmp_path / 'rc_filter.cir',
    )
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
async def test_facade_rc_ac_unity_gain_far_below_cutoff(
    rc_filter_schematic_path: Path,
    tmp_path: Path,
) -> None:
    """AC через фасад: на f=1Hz (<< fc=159Hz) → |H| ≈ 1 (passband)."""
    netlist = await _export_netlist(
        rc_filter_schematic_path, tmp_path / 'rc_filter.cir',
    )
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
