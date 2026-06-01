"""T027 Phase A: mid-band gain calibration на tube-pp-amp fixture.

Single-point AC gain measurement @ 1 kHz через `measure_gain` (small AC
mode). Empirical reference: ≈16.5 V/V (≈24.4 dB), полученное на baked
fixture при `data/models/tubes/custom/6N2P.lib` + `6P14P.lib` +
`OPT_PP_6K6_8.lib` нагрузка 8 Ω. ±15% tolerance ловит регрессии model
updates / builder topology drift.

**Hand-calc reference (в README.md template):**
* LTP per-output gain ≈ μR_p/(R_p+r_a) ≈ 100·47/127 ≈ 37 V/V (ideal).
  Реально ~12 V/V — model parameter drift + downstream loading через
  C_couple_a + R_g2 (470k grid leak).
* Per-tube 6П14П pentode gain ≈ g_m·Z_a_per ≈ 11mA/V · 1.65k ≈ 18 V/V.
  Реально ~28 V/V (g_m effective выше при V_a≈300V, I_a≈30mA).
* OPT step-down: V_sec/V_diff_prim = 1/N, N=√(R_aa/R_load)=√(6600/8)=28.7
  → 1/28.7 = 0.035.
* Total system: 12 · 28 · 0.035 ≈ 12 V/V (нижняя граница), or через
  ngspice measured ≈ 16.5 V/V.

Tolerance ±15% → range [14, 19] V/V (≈22.9 – 25.6 dB).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from adapters.outbound.kicad_cli.schematic_exporter import (
    KicadCliSchematicExporter,
)
from adapters.outbound.ngspice.netlist_substitution import NgspiceNetlistEditor
from adapters.outbound.ngspice.simulator import NgspiceSimulator
from adapters.outbound.platform_native.platform_layer import (
    NativePlatformLayer,
)
from adapters.outbound.subprocess_apps.app_manager import SubprocessAppManager
from application.measure_gain import measure_gain
from tests.integration.adapters.schematic_kicad.test_tube_pp_amp_facade import (
    _build_tube_pp_amp,
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

# Empirical mid-band Av @ 1 kHz, computed на baked fixture (T027 Phase A).
# Если изменишь model parameters / R_p / R_tail / C_couple — re-baseline
# через interactive measure_gain run и обнови target+tolerance ниже.
_AV_MID_TARGET = 16.5
_AV_MID_TOL = 0.15  # ±15% per spec §4 Success Criteria


def _make_simulator() -> NgspiceSimulator:
    return NgspiceSimulator(SubprocessAppManager(NativePlatformLayer()))


@needs_kicad
@needs_ngspice
async def test_measure_gain_calibration_tube_pp_amp_mid_band(
    tmp_path: Path,
) -> None:
    """Av @ 1 kHz через `measure_gain` small AC mode, ±15% to empirical baseline."""
    sch_path = _build_tube_pp_amp(tmp_path / 'tube_pp_amp.kicad_sch')

    mgr = SubprocessAppManager(NativePlatformLayer())
    exporter = KicadCliSchematicExporter(mgr)
    cir = await exporter.export_spice_netlist(
        sch_path, tmp_path / 'tube_pp_amp.cir',
    )

    result = await measure_gain(
        netlist=cir,
        frequency_hz=1000.0,
        mode='small',
        simulator=_make_simulator(),
        netlist_editor=NgspiceNetlistEditor(),
        output_signal='v(/sec_a)',
        input_source='V2',
    )

    lo = _AV_MID_TARGET * (1.0 - _AV_MID_TOL)
    hi = _AV_MID_TARGET * (1.0 + _AV_MID_TOL)
    assert lo <= result.value_linear <= hi, (
        f'Av_mid @ 1 kHz = {result.value_linear:.3f} V/V '
        f'({result.value_db:.2f} dB) out of empirical baseline '
        f'{_AV_MID_TARGET:.1f} ±{_AV_MID_TOL:.0%} = [{lo:.2f}, {hi:.2f}].'
        f'Re-baseline via interactive measure_gain run if intentional change.'
    )
