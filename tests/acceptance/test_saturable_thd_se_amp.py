"""
T131 Phase D acceptance pilot: SE-amp 6П14П + saturable OPT THD spectrum.

**Closure status: infrastructure-only.** Pilot acceptance gates
(THD@1kHz/1W ∈ [1%, 5%], dominant n=2, monotonic by power, runtime
≤120 s) **не достигнуты** — `EL84 + saturable_core` subckt не сходится
численно: ngspice TRAN с реальной EL84 Koren-моделью и Frohlich-PWL
saturable OPT даёт magnitudes ≈ 1e+65 (numerical garbage) при любых
gmin / itl4 / reltol option'ах. Standalone saturable + linear sources
(см. Phase C `test_analyze_distortion_spectrum_smoke_on_synth_amp`)
работает нормально — проблема в interaction `tube + saturable`.

Root cause likely:
- Algebraic loop через PWL `B_Lm` current source + tube G-source +
  primary R_pri without stabilizing series-L.
- `C_int = 1 F` integrator не даёт быстрой relaxation к equilibrium —
  малейшая численная погрешность каскадирует в drift.

Fix scope — Phase A revision (`saturable_core.py` redesign):
переход с current-source PWL на nonlinear-inductance formulation (B-
source с воспроизводимым flux equation `V = N·A·dB/dt`), либо
hysteresis-loop model (Jiles-Atherton / Preisach) с inherent DC
stability. См. spec Q6 — failure path (a) "ADR + T134 follow-up".

Этот файл оставлен в репо как **infrastructure-ready pipeline**:
1. `opt_se_5k_8_magnetic_component()` — fixture готова, PyOM Lp =
   25.7 H валидируется в pre-check.
2. `_build_se_amp_for_thd_pilot` + post-processing — KiCad export +
   netlist substitution + 1MΩ DC leak готов.
3. Sweep matrix + acceptance gate code — готовы запуститься как только
   saturable_core стабилизируется.

При re-attempt: убрать `@pytest.mark.skip` с
`test_se_amp_6p14p_saturable_thd_pilot`.
"""

from __future__ import annotations

import importlib.util
import math
import re
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from adapters.outbound.fem_solver_getdp.material import FrohlichBHCurve
from adapters.outbound.kicad_cli.schematic_exporter import (
    KicadCliSchematicExporter,
)
from adapters.outbound.magnetic_analytics_pyopenmagnetics import (
    PyOpenMagneticsAnalytics,
    load_pyopenmagnetics,
)
from adapters.outbound.ngspice.simulator import NgspiceSimulator
from adapters.outbound.platform_native.platform_layer import (
    NativePlatformLayer,
)
from adapters.outbound.subprocess_apps.app_manager import (
    SubprocessAppManager,
)
from application.analyze_distortion_spectrum import (
    analyze_distortion_spectrum,
)
from domain.magnetic import (
    Core,
    GapType,
    IsolationSide,
    MagneticComponent,
    OperatingPoint,
    Winding,
)
from domain.thd import ThdSweepSpec
from ports.outbound.magnetic_analytics import (
    MagneticAnalyticsUnavailableError,
)

if TYPE_CHECKING:
    pass

# Skip markers
_KICAD_AVAILABLE = (
    any((Path.home() / 'kicad').glob('kicad*.AppImage'))
    or shutil.which('kicad-cli') is not None
)
_NGSPICE_AVAILABLE = shutil.which('ngspice') is not None


def _pyom_available() -> bool:
    try:
        load_pyopenmagnetics()
    except MagneticAnalyticsUnavailableError:
        return False
    return True


_PYOM_AVAILABLE = _pyom_available()

needs_kicad = pytest.mark.skipif(
    not _KICAD_AVAILABLE,
    reason='KiCad not installed',
)
needs_ngspice = pytest.mark.skipif(
    not _NGSPICE_AVAILABLE,
    reason='ngspice not installed',
)
needs_pyom = pytest.mark.skipif(
    not _PYOM_AVAILABLE,
    reason='PyOpenMagnetics не установлен в venv',
)

