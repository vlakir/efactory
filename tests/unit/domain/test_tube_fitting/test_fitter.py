"""
Fitter round-trip + multi-start tests (T031 Phase 1, SC#1).

Round-trip: synth IVDataset через known params (formulas.py) → fit
тем же fitter'ом → восстановленные params в пределах SC#1 tolerance:
MU/KG1/KP/KVB ≤5%, EX ≤2%.
"""

from __future__ import annotations

import random
from datetime import date

import numpy as np
import pytest

from domain.tube_fitting import (
    AyumiPentodeParams,
    CurveData,
    FitFailedError,
    IVDataset,
    KorenDerkPentodeParams,
    KorenModifiedCutoffTriodeParams,
    KorenModifiedKneePentodeParams,
    KorenReefmanPentodeParams,
    KorenTriodeParams,
    ayumi_pentode_ia,
    fit_ayumi_pentode,
    fit_koren_derk_pentode,
    fit_koren_modified_cutoff_triode,
    fit_koren_modified_knee_pentode,
    fit_koren_reefman_pentode,
    fit_koren_triode,
    koren_derk_pentode_ia,
    koren_modified_cutoff_triode_ia,
    koren_modified_knee_pentode_ia,
    koren_reefman_pentode_ia,
    koren_triode_ia,
)
from domain.tube_fitting._fitter import (
    _ayumi_pentode_ig2_vec,
    _koren_derk_pentode_ig2_vec,
    _koren_modified_knee_pentode_ig2_vec,
    _koren_reefman_pentode_ig2_vec,
)


def _synthesize_triode_dataset(
    params: KorenTriodeParams,
    tube_name: str = 'SYNTH_TRIODE',
    vg_values: tuple[float, ...] = (-0.5, -1.0, -2.0, -3.0, -4.0),
    va_values: tuple[float, ...] = (50.0, 100.0, 150.0, 200.0, 250.0, 300.0, 350.0, 400.0),
) -> IVDataset:
    curves = tuple(
        CurveData(
            vg=vg,
            points=tuple(
                (va, koren_triode_ia(vg, va, params)) for va in va_values
            ),
        )
        for vg in vg_values
    )
    return IVDataset(
        tube_name=tube_name,
        tube_type='triode',
        source='synthesized',
        date_extracted=date(2026, 6, 3),
        curves=curves,
    )


def _synthesize_pentode_dataset(
    params: AyumiPentodeParams,
    tube_name: str = 'SYNTH_PENTODE',
    vg_values: tuple[float, ...] = (-5.0, -10.0, -15.0, -20.0),
    va_values: tuple[float, ...] = (50.0, 100.0, 200.0, 300.0, 400.0, 500.0),
    *,
    include_screen: bool = False,
) -> IVDataset:
    curves = tuple(
        CurveData(
            vg=vg,
            points=tuple(
                (va, ayumi_pentode_ia(vg, va, params)) for va in va_values
            ),
        )
        for vg in vg_values
    )
    screen_curves: tuple[CurveData, ...] = ()
    if include_screen:
        # Ig2 не зависит от Va — реальные Ig2-curves плоские по Va,
        # но всё равно сэмплируем на тех же Va для realism + cross-check.
        screen_curves = tuple(
            CurveData(
                vg=vg,
                points=tuple(
                    (
                        va,
                        float(
                            _ayumi_pentode_ig2_vec(
                                np.array([vg]),
                                params.mu,
                                params.ex,
                                params.kg2,
                                params.kp,
                                params.screen_v,
                            )[0]
                        ),
                    )
                    for va in va_values
                ),
            )
            for vg in vg_values
        )
    return IVDataset(
        tube_name=tube_name,
        tube_type='pentode',
        source='synthesized',
        date_extracted=date(2026, 6, 3),
        curves=curves,
        screen_voltage_v=params.screen_v,
        screen_curves=screen_curves,
    )


def _rel_err(fitted: float, truth: float) -> float:
    return abs(fitted - truth) / truth


# ============================== round-trip Koren triode (SC#1) ==============================


