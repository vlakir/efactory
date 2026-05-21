"""Integration test для analyze_distortion_spectrum через реальный ngspice (T131 Phase C).

Синтетическая «минимальная схема»: voltage source → saturable transformer →
load. Без лампы — линейный path, но saturable subckt всё равно
демонстрирует saturation distortion при высоком V_in.

Цель этого test'а — **end-to-end smoke**: spectrum well-formed, все cells
заполнены, THD значения physically plausible (не negative, не NaN).
Точные acceptance gate'ы для tube-amp pilot — в Phase D.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from adapters.outbound.ngspice.netlist_substitution import (
    NgspiceNetlistEditor,
)
from adapters.outbound.ngspice.simulator import NgspiceSimulator
from adapters.outbound.platform_native.platform_layer import NativePlatformLayer
from adapters.outbound.spice_models.saturable_core import (
    XSpiceSaturableSubcktGenerator,
)
from adapters.outbound.subprocess_apps.app_manager import SubprocessAppManager
from application.analyze_distortion_spectrum import analyze_distortion_spectrum
from domain.material import FrohlichBHCurve
from domain.magnetic import (
    Core,
    IsolationSide,
    MagneticComponent,
    OperatingPoint,
    Winding,
)
from domain.thd import ThdSweepSpec

_NGSPICE_AVAILABLE = shutil.which('ngspice') is not None
needs_ngspice = pytest.mark.skipif(
    not _NGSPICE_AVAILABLE,
    reason='ngspice not installed',
)


def _make_component() -> MagneticComponent:
    return MagneticComponent(
        name='OPT_synth',
        core=Core(
            shape_name='E42/15',
            material_name='Nanoperm 8000',
            gap_length_m=0.3e-3,
        ),
        windings=(
            Winding(name='pri', number_turns=1000, isolation_side=IsolationSide.PRIMARY),
            Winding(name='sec', number_turns=40, isolation_side=IsolationSide.SECONDARY),
        ),
        operating_point=OperatingPoint(
            frequency_hz=1000.0,
            primary_peak_voltage_v=100.0,
        ),
    )


def _write_synth_netlist(path: Path) -> None:
    """Минимальная схема: V_in → X_OPT → R_load."""
    path.write_text(
        '* T131 Phase C synthetic test amp\n'
        'V_in /in 0 SIN(0 0 1000)\n'
        'X_OPT /in 0 /load 0 OPT_SE_5K_8\n'
        '.include OPT_SE_5K_8.lib\n'
        'R_load /load 0 8\n'
        '.end\n',
    )


@needs_ngspice
async def test_analyze_distortion_spectrum_smoke_on_synth_amp(
    tmp_path: Path,
) -> None:
    base = tmp_path / 'synth.cir'
    _write_synth_netlist(base)
    workdir = tmp_path / 'work'

    # voltage_per_root_power=100 (V_in peak per √W load): для P=0.25 W →
    # V_in = 50 V; для P=1 W → V_in = 100 V. С turns ratio 25:1 это даёт
    # ~2-4 V на 8Ω нагрузке (~0.25-1 W measured, ±50% от target из-за
    # отсутствия учёта реальной коммутации, но это smoke test).
    spec = ThdSweepSpec(
        component=_make_component(),
        bh_curve=FrohlichBHCurve.from_pyom_material(mu_initial=8000.0, b_sat=1.2),
        a_core_m2=2.5e-4,
        l_path_m=0.1,
        r_primary_ohm=200.0,
        r_secondary_ohm=0.3,
        target_subckt_name='OPT_SE_5K_8',
        input_source_ref='V_in',
        voltage_per_root_power=100.0,
        frequencies_hz=(1000.0,),
        output_powers_w=(0.25, 1.0),
        signal_node='v(/load)',
        n_harmonics=10,
        periods_per_run=10,
        samples_per_period=100,
    )

    app_manager = SubprocessAppManager(NativePlatformLayer())
    simulator = NgspiceSimulator(app_manager)

    spectrum = await analyze_distortion_spectrum(
        base_netlist=base,
        spec=spec,
        simulator=simulator,
        subckt_generator=XSpiceSaturableSubcktGenerator(),
        netlist_editor=NgspiceNetlistEditor(),
        workdir=workdir,
        timeout_per_cell_seconds=30.0,
    )

    # 1 freq × 2 powers = 2 cells
    assert len(spectrum.points) == 2
    assert spectrum.component_name == 'OPT_synth'
    # Все cells заполнены: thd_percent ≥ 0, harmonics не пусты,
    # dominant_n ∈ [2, 9] (для n_harmonics=10).
    for point in spectrum.points:
        assert point.thd_percent >= 0.0
        assert len(point.harmonics) == 10
        assert 2 <= point.dominant_harmonic_n <= 9
        assert point.measured_power_w > 0.0
        # fundamental harmonic n=1 присутствует
        assert any(h.n == 1 for h in point.harmonics)
    # Runtime — 2 SPICE прогона на 1 kHz × 10 periods = ~10 ms transient
    # каждый, total wall-clock < 30 с с большим запасом.
    assert spectrum.runtime_seconds < 30.0
    # Каждая cell — отдельный netlist (ngspice ещё кладёт рядом
    # .wrapper.cir и .raw, поэтому фильтруем по точному pattern).
    cell_files = [
        p for p in workdir.glob('cell_*.cir')
        if not p.name.endswith('.wrapper.cir')
    ]
    assert len(cell_files) == 2
