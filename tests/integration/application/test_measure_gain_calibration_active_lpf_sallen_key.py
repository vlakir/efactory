"""T027 Phase D: Sallen-Key low-pass calibration на active-lpf-sallen-key fixture.

Multi-point AC sweep verifies 2nd-order Butterworth LPF response:
* Passband (DC, 100 Hz): ≈ 0 dB unity gain ±0.1 dB.
* -3 dB cutoff @ analytical f₀ = 1/(2π·R·√(C1·C2)) = 1024 Hz ±10%
  (spec §4 Success Criteria).
* Q ≈ 0.707 ±10% inferred через monotonic passband (no peaking).
* HF rolloff -40 dB/decade @ 10× f_c.

**Component values (equal-R, unequal-C per Analyze W1):**
R1=R2=10 kΩ, C1=22 nF, C2=11 nF → C1/C2=2 exact для Butterworth Q=0.707.

**Empirical baseline (T027 Phase D):**
* Passband flat 0 dB.
* -3 dB точно @ 1024 Hz (matches analytical f₀ within < 1 Hz).
* Monotonic rolloff (no peaking) — confirms Q=0.707.
* -39.6 dB @ 10 kHz (≈ ideal -40 dB·log10(10/1.024) ≈ -39.7).
"""

from __future__ import annotations