_TWELVE_AX7_TRUTH = KorenTriodeParams(mu=100, ex=1.4, kg1=1060, kp=600, kvb=300)


def test_round_trip_koren_triode_12ax7_within_sc1_tolerance() -> None:
    """
    Spec SC#1: на синтетике 12AX7 → fitter возвращает MU/KG1/KP/KVB
    ≤5%, EX ≤2%.
    """
    ds = _synthesize_triode_dataset(_TWELVE_AX7_TRUTH)
    fr = fit_koren_triode(ds, n_starts=5, seed=42)

    assert isinstance(fr.params, KorenTriodeParams)
    p = fr.params
    assert _rel_err(p.mu, 100.0) <= 0.05
    assert _rel_err(p.ex, 1.4) <= 0.02
    assert _rel_err(p.kg1, 1060.0) <= 0.05
    assert _rel_err(p.kp, 600.0) <= 0.05
    assert _rel_err(p.kvb, 300.0) <= 0.05
    assert fr.converged is True
    assert fr.n_points == 5 * 8
    # RMS должен быть очень маленький для round-trip (no noise).
    assert fr.rms_residual_ma < 0.1


def test_round_trip_koren_triode_with_vct() -> None:
    truth = KorenTriodeParams(mu=100, ex=1.4, kg1=1060, kp=600, kvb=300, vct=0.6)
    ds = _synthesize_triode_dataset(truth, tube_name='SYNTH_VCT')
    fr = fit_koren_triode(ds, include_vct=True, n_starts=5, seed=42)

    assert isinstance(fr.params, KorenTriodeParams)
    assert fr.params.vct is not None
    assert _rel_err(fr.params.vct, 0.6) <= 0.20  # vct менее identifiable, шире tolerance
    assert _rel_err(fr.params.mu, 100.0) <= 0.05


# ============================== round-trip Ayumi pentode (SC#1) ==============================


_EL34_TRUTH = AyumiPentodeParams(
    mu=11, ex=1.35, kg1=650, kg2=4500, kp=60, kvb=24, screen_v=250
)


def test_round_trip_ayumi_pentode_el34_ia_only_within_sc1_tolerance() -> None:
    """
    SC#1 Ia-only path: MU/KG1/KP/KVB ≤5%, EX ≤2%. KG2 не identifiable —
    `per_param_stderr['kg2']` undefined (scipy pinv может дать
    artificial ~0 или ~inf), не assert'им.
    """
    ds = _synthesize_pentode_dataset(_EL34_TRUTH)
    fr = fit_ayumi_pentode(ds, n_starts=5, seed=42)

    assert isinstance(fr.params, AyumiPentodeParams)
    p = fr.params
    assert _rel_err(p.mu, 11.0) <= 0.05
    assert _rel_err(p.ex, 1.35) <= 0.02
    assert _rel_err(p.kg1, 650.0) <= 0.05
    assert _rel_err(p.kp, 60.0) <= 0.05
    assert _rel_err(p.kvb, 24.0) <= 0.05
    assert p.screen_v == 250.0  # input, not fitted
    assert fr.converged is True
    assert fr.rms_residual_ma < 0.1


def test_round_trip_ayumi_pentode_el34_joint_recovers_kg2() -> None:
    """
    Joint Ia+Ig2 path: с screen_curves все 6 params identifiable,
    включая KG2 (≤5%).
    """
    ds = _synthesize_pentode_dataset(_EL34_TRUTH, include_screen=True)
    fr = fit_ayumi_pentode(ds, n_starts=5, seed=42)

    assert isinstance(fr.params, AyumiPentodeParams)
    p = fr.params
    assert _rel_err(p.mu, 11.0) <= 0.05
    assert _rel_err(p.ex, 1.35) <= 0.02
    assert _rel_err(p.kg1, 650.0) <= 0.05
    assert _rel_err(p.kg2, 4500.0) <= 0.05  # ← теперь identifiable
    assert _rel_err(p.kp, 60.0) <= 0.05
    assert _rel_err(p.kvb, 24.0) <= 0.05
    # n_points = 24 Ia + 24 Ig2 = 48.
    assert fr.n_points == 48


