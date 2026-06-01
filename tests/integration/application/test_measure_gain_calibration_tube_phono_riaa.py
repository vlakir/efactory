"""T027 Phase C: RIAA compliance calibration на tube-phono-riaa fixture.

Multi-point AC gain sweep @ 20 Hz / 50 Hz / 100 Hz / 200 Hz / 500 Hz /
1 kHz / 2 kHz / 5 kHz / 10 kHz / 20 kHz сравнивается с inverse RIAA
curve relative @ 1 kHz reference. Spec §4 Success Criteria: ±1 dB
compliance в audio band 20 Hz – 20 kHz.

**Inverse RIAA curve (canonical):** standard time constants
τ1=3180 µs, τ2=318 µs, τ3=75 µs дают inverse curve:
* +19.27 dB @ 20 Hz (relative to 1 kHz)
* +16.95 dB @ 50 Hz
* +13.09 dB @ 100 Hz
* +8.22 dB @ 200 Hz
* +2.65 dB @ 500 Hz
* 0.00 dB @ 1 kHz (reference)
* -2.59 dB @ 2 kHz
* -8.22 dB @ 5 kHz
* -13.74 dB @ 10 kHz
* -19.62 dB @ 20 kHz

**Empirical baseline (T027 Phase C, Lipshitz-corrected component values
R1=68k / R2=9.1k / C1=11n / C2=33n):** worst-case error 0.65 dB @ 50 Hz,
все остальные < 0.55 dB. Compliance achieved per spec.

**Calibration tolerance:** ±1 dB per spec (consumer-grade phono).
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
from tests.integration.adapters.schematic_kicad.test_tube_phono_riaa_facade import (
    _build_tube_phono_riaa,
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

# Inverse RIAA target curve, dB relative @ 1 kHz reference.
_RIAA_INVERSE_DB: dict[float, float] = {
    20.0: 19.27,
    50.0: 16.95,
    100.0: 13.09,
    200.0: 8.22,
    500.0: 2.65,
    1000.0: 0.0,
    2000.0: -2.59,
    5000.0: -8.22,
    10000.0: -13.74,
    20000.0: -19.62,
}

_RIAA_TOL_DB = 1.0  # ±1 dB per spec §4 Success Criteria


def _make_simulator() -> NgspiceSimulator:
    return NgspiceSimulator(SubprocessAppManager(NativePlatformLayer()))


@needs_kicad
@needs_ngspice
async def test_measure_gain_calibration_tube_phono_riaa_compliance(
    tmp_path: Path,
) -> None:
    """AC sweep 20 Hz – 20 kHz vs inverse RIAA: ±1 dB compliance в audio band."""
    sch_path = _build_tube_phono_riaa(tmp_path / 'tube_phono_riaa.kicad_sch')

    mgr = SubprocessAppManager(NativePlatformLayer())
    exporter = KicadCliSchematicExporter(mgr)
    cir = await exporter.export_spice_netlist(
        sch_path, tmp_path / 'tube_phono_riaa.cir',
    )

    sim = _make_simulator()
    editor = NgspiceNetlistEditor()

    # Reference @ 1 kHz first.
    ref = await measure_gain(
        netlist=cir,
        frequency_hz=1000.0,
        mode='small',
        simulator=sim,
        netlist_editor=editor,
        output_signal='v(/output)',
        input_source='V2',
    )
    ref_db = ref.value_db

    errors: list[tuple[float, float, float, float]] = []  # freq, rel_db, target, error
    for freq, target_rel_db in _RIAA_INVERSE_DB.items():
        result = await measure_gain(
            netlist=cir,
            frequency_hz=freq,
            mode='small',
            simulator=sim,
            netlist_editor=editor,
            output_signal='v(/output)',
            input_source='V2',
        )
        rel_db = result.value_db - ref_db
        error = rel_db - target_rel_db
        errors.append((freq, rel_db, target_rel_db, error))

    # Check all points within ±1 dB.
    violations = [
        (freq, rel_db, target_db, err)
        for (freq, rel_db, target_db, err) in errors
        if abs(err) > _RIAA_TOL_DB
    ]
    if violations:
        msg_lines = [
            f'RIAA compliance failed (±{_RIAA_TOL_DB:.1f} dB tolerance):',
        ]
        for freq, rel_db, target_db, err in violations:
            msg_lines.append(
                f'  {freq:>7.0f} Hz: measured {rel_db:+.2f} dB rel '
                f'(target {target_db:+.2f}, error {err:+.2f} dB)'
            )
        pytest.fail('\n'.join(msg_lines))