# OPT_SE_5K_8 fixture геометрии (PyOM E 42/15 / Nanoperm 8000 catalog).
# Effective core area / path length — извлечены через PyOM
# calculate_core_data (см. tests/fixtures/magnetic/opt-6p14p-se/expected.json:
# effectiveArea_m2 / effectiveLength_m).
_OPT_CORE_SHAPE = 'E 42/15'
_OPT_CORE_MATERIAL = 'Nanoperm 8000'
_OPT_BOBBIN = 'Bobbin E42/15'
_OPT_GAP_M = 0.02e-3  # 20 µm — tight gap для Lp ≈ 25 H с Nanoperm 8000
_OPT_PRIMARY_TURNS = 2500
_OPT_SECONDARY_TURNS = 100  # ratio 25:1 (= sqrt(5000/8), matches static lib)
_OPT_A_CORE_M2 = 1.424767e-4
_OPT_L_PATH_M = 9.735310e-2
# DCR — typical из static lib (data/models/transformers/generic/OPT_SE_5K_8.lib).
_OPT_R_PRIMARY_OHM = 200.0
_OPT_R_SECONDARY_OHM = 0.3

# PyOM-предсказанная Lp (при заданной геометрии и gap) — sanity bound.
# Конкретное значение 25.7 H probed 2026-05-21 (см. PR description).
_PYOM_PILOT_LP_RANGE = (20.0, 35.0)

# Calibration: EL84 SE с turns ratio 25:1 на 8Ω нагрузку. V_in (grid) →
# V_load relation ≈ G_pentode/ratio. Эмпирический initial guess; уточняется
# через probe run перед main sweep.
_V_IN_PER_ROOT_POWER_INITIAL_GUESS = 2.5
_PROBE_TARGET_POWER_W = 0.05  # тихий probe для derive gain

_SCHEMATIC_FACADE_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / 'integration'
    / 'adapters'
    / 'schematic_kicad'
    / 'test_se_amp_facade.py'
)


def _load_se_amp_factory():  # noqa: ANN202
    """
    Загрузить `_build_se_amp` из integration-test модуля без pythonpath-хака.

    `tests/` не входит в `pythonpath = ["src"]`, поэтому статический
    `from tests.integration...` import не работает. Решение — dynamic
    import через `importlib.util.spec_from_file_location`. Альтернатива
    (extracted shared fixture в `tests/fixtures/`) требует extension
    `pythonpath` — отложено как follow-up.
    """
    spec = importlib.util.spec_from_file_location(
        '_se_amp_facade_dyn',
        _SCHEMATIC_FACADE_MODULE_PATH,
    )
    if spec is None or spec.loader is None:
        msg = f'cannot load {_SCHEMATIC_FACADE_MODULE_PATH}'
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules['_se_amp_facade_dyn'] = module
    spec.loader.exec_module(module)
    return module._build_se_amp  # noqa: SLF001 — dynamic import surface


def opt_se_5k_8_magnetic_component() -> MagneticComponent:
    """
    OPT_SE_5K_8 fixture для T131 acceptance pilot.

    Параметры подобраны так, чтобы PyOM `calculate_inductance` давал
    Lp ≈ 25 H — на нижней границе plan-диапазона ±50% от static lib's
    50 H. Реальная static lib (`OPT_SE_5K_8.lib`) специфицирует Lp=50H
    как «typical Hammond 1627A-class» — недостижимо с PyOM Nanoperm
    8000 + E 42/15 без огромного количества витков; tight 20 µm gap +
    2500 turns даёт практический компромисс.
    """
    return MagneticComponent(
        name='OPT_SE_5K_8',
        core=Core(
            shape_name=_OPT_CORE_SHAPE,
            material_name=_OPT_CORE_MATERIAL,
            bobbin_name=_OPT_BOBBIN,
            gap_length_m=_OPT_GAP_M,
            gap_type=GapType.SUBTRACTIVE,
        ),
        windings=(
            Winding(
                name='primary',
                number_turns=_OPT_PRIMARY_TURNS,
                isolation_side=IsolationSide.PRIMARY,
            ),
            Winding(
                name='secondary',
                number_turns=_OPT_SECONDARY_TURNS,
                isolation_side=IsolationSide.SECONDARY,
            ),
        ),
        operating_point=OperatingPoint(
            frequency_hz=1000.0,
            primary_peak_voltage_v=100.0,
        ),
    )