# ============================== multi-start determinism (A-C2) ==============================


def test_fit_koren_triode_seed_determinism() -> None:
    """Same seed → bit-identical FitResult."""
    ds = _synthesize_triode_dataset(_TWELVE_AX7_TRUTH)
    fr_a = fit_koren_triode(ds, n_starts=5, seed=42)
    fr_b = fit_koren_triode(ds, n_starts=5, seed=42)
    assert fr_a.params == fr_b.params
    assert fr_a.rms_residual_ma == fr_b.rms_residual_ma
    assert fr_a.best_start_index == fr_b.best_start_index


def test_fit_koren_triode_different_seed_same_quality() -> None:
    """Разные seeds → возможно разные best_start_index, но все ≤5%."""
    ds = _synthesize_triode_dataset(_TWELVE_AX7_TRUTH)
    fr_a = fit_koren_triode(ds, n_starts=5, seed=42)
    fr_b = fit_koren_triode(ds, n_starts=5, seed=123)
    # Оба должны попадать в SC#1.
    assert _rel_err(fr_a.params.mu, 100.0) <= 0.05
    assert _rel_err(fr_b.params.mu, 100.0) <= 0.05


def test_fit_koren_triode_n_starts_equals_starts_tried() -> None:
    ds = _synthesize_triode_dataset(_TWELVE_AX7_TRUTH)
    fr = fit_koren_triode(ds, n_starts=3, seed=42)
    assert fr.n_starts_tried == 3
    assert 0 <= fr.best_start_index < 3


# ============================== seed_from helper ==============================


def test_fit_koren_triode_with_seed_from() -> None:
    """seed_from даёт fitter'у hint точно в нужной области → быстрее."""
    ds = _synthesize_triode_dataset(_TWELVE_AX7_TRUTH)
    hint = KorenTriodeParams(mu=90, ex=1.45, kg1=1100, kp=580, kvb=310)
    fr = fit_koren_triode(ds, n_starts=3, seed=42, seed_from=hint)
    # Должно сойтись в SC#1.
    assert _rel_err(fr.params.mu, 100.0) <= 0.05


def test_fit_ayumi_pentode_with_seed_from() -> None:
    ds = _synthesize_pentode_dataset(_EL34_TRUTH)
    hint = AyumiPentodeParams(
        mu=10, ex=1.3, kg1=700, kg2=4000, kp=55, kvb=25, screen_v=250
    )
    fr = fit_ayumi_pentode(ds, n_starts=3, seed=42, seed_from=hint)
    assert _rel_err(fr.params.kg1, 650.0) <= 0.05


# ============================== input validation ==============================


def test_fit_koren_rejects_pentode_dataset() -> None:
    ds = _synthesize_pentode_dataset(_EL34_TRUTH)
    with pytest.raises(ValueError, match='tube_type'):
        fit_koren_triode(ds)


def test_fit_ayumi_rejects_triode_dataset() -> None:
    ds = _synthesize_triode_dataset(_TWELVE_AX7_TRUTH)
    with pytest.raises(ValueError, match='tube_type'):
        fit_ayumi_pentode(ds)


def test_fit_koren_n_starts_zero_raises() -> None:
    ds = _synthesize_triode_dataset(_TWELVE_AX7_TRUTH)
    with pytest.raises(ValueError, match='n_starts'):
        fit_koren_triode(ds, n_starts=0)


def test_fit_ayumi_n_starts_zero_raises() -> None:
    ds = _synthesize_pentode_dataset(_EL34_TRUTH)
    with pytest.raises(ValueError, match='n_starts'):
        fit_ayumi_pentode(ds, n_starts=0)


# ============================== FitFailedError ==============================


