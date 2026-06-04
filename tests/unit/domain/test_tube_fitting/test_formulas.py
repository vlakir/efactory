"""
Forward Ia(Vg, Va) compute reference values (T031 Phase 1).

Reference values вычислены вручную в Phase 0 probe:

* 12AX7 (MU=100, EX=1.4, KG1=1060, KP=600, KVB=300) at Vg=-2, Va=250
  → Ia ≈ 0.9534 mA.
* EL34 (MU=11, EX=1.35, KG1=650, KP=60, KVB=24, screen_v=250) at
  Vg=-12.2, Va=250 → Ia ≈ 113.3 mA.
"""

from __future__ import annotations

import math

import pytest

from domain.tube_fitting import (
    AyumiPentodeParams,
    KorenDerkPentodeParams,
    KorenModifiedCutoffTriodeParams,
    KorenModifiedKneePentodeParams,
    KorenReefmanPentodeParams,
    KorenTriodeParams,
    ayumi_pentode_ia,
    koren_derk_pentode_ia,
    koren_derk_pentode_ig2,
    koren_modified_cutoff_triode_ia,
    koren_modified_knee_pentode_ia,
    koren_reefman_pentode_ia,
    koren_reefman_pentode_ig2,
    koren_triode_ia,
)


# ============================== Koren triode ==============================


_TWELVE_AX7 = KorenTriodeParams(mu=100, ex=1.4, kg1=1060, kp=600, kvb=300)


def test_koren_triode_12ax7_at_known_point() -> None:
    ia = koren_triode_ia(vg=-2.0, va=250.0, params=_TWELVE_AX7)
    # Hand-calc: 0.953 mA; allow ±2% rounding tolerance.
    assert ia == pytest.approx(0.9534, rel=2e-2)


def test_koren_triode_cutoff_returns_negligible() -> None:
    # Strongly negative grid → deep cutoff. Strict zero численно не
    # достижим (softplus всегда > 0 для finite arg), но Ia физически
    # negligible — ниже datasheet resolution (~10 µA в mA scale).
    ia = koren_triode_ia(vg=-100.0, va=250.0, params=_TWELVE_AX7)
    assert ia < 0.01  # < 10 µA = ниже шумового пола


def test_koren_triode_monotonic_in_va() -> None:
    # На фиксированном Vg, Ia должен расти при увеличении Va.
    ias = [koren_triode_ia(vg=-2.0, va=v, params=_TWELVE_AX7) for v in (100, 200, 300, 400)]
    assert ias[0] < ias[1] < ias[2] < ias[3]


def test_koren_triode_monotonic_in_vg() -> None:
    # При фиксированном Va, Ia должен расти при увеличении Vg (-3 → -1).
    ias = [koren_triode_ia(vg=v, va=250.0, params=_TWELVE_AX7) for v in (-3.0, -2.0, -1.0)]
    assert ias[0] < ias[1] < ias[2]


def test_koren_triode_vct_shifts_curve_up() -> None:
    # Vct>0 effectively reduces |Vg|, увеличивает Ia.
    p0 = KorenTriodeParams(mu=100, ex=1.4, kg1=1060, kp=600, kvb=300, vct=0.0)
    p1 = KorenTriodeParams(mu=100, ex=1.4, kg1=1060, kp=600, kvb=300, vct=0.5)
    ia0 = koren_triode_ia(vg=-2.0, va=250.0, params=p0)
    ia1 = koren_triode_ia(vg=-2.0, va=250.0, params=p1)
    assert ia1 > ia0


def test_koren_triode_handles_large_arg_no_overflow() -> None:
    # Очень большие Vg → arg в softplus → должно не падать в overflow.
    # Это защита от math.exp(arg) при arg ~ 100+; используется fallback.
    ia = koren_triode_ia(vg=10.0, va=250.0, params=_TWELVE_AX7)
    assert math.isfinite(ia)
    assert ia > 0.0


# ============================== Ayumi pentode ==============================


_EL34 = AyumiPentodeParams(
    mu=11, ex=1.35, kg1=650, kg2=4500, kp=60, kvb=24, screen_v=250
)


def test_ayumi_pentode_el34_at_known_point() -> None:
    # Phase 0 manual: Vg=-12.2, Va=250 → 113.3 mA.
    ia = ayumi_pentode_ia(vg=-12.2, va=250.0, params=_EL34)
    assert ia == pytest.approx(113.3, rel=1e-2)