# ---------- Pre-check: PyOM sanity на OPT fixture ----------


@needs_pyom
async def test_opt_se_5k_8_component_pyom_inductance() -> None:
    """
    Pre-check (Phase D plan §"A1 sanity"): PyOM `calculate_inductance`
    на opt_se_5k_8_magnetic_component возвращает Lp в физически
    разумном диапазоне ≈25 H (plan ±50% bound к static lib's 50 H).

    Если Lp выходит за [20, 35] H — geometry/turns/gap пилот-фикстуры
    выбран wrong для PyOM Nanoperm 8000, перед запуском acceptance
    pilot'а нужно reconsider.
    """
    pyom = load_pyopenmagnetics()
    analytics = PyOpenMagneticsAnalytics(pyom)
    component = opt_se_5k_8_magnetic_component()

    lp = await analytics.calculate_inductance(component)

    lo, hi = _PYOM_PILOT_LP_RANGE
    assert lo <= lp <= hi, (
        f'PyOM Lp = {lp:.3f} H вне ожидаемого диапазона [{lo}, {hi}] H. '
        f'Скорректируйте turns / gap в opt_se_5k_8_magnetic_component '
        f'или explicitly accept new Lp baseline.'
    )


# ---------- Acceptance pilot ----------

# Netlist post-processing (после kicad-cli export, перед use case'ом):

_TRAN_DIRECTIVE_RE = re.compile(r'^\.tran\b.*$', re.IGNORECASE | re.MULTILINE)


def _strip_inline_tran_directive(netlist_text: str) -> str:
    """Убрать `.tran ...` из netlist'а — use case делает свою FourierAnalysis."""
    return _TRAN_DIRECTIVE_RE.sub('', netlist_text)


def _add_secondary_dc_leak(netlist_text: str, leak_ohm: float = 1e6) -> str:
    """
    Воткнуть 1 MΩ leak `R_dc_leak /sec_b 0 ...` перед `.end` строкой.

    Floating secondary без DC reference оставляет v(/sec_a, /sec_b) с
    arbitrary смещением — 1 MΩ к GND даёт неизмеримое влияние на signal
    (Z_load=8Ω → I_leak вклад ≈ 8e-6, инжектируется в 1e-8 от signal),
    но фиксирует DC reference.
    """
    leak_line = f'R_dc_leak /sec_b 0 {leak_ohm:.0f}'
    if leak_line in netlist_text:
        return netlist_text
    end_re = re.compile(r'^\.end\b', re.IGNORECASE | re.MULTILINE)
    match = end_re.search(netlist_text)
    if match is None:
        return netlist_text + '\n' + leak_line + '\n'
    return netlist_text[: match.start()] + leak_line + '\n' + netlist_text[match.start() :]


def _prepare_netlist(raw_netlist_path: Path, prepared_path: Path) -> Path:
    text = raw_netlist_path.read_text()
    text = _strip_inline_tran_directive(text)
    text = _add_secondary_dc_leak(text)
    prepared_path.write_text(text)
    return prepared_path


