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
    KorenModifiedCutoffTriodeParams,
    KorenModifiedKneePentodeParams,
    KorenTriodeParams,
    ayumi_pentode_ia,
    koren_modified_cutoff_triode_ia,
    koren_modified_knee_pentode_ia,
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