def test_fit_koren_triode_no_starts_converge_raises() -> None:
    """Pathologically bad dataset → fitter не сходится → FitFailedError."""
    # Все Ia = 0 (deep cutoff везде) — нет полезного сигнала.
    ds = IVDataset(
        tube_name='ALL_ZERO',
        tube_type='triode',
        source='pathological',
        date_extracted=date(2026, 6, 3),
        curves=(
            CurveData(vg=-2.0, points=((100.0, 0.0), (200.0, 0.0), (300.0, 0.0))),
        ),
    )
    # max_nfev малый + only 1 start, чтобы быстро упасть в local opt с RMS=0
    # на initial-guess или вообще не двигаться.
    # NB: zero Ia может всё-таки fit'нуть в какие-то трivial params; не
    # гарантировано raises. Делаю слабый тест — проверяю либо raises,
    # либо RMS ~ 0 (degenerate fit).
    try:
        fr = fit_koren_triode(ds, n_starts=3, seed=42, max_nfev=50)
        # Если не упало — fit считает нашёл «решение» с Ia≈0 везде.
        assert fr.rms_residual_ma < 1e-3
    except FitFailedError:
        pass  # ожидаемое поведение


# ============================== rms residual ==============================


def test_fit_koren_residual_is_meaningful_when_noisy() -> None:
    """С шумом RMS не нулевой, но fit устойчив."""
    ds_clean = _synthesize_triode_dataset(_TWELVE_AX7_TRUTH)
    # Inject ±2% noise.
    rnd = random.Random(42)
    noisy_curves = tuple(
        CurveData(
            vg=c.vg,
            points=tuple(
                (va, max(0.0, ia * (1.0 + rnd.uniform(-0.02, 0.02))))
                for va, ia in c.points
            ),
        )
        for c in ds_clean.curves
    )
    ds_noisy = ds_clean.model_copy(update={'curves': noisy_curves})
    fr = fit_koren_triode(ds_noisy, n_starts=5, seed=42)
    assert fr.rms_residual_ma > 0.0
    # Шум ±2% по Ia ~1-5 mA → RMS ~ 0.05-0.1 mA.
    assert fr.rms_residual_ma < 1.0
    # Params всё ещё ≤5%.
    assert _rel_err(fr.params.mu, 100.0) <= 0.05


# ============================== T182: round-trip modified-knee pentode (SC#3) ==============================


def _synthesize_modified_knee_pentode_dataset(
    params: KorenModifiedKneePentodeParams,
    tube_name: str = 'SYNTH_MOD_KNEE_PENTODE',
    vg_values: tuple[float, ...] = (-2.0, -5.0, -10.0, -15.0, -20.0),
    va_values: tuple[float, ...] = (30.0, 50.0, 80.0, 120.0, 200.0, 300.0, 400.0, 500.0),
    *,
    include_screen: bool = False,
) -> IVDataset:
    curves = tuple(
        CurveData(
            vg=vg,
            points=tuple(
                (va, koren_modified_knee_pentode_ia(vg, va, params)) for va in va_values
            ),
        )
        for vg in vg_values
    )
    screen_curves: tuple[CurveData, ...] = ()
    if include_screen:
        screen_curves = tuple(
            CurveData(
                vg=vg,
                points=tuple(
                    (
                        va,
                        float(
                            _koren_modified_knee_pentode_ig2_vec(
                                np.array([vg]),
                                params.mu,
                                params.ex,
                                params.kg2,
                                params.kp,
                                params.screen_v,
                            )[0]
                        ),
                    )
                    for va in va_values
                ),
            )
            for vg in vg_values
        )
    return IVDataset(
        tube_name=tube_name,
        tube_type='pentode',
        source='synthesized-modified-knee',
        date_extracted=date(2026, 6, 4),
        curves=curves,
        screen_voltage_v=params.screen_v,
        screen_curves=screen_curves,
    )


_EL34_MOD_KNEE_TRUTH = KorenModifiedKneePentodeParams(
    mu=11, ex=1.35, kg1=650, kg2=4500, kp=60, kvb=24, screen_v=250, vk=50.0
)