def test_ayumi_pentode_phase_0_reference_op_point() -> None:
    # Published Mullard op-point: Vg=-12.2, Va=250 → expected Ia=100 mA
    # (datasheet text value). Model = 113.3 mA → +13.4% built-in fit error.
    # Это **известный** model-vs-real gap (Phase 0); тест фиксирует
    # math, не качество fit'а.
    ia = ayumi_pentode_ia(vg=-12.2, va=250.0, params=_EL34)
    assert 110.0 < ia < 117.0


def test_ayumi_pentode_cutoff_returns_negligible() -> None:
    ia = ayumi_pentode_ia(vg=-50.0, va=250.0, params=_EL34)
    assert ia < 0.01  # см. test_koren_triode_cutoff_returns_negligible


def test_ayumi_pentode_monotonic_in_va() -> None:
    ias = [ayumi_pentode_ia(vg=-10.0, va=v, params=_EL34) for v in (50, 100, 200, 400)]
    assert ias[0] < ias[1] < ias[2] < ias[3]


def test_ayumi_pentode_monotonic_in_vg() -> None:
    ias = [ayumi_pentode_ia(vg=v, va=250.0, params=_EL34) for v in (-20.0, -15.0, -10.0, -5.0)]
    assert ias[0] < ias[1] < ias[2] < ias[3]


def test_ayumi_pentode_atan_plateau_approaches_max() -> None:
    # При Va → ∞, atan(Va/KVB) → π/2, Ia стремится к плато.
    ia_far = ayumi_pentode_ia(vg=-10.0, va=2000.0, params=_EL34)
    ia_close = ayumi_pentode_ia(vg=-10.0, va=400.0, params=_EL34)
    # Ratio должен быть < 1.10 (plateau).
    assert ia_far / ia_close < 1.10


# ============================== T182: Modified Koren-pentode (knee) ==============================


_EL34_MOD_KNEE = KorenModifiedKneePentodeParams(
    mu=11, ex=1.35, kg1=650, kg2=4500, kp=60, kvb=24, screen_v=250, vk=50.0
)


def test_modified_knee_pentode_el34_plateau_matches_canonical() -> None:
    # Plateau region (Va ≫ Vk): modifier (1-exp(-Va/Vk)) ≈ 1, должно быть
    # близко к canonical Ayumi EL34 (113.3 mA).
    ia = koren_modified_knee_pentode_ia(vg=-12.2, va=250.0, params=_EL34_MOD_KNEE)
    assert ia == pytest.approx(112.64, rel=2e-2)


def test_modified_knee_pentode_el34_knee_region_lower_than_canonical() -> None:
    # Hand-calc: canonical EL34 @ Vg=-12.2, Va=50 → 86.36 mA;
    # modified-knee vk=50 → 54.59 mA (-37%, modifier даёт sharper rise).
    ia_mod = koren_modified_knee_pentode_ia(vg=-12.2, va=50.0, params=_EL34_MOD_KNEE)
    ia_can = ayumi_pentode_ia(
        vg=-12.2,
        va=50.0,
        params=AyumiPentodeParams(
            mu=11, ex=1.35, kg1=650, kg2=4500, kp=60, kvb=24, screen_v=250
        ),
    )
    assert ia_mod == pytest.approx(54.59, rel=2e-2)
    assert ia_mod < ia_can  # знак modifier'а: knee давит Ia вниз


def test_modified_knee_pentode_zero_va_returns_zero() -> None:
    # Modifier (1 - exp(-0/Vk)) = 0. И atan(0) = 0. Дважды zero.
    ia = koren_modified_knee_pentode_ia(vg=-5.0, va=0.001, params=_EL34_MOD_KNEE)
    assert ia < 0.05  # negligible near zero


def test_modified_knee_pentode_plateau_unchanged_vs_canonical() -> None:
    # При Va → ∞ modifier → 1, должно совпасть с canonical.
    ia_mod_far = koren_modified_knee_pentode_ia(
        vg=-10.0, va=2000.0, params=_EL34_MOD_KNEE
    )
    ia_can_far = ayumi_pentode_ia(
        vg=-10.0,
        va=2000.0,
        params=AyumiPentodeParams(
            mu=11, ex=1.35, kg1=650, kg2=4500, kp=60, kvb=24, screen_v=250
        ),
    )
    assert ia_mod_far == pytest.approx(ia_can_far, rel=1e-2)