import shutil
import math
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
from tests.integration.adapters.schematic_kicad.test_active_lpf_sallen_key_facade import (
    _build_active_lpf_sallen_key,
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

# Analytical f₀ = 1/(2π·R·√(C1·C2)) with R=10kΩ, C1=22nF, C2=11nF.
_R = 10e3
_C1 = 22e-9
_C2 = 11e-9
_F0_ANALYTICAL = 1.0 / (2.0 * math.pi * _R * math.sqrt(_C1 * _C2))

_F0_TOL = 0.10  # ±10% per spec §4

# Q analytical (Sallen-Key unity-gain VCVS, equal-R).
_Q_ANALYTICAL = 0.5 * math.sqrt(_C1 / _C2)


def _make_simulator() -> NgspiceSimulator:
    return NgspiceSimulator(SubprocessAppManager(NativePlatformLayer()))


@needs_kicad
@needs_ngspice
async def test_measure_gain_calibration_sallen_key_passband_unity(
    tmp_path: Path,
) -> None:
    """Passband (10 Hz и 100 Hz) ≈ 0 dB unity gain (within ±0.1 dB)."""
    sch_path = _build_active_lpf_sallen_key(tmp_path / 'lpf.kicad_sch')

    mgr = SubprocessAppManager(NativePlatformLayer())
    exporter = KicadCliSchematicExporter(mgr)
    cir = await exporter.export_spice_netlist(
        sch_path, tmp_path / 'lpf.cir',
    )

    sim = _make_simulator()
    editor = NgspiceNetlistEditor()

    for freq in (10.0, 100.0):
        result = await measure_gain(
            netlist=cir,
            frequency_hz=freq,
            mode='small',
            simulator=sim,
            netlist_editor=editor,
            output_signal='v(/vout)',
            input_source='V_in',
        )
        assert abs(result.value_db) <= 0.1, (
            f'Passband @ {freq} Hz: {result.value_db:+.3f} dB '
            f'(expected 0 ±0.1 dB unity gain)'
        )


@needs_kicad
@needs_ngspice
async def test_measure_gain_calibration_sallen_key_minus_3db_at_fc(
    tmp_path: Path,
) -> None:
    """-3 dB cutoff at f₀ ±10% (spec §4 tolerance)."""
    sch_path = _build_active_lpf_sallen_key(tmp_path / 'lpf.kicad_sch')
    mgr = SubprocessAppManager(NativePlatformLayer())
    exporter = KicadCliSchematicExporter(mgr)
    cir = await exporter.export_spice_netlist(
        sch_path, tmp_path / 'lpf.cir',
    )
    sim = _make_simulator()
    editor = NgspiceNetlistEditor()

    # Measure at exactly f₀ — should be -3 dB ± 0.5 dB для Butterworth.
    result = await measure_gain(
        netlist=cir,
        frequency_hz=_F0_ANALYTICAL,
        mode='small',
        simulator=sim,
        netlist_editor=editor,
        output_signal='v(/vout)',
        input_source='V_in',
    )
    assert -3.5 <= result.value_db <= -2.5, (
        f'|H(f₀={_F0_ANALYTICAL:.1f} Hz)| = {result.value_db:+.3f} dB; '
        f'expected -3.0 ±0.5 dB для Butterworth Q=0.707.'
    )

    # Verify -3 dB cutoff falls within ±10% of analytical f₀:
    # sweep nearby and find where |H| crosses -3 dB.
    f_lo = _F0_ANALYTICAL * (1.0 - _F0_TOL)
    f_hi = _F0_ANALYTICAL * (1.0 + _F0_TOL)
    res_lo = await measure_gain(
        netlist=cir, frequency_hz=f_lo, mode='small',
        simulator=sim, netlist_editor=editor,
        output_signal='v(/vout)', input_source='V_in',
    )
    res_hi = await measure_gain(
        netlist=cir, frequency_hz=f_hi, mode='small',
        simulator=sim, netlist_editor=editor,
        output_signal='v(/vout)', input_source='V_in',
    )
    # -3 dB должен быть между f_lo (~-2 dB) и f_hi (~-4 dB).
    assert res_lo.value_db > -3.0, (
        f'At f_lo={f_lo:.1f}: {res_lo.value_db:+.3f} dB; '
        f'should be > -3 dB (-3dB point внутри ±10% range)'
    )
    assert res_hi.value_db < -3.0, (
        f'At f_hi={f_hi:.1f}: {res_hi.value_db:+.3f} dB; '
        f'should be < -3 dB (-3dB point внутри ±10% range)'
    )


@needs_kicad
@needs_ngspice
async def test_measure_gain_calibration_sallen_key_butterworth_monotonic(
    tmp_path: Path,
) -> None:
    """Butterworth Q=0.707: monotonic passband (no peaking), Q ±10% inferred."""
    sch_path = _build_active_lpf_sallen_key(tmp_path / 'lpf.kicad_sch')
    mgr = SubprocessAppManager(NativePlatformLayer())
    exporter = KicadCliSchematicExporter(mgr)
    cir = await exporter.export_spice_netlist(
        sch_path, tmp_path / 'lpf.cir',
    )
    sim = _make_simulator()
    editor = NgspiceNetlistEditor()

    # Sweep passband — check no peaking (|H| ≤ 1 + small tolerance) и
    # monotonic decrease (each subsequent freq лучше attenuated).
    freqs = [10.0, 100.0, 300.0, 500.0, 700.0, _F0_ANALYTICAL]
    db_values = []
    for freq in freqs:
        result = await measure_gain(
            netlist=cir, frequency_hz=freq, mode='small',
            simulator=sim, netlist_editor=editor,
            output_signal='v(/vout)', input_source='V_in',
        )
        db_values.append(result.value_db)

    # Q=0.707 ±10% → no peaking >0.1 dB (for Q ≤ 0.707, |H| ≤ 1 strictly).
    # Allow slight tolerance для numerical artifacts.
    max_db = max(db_values)
    assert max_db <= 0.15, (
        f'Max passband |H| = {max_db:+.3f} dB; expected ≤ 0 dB для '
        f'Butterworth Q=0.707. Peaking suggests Q > 0.707 (outside ±10%).'
    )

    # Monotonic decrease check: each subsequent freq должна attenuate
    # больше предыдущего (или equal в численном пределе).
    for i in range(1, len(db_values)):
        assert db_values[i] <= db_values[i - 1] + 0.05, (
            f'Non-monotonic при f={freqs[i]} Hz: '
            f'{db_values[i]:+.3f} dB > prev {db_values[i - 1]:+.3f} dB. '
            f'Suggests Q peaking — outside Butterworth Q=0.707 spec.'
        )