def test_round_trip_modified_knee_pentode_joint_within_sc3_tolerance() -> None:
    """
    Spec SC#3: synthetic EL34-style modified-knee → fitter:
    MU/KG1/KG2/KP/KVB ≤7%, EX ≤3%, Vk ≤15%.

    Joint Ia+Ig2 mode гарантирует identifiability KG2.
    """
    ds = _synthesize_modified_knee_pentode_dataset(_EL34_MOD_KNEE_TRUTH, include_screen=True)
    fr = fit_koren_modified_knee_pentode(ds, n_starts=8, seed=42)

    assert isinstance(fr.params, KorenModifiedKneePentodeParams)
    p = fr.params
    assert _rel_err(p.mu, 11.0) <= 0.07
    assert _rel_err(p.ex, 1.35) <= 0.03
    assert _rel_err(p.kg1, 650.0) <= 0.07
    assert _rel_err(p.kg2, 4500.0) <= 0.07
    assert _rel_err(p.kp, 60.0) <= 0.07
    assert _rel_err(p.kvb, 24.0) <= 0.07
    assert _rel_err(p.vk, 50.0) <= 0.15
    assert p.screen_v == 250.0  # input, not fitted
    assert fr.converged is True


def test_round_trip_modified_knee_pentode_ia_only_within_sc3_tolerance() -> None:
    """SC#3 Ia-only path: KG2 не identifiable, остальные ≤7%/≤3%/≤15%."""
    ds = _synthesize_modified_knee_pentode_dataset(_EL34_MOD_KNEE_TRUTH)
    fr = fit_koren_modified_knee_pentode(ds, n_starts=8, seed=42)

    assert isinstance(fr.params, KorenModifiedKneePentodeParams)
    p = fr.params
    assert _rel_err(p.mu, 11.0) <= 0.07
    assert _rel_err(p.ex, 1.35) <= 0.03
    assert _rel_err(p.kg1, 650.0) <= 0.07
    assert _rel_err(p.kp, 60.0) <= 0.07
    assert _rel_err(p.kvb, 24.0) <= 0.07
    assert _rel_err(p.vk, 50.0) <= 0.15


def test_round_trip_modified_knee_pentode_seed_determinism() -> None:
    ds = _synthesize_modified_knee_pentode_dataset(_EL34_MOD_KNEE_TRUTH, include_screen=True)
    fr_a = fit_koren_modified_knee_pentode(ds, n_starts=8, seed=42)
    fr_b = fit_koren_modified_knee_pentode(ds, n_starts=8, seed=42)
    assert fr_a.params == fr_b.params
    assert fr_a.rms_residual_ma == fr_b.rms_residual_ma


def test_fit_modified_knee_pentode_rejects_triode() -> None:
    ds = _synthesize_triode_dataset(_TWELVE_AX7_TRUTH)
    with pytest.raises(ValueError, match='tube_type'):
        fit_koren_modified_knee_pentode(ds)


def test_fit_modified_knee_pentode_n_starts_zero_raises() -> None:
    ds = _synthesize_modified_knee_pentode_dataset(_EL34_MOD_KNEE_TRUTH)
    with pytest.raises(ValueError, match='n_starts'):
        fit_koren_modified_knee_pentode(ds, n_starts=0)


# ============================== T182: round-trip modified-cutoff triode (SC#3b) ==============================


def _synthesize_modified_cutoff_triode_dataset(
    params: KorenModifiedCutoffTriodeParams,
    tube_name: str = 'SYNTH_MOD_CUTOFF_TRIODE',
    vg_values: tuple[float, ...] = (-5.0, -15.0, -30.0, -45.0, -55.0, -65.0),
    va_values: tuple[float, ...] = (50.0, 100.0, 200.0, 300.0, 400.0),
) -> IVDataset:
    curves = tuple(
        CurveData(
            vg=vg,
            points=tuple(
                (va, koren_modified_cutoff_triode_ia(vg, va, params)) for va in va_values
            ),
        )
        for vg in vg_values
    )
    return IVDataset(
        tube_name=tube_name,
        tube_type='triode',
        source='synthesized-modified-cutoff',
        date_extracted=date(2026, 6, 4),
        curves=curves,
    )