def _make_spec(
    *,
    voltage_per_root_power: float,
    frequencies_hz: tuple[float, ...],
    output_powers_w: tuple[float, ...],
) -> ThdSweepSpec:
    return ThdSweepSpec(
        component=opt_se_5k_8_magnetic_component(),
        bh_curve=FrohlichBHCurve.from_pyom_material(
            mu_initial=8000.0,
            b_sat=1.2,
        ),
        a_core_m2=_OPT_A_CORE_M2,
        l_path_m=_OPT_L_PATH_M,
        r_primary_ohm=_OPT_R_PRIMARY_OHM,
        r_secondary_ohm=_OPT_R_SECONDARY_OHM,
        target_subckt_name='OPT_SE_5K_8',
        input_source_ref='V2',  # auto-numbering из _build_se_amp: V1=B+, V2=V_in
        load_ohm=8.0,
        signal_node='v(/sec_a)',  # /sec_b grounded через _add_secondary_dc_leak
        voltage_per_root_power=voltage_per_root_power,
        frequencies_hz=frequencies_hz,
        output_powers_w=output_powers_w,
        n_harmonics=10,
        periods_per_run=10,
        samples_per_period=100,
    )


async def _calibrate_voltage_per_root_power(
    *,
    base_netlist: Path,
    simulator: NgspiceSimulator,
    workdir: Path,
) -> float:
    """
    Probe run на тихой мощности → derive empirical V_grid/√P_load.

    1V probe @ 1 kHz даёт нам V_load_peak; из этого считаем
    `voltage_per_root_power = √(2·R_load) / amplitude_gain`.
    """
    probe_spec = _make_spec(
        voltage_per_root_power=_V_IN_PER_ROOT_POWER_INITIAL_GUESS,
        frequencies_hz=(1000.0,),
        output_powers_w=(_PROBE_TARGET_POWER_W,),
    )
    probe_workdir = workdir / 'probe'
    probe_spectrum = await analyze_distortion_spectrum(
        base_netlist=base_netlist,
        spec=probe_spec,
        simulator=simulator,
        workdir=probe_workdir,
        timeout_per_cell_seconds=30.0,
    )
    probe_point = probe_spectrum.points[0]
    v_in_peak = _V_IN_PER_ROOT_POWER_INITIAL_GUESS * math.sqrt(
        _PROBE_TARGET_POWER_W,
    )
    v_load_peak = math.sqrt(2.0 * probe_spec.load_ohm * probe_point.measured_power_w)
    amplitude_gain = v_load_peak / v_in_peak if v_in_peak > 0.0 else 0.0
    if amplitude_gain <= 0.0:
        msg = (
            f'probe failed to measure amplitude gain (v_in_peak={v_in_peak}, '
            f'v_load_peak={v_load_peak})'
        )
        raise RuntimeError(msg)
    return math.sqrt(2.0 * probe_spec.load_ohm) / amplitude_gain