def test_modified_knee_pentode_monotonic_in_va() -> None:
    ias = [
        koren_modified_knee_pentode_ia(vg=-10.0, va=v, params=_EL34_MOD_KNEE)
        for v in (50, 100, 200, 400)
    ]
    assert ias[0] < ias[1] < ias[2] < ias[3]


def test_modified_knee_pentode_smaller_vk_gives_steeper_knee() -> None:
    # vk=10 — резче подъём; vk=100 — мягче. На фикс. (Vg, Va<<plateau)
    # vk=10 даёт больший Ia (модификатор быстрее насыщается до 1).
    p_sharp = _EL34_MOD_KNEE.model_copy(update={'vk': 10.0})
    p_smooth = _EL34_MOD_KNEE.model_copy(update={'vk': 200.0})
    ia_sharp = koren_modified_knee_pentode_ia(vg=-10.0, va=100.0, params=p_sharp)
    ia_smooth = koren_modified_knee_pentode_ia(vg=-10.0, va=100.0, params=p_smooth)
    assert ia_sharp > ia_smooth


def test_modified_knee_pentode_cutoff_returns_negligible() -> None:
    ia = koren_modified_knee_pentode_ia(vg=-50.0, va=250.0, params=_EL34_MOD_KNEE)
    assert ia < 0.01


# ============================== T182: Modified Koren-triode (cutoff) ==============================


_300B_LIKE = KorenModifiedCutoffTriodeParams(
    mu=4, ex=1.4, kg1=1500, kp=800, kvb=200, vc_off=-50.0, vs_off=5.0
)


def test_modified_cutoff_triode_at_vc_off_sigmoid_half() -> None:
    # Vg = vc_off → sigmoid(0) = 0.5 → Ia = canonical * 0.5.
    # Hand-calc: 106.71 mA.
    ia = koren_modified_cutoff_triode_ia(vg=-50.0, va=350.0, params=_300B_LIKE)
    assert ia == pytest.approx(106.71, rel=2e-2)


def test_modified_cutoff_triode_mid_region_sigmoid_one() -> None:
    # Vg ≫ vc_off (Vg=-30 > -50) → sigmoid → 1 → Ia ≈ canonical.
    # Hand-calc: 380.93 mA.
    ia = koren_modified_cutoff_triode_ia(vg=-30.0, va=350.0, params=_300B_LIKE)
    assert ia == pytest.approx(380.93, rel=2e-2)


def test_modified_cutoff_triode_deep_cutoff_sigmoid_zero() -> None:
    # Vg ≪ vc_off (Vg=-80 < -50) → sigmoid → ~0 → Ia → ~0.
    # Hand-calc: 0.056 mA (vs canonical 22.66 mA — sharp shutdown).
    ia = koren_modified_cutoff_triode_ia(vg=-80.0, va=350.0, params=_300B_LIKE)
    assert ia < 0.1  # ≪ canonical 22.66; настоящий shutdown


def test_modified_cutoff_triode_monotonic_in_va() -> None:
    ias = [
        koren_modified_cutoff_triode_ia(vg=-30.0, va=v, params=_300B_LIKE)
        for v in (100, 200, 300, 400)
    ]
    assert ias[0] < ias[1] < ias[2] < ias[3]


def test_modified_cutoff_triode_monotonic_in_vg() -> None:
    ias = [
        koren_modified_cutoff_triode_ia(vg=v, va=350.0, params=_300B_LIKE)
        for v in (-60.0, -40.0, -20.0, -10.0)
    ]
    assert ias[0] < ias[1] < ias[2] < ias[3]


def test_modified_cutoff_triode_smaller_vs_off_gives_sharper_cutoff() -> None:
    # Sharper sigmoid → deeper-cutoff Ia уменьшается быстрее.
    p_sharp = _300B_LIKE.model_copy(update={'vs_off': 1.0})
    p_smooth = _300B_LIKE.model_copy(update={'vs_off': 15.0})
    ia_sharp = koren_modified_cutoff_triode_ia(vg=-55.0, va=350.0, params=p_sharp)
    ia_smooth = koren_modified_cutoff_triode_ia(vg=-55.0, va=350.0, params=p_smooth)
    assert ia_sharp < ia_smooth  # sharper модификатор сильнее давит при Vg < vc_off