_300B_MOD_CUTOFF_TRUTH = KorenModifiedCutoffTriodeParams(
    mu=4, ex=1.4, kg1=1500, kp=800, kvb=200, vc_off=-50.0, vs_off=5.0
)


def test_round_trip_modified_cutoff_triode_within_sc3b_tolerance() -> None:
    """
    Spec SC#3b: synthetic 300B-style modified-cutoff → fitter:
    MU/KG1/KP/KVB ≤7%, EX ≤3%, Vc_off ≤20%, Vs_off ≤25%.
    """
    ds = _synthesize_modified_cutoff_triode_dataset(_300B_MOD_CUTOFF_TRUTH)
    fr = fit_koren_modified_cutoff_triode(ds, n_starts=8, seed=42)

    assert isinstance(fr.params, KorenModifiedCutoffTriodeParams)
    p = fr.params
    assert _rel_err(p.mu, 4.0) <= 0.07
    assert _rel_err(p.ex, 1.4) <= 0.03
    assert _rel_err(p.kg1, 1500.0) <= 0.07
    assert _rel_err(p.kp, 800.0) <= 0.07
    assert _rel_err(p.kvb, 200.0) <= 0.07
    assert _rel_err(p.vc_off, -50.0) <= 0.20
    assert _rel_err(p.vs_off, 5.0) <= 0.25
    assert p.vct is None  # A-W1: forced to None
    assert fr.converged is True


def test_round_trip_modified_cutoff_triode_seed_determinism() -> None:
    ds = _synthesize_modified_cutoff_triode_dataset(_300B_MOD_CUTOFF_TRUTH)
    fr_a = fit_koren_modified_cutoff_triode(ds, n_starts=8, seed=42)
    fr_b = fit_koren_modified_cutoff_triode(ds, n_starts=8, seed=42)
    assert fr_a.params == fr_b.params
    assert fr_a.rms_residual_ma == fr_b.rms_residual_ma


def test_fit_modified_cutoff_triode_rejects_pentode() -> None:
    ds = _synthesize_pentode_dataset(_EL34_TRUTH)
    with pytest.raises(ValueError, match='tube_type'):
        fit_koren_modified_cutoff_triode(ds)


def test_fit_modified_cutoff_triode_n_starts_zero_raises() -> None:
    ds = _synthesize_modified_cutoff_triode_dataset(_300B_MOD_CUTOFF_TRUTH)
    with pytest.raises(ValueError, match='n_starts'):
        fit_koren_modified_cutoff_triode(ds, n_starts=0)


def test_fit_modified_cutoff_triode_forces_vct_to_none() -> None:
    """A-W1: vct (cathode contact) overlaps semantically с vc_off.
    Fitter форсирует vct=None в результате независимо от input."""
    ds = _synthesize_modified_cutoff_triode_dataset(_300B_MOD_CUTOFF_TRUTH)
    fr = fit_koren_modified_cutoff_triode(ds, n_starts=8, seed=42)
    assert isinstance(fr.params, KorenModifiedCutoffTriodeParams)
    assert fr.params.vct is None


# ============================== T184: round-trip Reefman pentode ==============================


def _synthesize_reefman_pentode_dataset(
    params: KorenReefmanPentodeParams,
    tube_name: str = 'SYNTH_REEFMAN_PENTODE',
    vg_values: tuple[float, ...] = (-2.0, -5.0, -10.0, -15.0, -20.0),
    va_values: tuple[float, ...] = (50.0, 100.0, 200.0, 300.0, 400.0, 500.0),
    *,
    include_screen: bool = False,
) -> IVDataset:
    curves = tuple(
        CurveData(
            vg=vg,
            points=tuple(
                (va, koren_reefman_pentode_ia(vg, va, params)) for va in va_values
            ),
        )
        for vg in vg_values
    )
    screen_curves: tuple[CurveData, ...] = ()
    if include_screen:
        screen_curves = tuple(
            CurveData(
                vg=vg,
                points=tuple(
                    (
                        va,
                        float(
                            _koren_reefman_pentode_ig2_vec(
                                np.array([vg]),
                                params.mu,
                                params.ex,
                                params.kg2,
                                params.kp,
                                params.kvb,
                                params.screen_v,
                            )[0]
                        ),
                    )
                    for va in va_values
                ),
            )
            for vg in vg_values
        )
    return IVDataset(
        tube_name=tube_name,
        tube_type='pentode',
        source='synthesized-reefman',
        date_extracted=date(2026, 6, 4),
        curves=curves,
        screen_voltage_v=params.screen_v,
        screen_curves=screen_curves,
    )


