"""T027 Phase B: mid-band gain calibration на tube-line-preamp fixture.

Single-point AC gain measurement @ 1 kHz через `measure_gain` (small AC
mode). Empirical reference: ≈64 V/V (≈36 dB), полученное на baked
fixture при `data/models/tubes/custom/6N2P.lib`. ±15% tolerance ловит
регрессии model updates / builder topology drift.

**Hand-calc reference (в README.md template):**
* Stage 1 (CC) gain ≈ μ·R_p/(R_p+r_a) = 100·100k/(100k+80k) ≈ 55 V/V
  (analytical при datasheet μ=100, r_a=80kΩ).
* Stage 2 (CF) gain ≈ +(μ+1)·R_k2 / ((μ+1)·R_k2 + R_p + r_a) ≈ 0.98
  (CF approaches unity при large R_k2).
* Total analytical ≈ 55 × 0.98 ≈ 54 V/V (≈ 34.6 dB).

**Ngspice empirical baseline (после T029 R4 grid-leak fix):**
В T029 Phase 0 был починен R4 grid-leak (pin_b теперь соединён с
grid2 net через wire (114.3, 88.9), а не с собственной координатой
0-length wire'ом). До фикса /grid2 net в DC analysis инициализировался
SPICE'ом непредсказуемо (R4 floating), gain получался ≈64 V/V на
ill-defined operating point. После фикса V_grid2 = 0V (DC) через
R4=470k к GND, R4 ещё и шунтирует C3→V1B coupling на input
impedance ~470k → empirical gain снижается до ≈54 V/V, что
совпадает с analytical hand-calc Stage_1 (55) × CF (0.98) = 54 V/V.

**Spec Q5 (Round 2 одобрено Vladimir 2026-06-02):** target ≈ 30-40 V/V
(~30 dB), ±15% к hand-calc. Spec Q5 имеет внутреннюю math-slip
несоответствие (30 dB = 31.6 V/V vs formula 55 V/V = 34.6 dB).
Empirical 54 V/V ≈ analytical 54 V/V — точный match, разумная
calibration baseline. Tolerance ±15% → range [45.9, 62.1] V/V
(≈ 33.2 – 35.9 dB).
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
from tests.integration.adapters.schematic_kicad.test_tube_line_preamp_facade import (
    _build_tube_line_preamp,
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

_AV_MID_TARGET = 54.0
_AV_MID_TOL = 0.15


def _make_simulator() -> NgspiceSimulator:
    return NgspiceSimulator(SubprocessAppManager(NativePlatformLayer()))


@needs_kicad
@needs_ngspice
async def test_measure_gain_calibration_tube_line_preamp_mid_band(
    tmp_path: Path,
) -> None:
    """Av @ 1 kHz через `measure_gain` small AC mode, ±15% to empirical baseline."""
    sch_path = _build_tube_line_preamp(tmp_path / 'tube_line_preamp.kicad_sch')

    mgr = SubprocessAppManager(NativePlatformLayer())
    exporter = KicadCliSchematicExporter(mgr)
    cir = await exporter.export_spice_netlist(
        sch_path, tmp_path / 'tube_line_preamp.cir',
    )

    result = await measure_gain(
        netlist=cir,
        frequency_hz=1000.0,
        mode='small',
        simulator=_make_simulator(),
        netlist_editor=NgspiceNetlistEditor(),
        output_signal='v(/output)',
        input_source='V2',
    )

    lo = _AV_MID_TARGET * (1.0 - _AV_MID_TOL)
    hi = _AV_MID_TARGET * (1.0 + _AV_MID_TOL)
    assert lo <= result.value_linear <= hi, (
        f'Av_mid @ 1 kHz = {result.value_linear:.3f} V/V '
        f'({result.value_db:.2f} dB) out of empirical baseline '
        f'{_AV_MID_TARGET:.1f} ±{_AV_MID_TOL:.0%} = [{lo:.2f}, {hi:.2f}].'
    )