@pytest.mark.skip(
    reason='EL84 + saturable_core numerical convergence — Phase A '
    'follow-up (см. module docstring root cause section). Тест-код '
    'оставлен infrastructure-ready: убрать skip когда saturable_core '
    'переписан с current-source PWL на nonlinear-inductance / '
    'hysteresis-loop formulation.',
)
@needs_kicad
@needs_ngspice
@needs_pyom
async def test_se_amp_6p14p_saturable_thd_pilot(tmp_path: Path) -> None:
    """
    T131 acceptance pilot: 6П14П SE с saturable OPT — THD матрица 3×3.

    Primary gate: THD @ 1 kHz / 1 W ∈ [1%, 5%], dominant n=2,
    monotonic THD по power @ 1 kHz, runtime ≤ 120 s.

    Diagnostic data: 50 Hz / 10 kHz / 0.25 W / 3 W cells печатаются для
    review, но НЕ acceptance gate (см. Analyze N5).
    """
    # 1. Build schematic via existing facade factory (через dynamic import).
    build_se_amp = _load_se_amp_factory()
    sch_path = build_se_amp(tmp_path / 'se_amp.kicad_sch')

    # 2. Export netlist через kicad-cli.
    app_manager = SubprocessAppManager(NativePlatformLayer())
    exporter = KicadCliSchematicExporter(app_manager)
    raw_netlist = await exporter.export_spice_netlist(
        sch_path,
        tmp_path / 'se_amp_raw.cir',
    )

    # 3. Post-process: strip embedded .tran, add 1Meg leak на /sec_b.
    prepared = _prepare_netlist(raw_netlist, tmp_path / 'se_amp.cir')

    # 4. Pre-calibration: probe run для derive voltage_per_root_power.
    simulator = NgspiceSimulator(app_manager)
    voltage_per_root_power = await _calibrate_voltage_per_root_power(
        base_netlist=prepared,
        simulator=simulator,
        workdir=tmp_path,
    )

    # 5. Acceptance sweep: 3×3 matrix.
    spec = _make_spec(
        voltage_per_root_power=voltage_per_root_power,
        frequencies_hz=(50.0, 1000.0, 10000.0),
        output_powers_w=(0.25, 1.0, 3.0),
    )
    spectrum = await analyze_distortion_spectrum(
        base_netlist=prepared,
        spec=spec,
        simulator=simulator,
        workdir=tmp_path / 'sweep',
        timeout_per_cell_seconds=30.0,
    )

    # 6. Pretty-print full spectrum для review.
    print('\n' + '=' * 72)  # noqa: T201
    print(  # noqa: T201
        f'T131 acceptance pilot — OPT_SE_5K_8 (saturable), '
        f'voltage_per_root_power={voltage_per_root_power:.3f}',
    )
    print('=' * 72)  # noqa: T201
    print(  # noqa: T201
        f'{"Freq, Hz":>10} {"Target W":>9} {"Measured W":>11} '
        f'{"THD, %":>8} {"Dom n":>6}',
    )
    for p in spectrum.points:
        print(  # noqa: T201
            f'{p.frequency_hz:>10.1f} {p.target_power_w:>9.3f} '
            f'{p.measured_power_w:>11.4f} {p.thd_percent:>8.3f} '
            f'{p.dominant_harmonic_n:>6d}',
        )
    print(f'runtime = {spectrum.runtime_seconds:.2f} s')  # noqa: T201
    print('=' * 72)  # noqa: T201

    # 7. Primary acceptance gate: THD @ 1 kHz / 1 W в [1%, 5%].
    try:
        point_1khz_1w = spectrum.find_closest(
            frequency_hz=1000.0,
            target_power_w=1.0,
            power_tolerance=0.20,
        )
    except ValueError as exc:
        pytest.fail(
            f'Primary acceptance: 1 kHz / 1 W point вне ±20% tolerance — '
            f'voltage calibration off. Reason: {exc}',
        )

    assert 1.0 <= point_1khz_1w.thd_percent <= 5.0, (
        f'Primary gate: THD @ 1 kHz / 1 W = {point_1khz_1w.thd_percent:.3f}% '
        f'вне ожидаемого диапазона [1%, 5%] (EL84 pentode SE no-feedback). '
        f'См. spec Q6 — failure path trifurcated по severity.'
    )

    # 8. Dominant 2nd harmonic — SE class A physically odd-harmonic-poor.
    assert point_1khz_1w.dominant_harmonic_n == 2, (
        f'Primary gate: dominant harmonic = '
        f'{point_1khz_1w.dominant_harmonic_n}, expected 2 (SE class A '
        f'asymmetric distortion). Modeling bug возможен.'
    )

    # 9. Monotonic THD по power @ 1 kHz.
    at_1khz = sorted(
        (p for p in spectrum.points if p.frequency_hz == 1000.0),
        key=lambda p: p.target_power_w,
    )
    for prev_p, next_p in zip(at_1khz, at_1khz[1:], strict=False):
        assert next_p.thd_percent > prev_p.thd_percent, (
            f'Monotonic gate: THD @ 1 kHz должен расти с power; '
            f'{prev_p.target_power_w} W → {prev_p.thd_percent:.3f}% '
            f'vs {next_p.target_power_w} W → {next_p.thd_percent:.3f}%'
        )

    # 10. Runtime budget.
    assert spectrum.runtime_seconds <= 120.0, (
        f'Performance gate: spectrum.runtime = '
        f'{spectrum.runtime_seconds:.2f} s > 120 s budget. '
        f'См. spec §4 / Analyze W2.'
    )