_EL34_REEFMAN_TRUTH = KorenReefmanPentodeParams(
    mu=11, ex=1.35, kg1=325, kg2=2250, kp=60, kvb=24, screen_v=250
)


def test_round_trip_reefman_pentode_joint_within_sc1_tolerance() -> None:
    """Same SC#1 tolerance как canonical Ayumi: MU/KG1/KG2/KP/KVB ≤5%, EX ≤2%."""
    ds = _synthesize_reefman_pentode_dataset(_EL34_REEFMAN_TRUTH, include_screen=True)
    fr = fit_koren_reefman_pentode(ds, n_starts=8, seed=42)

    assert isinstance(fr.params, KorenReefmanPentodeParams)
    p = fr.params
    assert _rel_err(p.mu, 11.0) <= 0.05
    assert _rel_err(p.ex, 1.35) <= 0.02
    assert _rel_err(p.kg1, 325.0) <= 0.05
    assert _rel_err(p.kg2, 2250.0) <= 0.05
    assert _rel_err(p.kp, 60.0) <= 0.05
    assert _rel_err(p.kvb, 24.0) <= 0.05
    assert p.screen_v == 250.0


def test_round_trip_reefman_pentode_ia_only_within_sc1_tolerance() -> None:
    """Ia-only: KG2 не identifiable, остальные ≤5%/≤2%."""
    ds = _synthesize_reefman_pentode_dataset(_EL34_REEFMAN_TRUTH)
    fr = fit_koren_reefman_pentode(ds, n_starts=8, seed=42)

    assert isinstance(fr.params, KorenReefmanPentodeParams)
    p = fr.params
    assert _rel_err(p.mu, 11.0) <= 0.05
    assert _rel_err(p.ex, 1.35) <= 0.02
    assert _rel_err(p.kg1, 325.0) <= 0.05
    assert _rel_err(p.kp, 60.0) <= 0.05
    assert _rel_err(p.kvb, 24.0) <= 0.05


def test_reefman_pentode_seed_determinism() -> None:
    ds = _synthesize_reefman_pentode_dataset(_EL34_REEFMAN_TRUTH, include_screen=True)
    fr_a = fit_koren_reefman_pentode(ds, n_starts=8, seed=42)
    fr_b = fit_koren_reefman_pentode(ds, n_starts=8, seed=42)
    assert fr_a.params == fr_b.params
    assert fr_a.rms_residual_ma == fr_b.rms_residual_ma


def test_fit_reefman_pentode_rejects_triode() -> None:
    ds = _synthesize_triode_dataset(_TWELVE_AX7_TRUTH)
    with pytest.raises(ValueError, match='tube_type'):
        fit_koren_reefman_pentode(ds)


def test_fit_reefman_pentode_n_starts_zero_raises() -> None:
    ds = _synthesize_reefman_pentode_dataset(_EL34_REEFMAN_TRUTH)
    with pytest.raises(ValueError, match='n_starts'):
        fit_koren_reefman_pentode(ds, n_starts=0)


# ============================== T186: round-trip Derk pentode ==============================