def test_modified_cutoff_triode_vct_still_works() -> None:
    # `vct` остаётся в схеме (хотя CLI запретит использование с этим
    # variant'ом — A-W1). Проверяем что формула учитывает vct корректно.
    p0 = _300B_LIKE
    p1 = _300B_LIKE.model_copy(update={'vct': 0.5})
    ia0 = koren_modified_cutoff_triode_ia(vg=-30.0, va=350.0, params=p0)
    ia1 = koren_modified_cutoff_triode_ia(vg=-30.0, va=350.0, params=p1)
    # vct смещает Vg → larger Ia.
    assert ia1 > ia0


def test_modified_cutoff_triode_handles_extreme_sigmoid_no_overflow() -> None:
    # Очень глубокий cutoff: (Vg - Vc_off)/Vs_off → большое отрицательное;
    # формула должна возвращать finite значение, не NaN/inf.
    ia = koren_modified_cutoff_triode_ia(vg=-150.0, va=300.0, params=_300B_LIKE)
    assert ia == 0.0  # глубокий cutoff — sigmoid_arg ниже SOFTPLUS_DEEP_CUTOFF


# ============================== T184: Reefman pentode ==============================


# EL34-like Reefman params (KG1=325 — half of Ayumi convention 650).
_EL34_REEFMAN = KorenReefmanPentodeParams(
    mu=11, ex=1.35, kg1=325, kg2=2250, kp=60, kvb=24, screen_v=250
)


def test_reefman_pentode_el34_at_known_point() -> None:
    # Hand-calc: Vg=-12.2, Va=250 → 113.44 mA (Reefman convention, KG1=325).
    ia = koren_reefman_pentode_ia(vg=-12.2, va=250.0, params=_EL34_REEFMAN)
    assert ia == pytest.approx(113.44, rel=1e-2)


def test_reefman_pentode_near_identical_to_canonical_at_high_vg2() -> None:
    # Для Vg2=250 ≫ √KVB=√24≈4.9, Reefman E1 ≈ canonical E1.
    # Reefman convention KG1=325, canonical KG1=650 (2× factor).
    ia_reef = koren_reefman_pentode_ia(vg=-12.2, va=250.0, params=_EL34_REEFMAN)
    ia_canon = ayumi_pentode_ia(
        vg=-12.2,
        va=250.0,
        params=AyumiPentodeParams(
            mu=11, ex=1.35, kg1=650, kg2=4500, kp=60, kvb=24, screen_v=250
        ),
    )
    # При rendered identity Reefman ratio ~ 1.0002 → < 0.5% delta.
    assert abs(ia_reef - ia_canon) / ia_canon < 5e-3


def test_reefman_pentode_monotonic_in_va() -> None:
    ias = [
        koren_reefman_pentode_ia(vg=-10.0, va=v, params=_EL34_REEFMAN)
        for v in (50, 100, 200, 400)
    ]
    assert ias[0] < ias[1] < ias[2] < ias[3]


def test_reefman_pentode_monotonic_in_vg() -> None:
    ias = [
        koren_reefman_pentode_ia(vg=v, va=250.0, params=_EL34_REEFMAN)
        for v in (-20.0, -15.0, -10.0, -5.0)
    ]
    assert ias[0] < ias[1] < ias[2] < ias[3]


def test_reefman_pentode_cutoff_returns_negligible() -> None:
    ia = koren_reefman_pentode_ia(vg=-50.0, va=250.0, params=_EL34_REEFMAN)
    assert ia < 0.01


def test_reefman_pentode_ig2_independent_of_va() -> None:
    # Ig2 (Eq 17) не зависит от Va — vacuum-tube pentode-model property.
    ig2_a = koren_reefman_pentode_ig2(vg=-5.0, va=100.0, params=_EL34_REEFMAN)
    ig2_b = koren_reefman_pentode_ig2(vg=-5.0, va=500.0, params=_EL34_REEFMAN)
    assert ig2_a == pytest.approx(ig2_b, rel=1e-9)


def test_reefman_pentode_ig2_monotonic_in_vg() -> None:
    ig2s = [
        koren_reefman_pentode_ig2(vg=v, va=250.0, params=_EL34_REEFMAN)
        for v in (-15.0, -10.0, -5.0, 0.0)
    ]
    assert ig2s[0] < ig2s[1] < ig2s[2] < ig2s[3]


def test_reefman_pentode_atan_plateau() -> None:
    ia_far = koren_reefman_pentode_ia(vg=-10.0, va=2000.0, params=_EL34_REEFMAN)
    ia_close = koren_reefman_pentode_ia(vg=-10.0, va=400.0, params=_EL34_REEFMAN)
    assert ia_far / ia_close < 1.10


# ============================== T186: Derk pentode ==============================


_EL34_DERK = KorenDerkPentodeParams(
    mu=11, ex=1.35, kg1=325, kg2=2250, kp=60, kvb=24, screen_v=250,
    alpha_s=1.0, beta=0.05, a_penetration=0.001,
)


def test_derk_pentode_zero_va_returns_zero_by_construction() -> None:
    # Eq 27 constraint guarantees I_a(V_a=0) = 0.
    ia = koren_derk_pentode_ia(vg=-12.2, va=0.0, params=_EL34_DERK)
    assert ia == pytest.approx(0.0, abs=1e-9)


def test_derk_pentode_at_known_point() -> None:
    # Hand-calc reference: Vg=-12.2, Va=250 → Ia=80.15 mA.
    ia = koren_derk_pentode_ia(vg=-12.2, va=250.0, params=_EL34_DERK)
    assert ia == pytest.approx(80.15, rel=2e-2)


def test_derk_pentode_monotonic_in_va() -> None:
    ias = [
        koren_derk_pentode_ia(vg=-10.0, va=v, params=_EL34_DERK)
        for v in (50, 100, 200, 400)
    ]
    assert ias[0] < ias[1] < ias[2] < ias[3]


def test_derk_pentode_monotonic_in_vg() -> None:
    ias = [
        koren_derk_pentode_ia(vg=v, va=250.0, params=_EL34_DERK)
        for v in (-20.0, -15.0, -10.0, -5.0)
    ]
    assert ias[0] < ias[1] < ias[2] < ias[3]


def test_derk_pentode_ig2_depends_on_va() -> None:
    # Eq 23: Ig2 has 1/(1+β·Va) term → должно зависеть от Va.
    # Это отличает Derk от canonical/Reefman Ig2.
    ig2_low = koren_derk_pentode_ig2(vg=-5.0, va=50.0, params=_EL34_DERK)
    ig2_high = koren_derk_pentode_ig2(vg=-5.0, va=500.0, params=_EL34_DERK)
    assert ig2_low > ig2_high  # При знизком Va, knee_factor больше → больше Ig2.


def test_derk_pentode_alpha_derived_correctly() -> None:
    # α = 1 - (kg1/kg2)(1+α_s); для EL34_DERK kg1=325, kg2=2250, α_s=1.0:
    # α = 1 - (325/2250)(2) = 1 - 0.2889 = 0.7111.
    # Не публичный, но через хорошо проверяемое поведение: при α_s=0,
    # α=1-kg1/kg2 = 0.8556 → Ia(Va=0) всё ещё 0 (constraint design).
    p_alpha_s_zero = _EL34_DERK.model_copy(update={'alpha_s': 0.0})
    ia_zero = koren_derk_pentode_ia(vg=-10.0, va=0.0, params=p_alpha_s_zero)
    assert ia_zero == pytest.approx(0.0, abs=1e-9)


def test_derk_pentode_anode_penetration_increases_plateau() -> None:
    # A·Va/KG1 term — при больших Va даёт линейный рост Ia.
    p_zero_a = _EL34_DERK.model_copy(update={'a_penetration': 0.0})
    p_higher_a = _EL34_DERK.model_copy(update={'a_penetration': 0.01})
    ia_zero = koren_derk_pentode_ia(vg=-5.0, va=400.0, params=p_zero_a)
    ia_high = koren_derk_pentode_ia(vg=-5.0, va=400.0, params=p_higher_a)
    assert ia_high > ia_zero


def test_derk_pentode_smaller_beta_gives_wider_knee() -> None:
    # β=0.01 → 1/(1+0.01·100)=0.5 при Va=100 (wider knee).
    # β=0.1 → 0.091 при Va=100 (sharper knee).
    p_wide = _EL34_DERK.model_copy(update={'beta': 0.01})
    p_sharp = _EL34_DERK.model_copy(update={'beta': 0.1})
    ia_wide = koren_derk_pentode_ia(vg=-5.0, va=50.0, params=p_wide)
    ia_sharp = koren_derk_pentode_ia(vg=-5.0, va=50.0, params=p_sharp)
    # Sharper knee при том же Va даёт больший Ia (more "saturation" at knee).
    assert ia_sharp > ia_wide


def test_derk_pentode_cutoff_returns_negligible() -> None:
    ia = koren_derk_pentode_ia(vg=-50.0, va=250.0, params=_EL34_DERK)
    assert ia < 0.01