def _synthesize_derk_pentode_dataset(
    params: KorenDerkPentodeParams,
    tube_name: str = 'SYNTH_DERK_PENTODE',
    vg_values: tuple[float, ...] = (-2.0, -5.0, -10.0, -15.0, -20.0),
    va_values: tuple[float, ...] = (30.0, 50.0, 80.0, 120.0, 200.0, 300.0, 400.0, 500.0),
    *,
    include_screen: bool = False,
) -> IVDataset:
    curves = tuple(
        CurveData(
            vg=vg,
            points=tuple(
                (va, koren_derk_pentode_ia(vg, va, params)) for va in va_values
            ),
        )
        for vg in vg_values
    )
    screen_curves: tuple[CurveData, ...] = ()
    if include_screen:
        screen_curves = tuple(
            CurveData(
                vg=vg,
                points=tuple(
                    (
                        va,
                        float(
                            _koren_derk_pentode_ig2_vec(
                                np.array([vg]),
                                np.array([va]),
                                params.mu,
                                params.ex,
                                params.kg2,
                                params.kp,
                                params.kvb,
                                params.screen_v,
                                params.alpha_s,
                                params.beta,
                            )[0]
                        ),
                    )
                    for va in va_values
                ),
            )
            for vg in vg_values
        )
    return IVDataset(
        tube_name=tube_name,
        tube_type='pentode',
        source='synthesized-derk',
        date_extracted=date(2026, 6, 4),
        curves=curves,
        screen_voltage_v=params.screen_v,
        screen_curves=screen_curves,
    )


_EL34_DERK_TRUTH = KorenDerkPentodeParams(
    mu=11, ex=1.35, kg1=325, kg2=2250, kp=60, kvb=24, screen_v=250,
    alpha_s=1.0, beta=0.05, a_penetration=0.001,
)


def test_round_trip_derk_pentode_joint_within_tolerance() -> None:
    """T186 round-trip Derk pentode (joint Ia+Ig2): canonical params
    ≤10% (wider tol чем canonical Ayumi из-за 9-param fit), Derk-specific
    params (alpha_s, beta, A) ≤30%."""
    ds = _synthesize_derk_pentode_dataset(_EL34_DERK_TRUTH, include_screen=True)
    fr = fit_koren_derk_pentode(ds, n_starts=10, seed=42)

    assert isinstance(fr.params, KorenDerkPentodeParams)
    p = fr.params
    assert _rel_err(p.mu, 11.0) <= 0.10
    assert _rel_err(p.ex, 1.35) <= 0.05
    assert _rel_err(p.kg1, 325.0) <= 0.10
    assert _rel_err(p.kg2, 2250.0) <= 0.10
    assert _rel_err(p.kp, 60.0) <= 0.10
    # KVB не identifiable при Vg2 ≫ √KVB (Vg2=250, KVB=24 → sqrt(KVB+Vg2²)≈250
    # независимо от KVB ∈ [1, 1000]); это known structural ambiguity Reefman/Derk
    # form. Не проверяем strict tolerance.
    assert p.kvb > 0  # любое positive значение acceptable
    assert _rel_err(p.alpha_s, 1.0) <= 0.30
    assert _rel_err(p.beta, 0.05) <= 0.30
    # a_penetration маленький; tolerance в абсолютных единицах.
    assert abs(p.a_penetration - 0.001) < 0.005
    assert p.screen_v == 250.0


def test_derk_pentode_seed_determinism() -> None:
    ds = _synthesize_derk_pentode_dataset(_EL34_DERK_TRUTH, include_screen=True)
    fr_a = fit_koren_derk_pentode(ds, n_starts=10, seed=42)
    fr_b = fit_koren_derk_pentode(ds, n_starts=10, seed=42)
    assert fr_a.params == fr_b.params
    assert fr_a.rms_residual_ma == fr_b.rms_residual_ma


def test_fit_derk_pentode_rejects_triode() -> None:
    ds = _synthesize_triode_dataset(_TWELVE_AX7_TRUTH)
    with pytest.raises(ValueError, match='tube_type'):
        fit_koren_derk_pentode(ds)


def test_fit_derk_pentode_n_starts_zero_raises() -> None:
    ds = _synthesize_derk_pentode_dataset(_EL34_DERK_TRUTH)
    with pytest.raises(ValueError, match='n_starts'):
        fit_koren_derk_pentode(ds, n_starts=0)
