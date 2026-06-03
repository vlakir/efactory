"""Tube-fitting params + IVDataset validation (T031 Phase 1)."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from domain.tube_fitting import (
    AyumiPentodeParams,
    CurveData,
    FitResult,
    IVDataset,
    IVPoint,
    KorenTriodeParams,
)

# ============================== KorenTriodeParams ==============================


def test_koren_triode_params_round_trip() -> None:
    # 12AX7 known values.
    p = KorenTriodeParams(mu=100, ex=1.4, kg1=1060, kp=600, kvb=300)
    assert p.mu == 100
    assert p.vct is None


def test_koren_triode_params_with_vct() -> None:
    p = KorenTriodeParams(mu=100, ex=1.4, kg1=1060, kp=600, kvb=300, vct=0.5)
    assert p.vct == 0.5


def test_koren_triode_params_frozen() -> None:
    p = KorenTriodeParams(mu=100, ex=1.4, kg1=1060, kp=600, kvb=300)
    with pytest.raises(ValidationError):
        p.mu = 50  # type: ignore[misc]


def test_koren_triode_params_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        KorenTriodeParams(mu=100, ex=1.4, kg1=1060, kp=600, kvb=300, junk=1.0)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    'field,value',
    [
        ('mu', 0),
        ('mu', -10),
        ('ex', 0.5),
        ('ex', 3.5),
        ('kg1', 0),
        ('kp', -1),
        ('kvb', 0),
    ],
)
def test_koren_triode_params_bounds_violation(field: str, value: float) -> None:
    base = {'mu': 100, 'ex': 1.4, 'kg1': 1060, 'kp': 600, 'kvb': 300}
    base[field] = value
    with pytest.raises(ValidationError):
        KorenTriodeParams(**base)  # type: ignore[arg-type]


def test_koren_triode_vct_bounds_violation() -> None:
    with pytest.raises(ValidationError):
        KorenTriodeParams(mu=100, ex=1.4, kg1=1060, kp=600, kvb=300, vct=10.0)
    with pytest.raises(ValidationError):
        KorenTriodeParams(mu=100, ex=1.4, kg1=1060, kp=600, kvb=300, vct=-0.5)


# ============================== AyumiPentodeParams ==============================


def test_ayumi_pentode_params_round_trip() -> None:
    # EL34 Koren-pentode known values.
    p = AyumiPentodeParams(
        mu=11, ex=1.35, kg1=650, kg2=4500, kp=60, kvb=24, screen_v=250
    )
    assert p.screen_v == 250


def test_ayumi_pentode_params_frozen() -> None:
    p = AyumiPentodeParams(
        mu=11, ex=1.35, kg1=650, kg2=4500, kp=60, kvb=24, screen_v=250
    )
    with pytest.raises(ValidationError):
        p.kg2 = 5000  # type: ignore[misc]


@pytest.mark.parametrize(
    'field,value',
    [
        ('mu', 0),
        ('ex', 1.0),
        ('kg1', 0),
        ('kg2', -1),
        ('kp', 0),
        ('kvb', 0),
        ('screen_v', 0),
        ('screen_v', -100),
    ],
)
def test_ayumi_pentode_params_bounds_violation(field: str, value: float) -> None:
    base = {
        'mu': 11,
        'ex': 1.35,
        'kg1': 650,
        'kg2': 4500,
        'kp': 60,
        'kvb': 24,
        'screen_v': 250,
    }
    base[field] = value
    with pytest.raises(ValidationError):
        AyumiPentodeParams(**base)  # type: ignore[arg-type]


# ============================== IVPoint / CurveData ==============================


def test_iv_point_round_trip() -> None:
    p = IVPoint(vg=-2.0, va=250.0, ia=1.0)
    assert p.ia == 1.0


def test_iv_point_negative_ia_rejected() -> None:
    with pytest.raises(ValidationError):
        IVPoint(vg=-2.0, va=250.0, ia=-0.1)


def test_iv_point_zero_va_rejected() -> None:
    # Va=0 → не используется (anode disconnected); reject.
    with pytest.raises(ValidationError):
        IVPoint(vg=-2.0, va=0.0, ia=1.0)


def test_curve_data_non_empty_points() -> None:
    with pytest.raises(ValidationError):
        CurveData(vg=-2.0, points=())


def test_curve_data_va_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        CurveData(vg=-2.0, points=((0.0, 1.0),))


def test_curve_data_ia_non_negative() -> None:
    with pytest.raises(ValidationError):
        CurveData(vg=-2.0, points=((250.0, -1.0),))


def test_curve_data_zero_ia_allowed() -> None:
    # Cutoff edge — Ia=0 разрешён.
    c = CurveData(vg=-30.0, points=((250.0, 0.0),))
    assert c.points[0][1] == 0.0


# ============================== IVDataset ==============================


def _make_pentode_dataset() -> IVDataset:
    return IVDataset(
        tube_name='EL34',
        tube_type='pentode',
        source='Mullard 1962',
        date_extracted=date(2026, 6, 3),
        curves=(
            CurveData(vg=-10.0, points=((100.0, 75.0), (300.0, 145.0))),
            CurveData(vg=-15.0, points=((100.0, 15.0), (300.0, 75.0))),
        ),
        screen_voltage_v=250.0,
    )


def _make_triode_dataset() -> IVDataset:
    return IVDataset(
        tube_name='12AX7',
        tube_type='triode',
        source='hand-fixture',
        date_extracted=date(2026, 6, 3),
        curves=(CurveData(vg=-2.0, points=((250.0, 1.0),)),),
    )


def test_iv_dataset_pentode_round_trip() -> None:
    ds = _make_pentode_dataset()
    assert ds.tube_type == 'pentode'
    assert ds.screen_voltage_v == 250.0
    assert len(ds.curves) == 2


def test_iv_dataset_triode_round_trip() -> None:
    ds = _make_triode_dataset()
    assert ds.tube_type == 'triode'
    assert ds.screen_voltage_v is None


def test_iv_dataset_empty_curves_rejected() -> None:
    with pytest.raises(ValidationError):
        IVDataset(
            tube_name='X',
            tube_type='triode',
            source='x',
            date_extracted=date(2026, 6, 3),
            curves=(),
        )


def test_iv_dataset_pentode_without_screen_voltage_rejected() -> None:
    with pytest.raises(ValidationError):
        IVDataset(
            tube_name='X',
            tube_type='pentode',
            source='x',
            date_extracted=date(2026, 6, 3),
            curves=(CurveData(vg=-10.0, points=((250.0, 100.0),)),),
        )


def test_iv_dataset_triode_with_screen_voltage_rejected() -> None:
    with pytest.raises(ValidationError):
        IVDataset(
            tube_name='X',
            tube_type='triode',
            source='x',
            date_extracted=date(2026, 6, 3),
            curves=(CurveData(vg=-2.0, points=((250.0, 1.0),)),),
            screen_voltage_v=250.0,
        )


def test_iv_dataset_flatten_pentode() -> None:
    ds = _make_pentode_dataset()
    vgs, vas, ias = ds.flatten()
    assert vgs == (-10.0, -10.0, -15.0, -15.0)
    assert vas == (100.0, 300.0, 100.0, 300.0)
    assert ias == (75.0, 145.0, 15.0, 75.0)


# ============================== FitResult ==============================


def test_fit_result_round_trip() -> None:
    p = KorenTriodeParams(mu=100, ex=1.4, kg1=1060, kp=600, kvb=300)
    fr = FitResult(
        params=p,
        rms_residual_ma=0.05,
        per_param_stderr={'mu': 0.5, 'ex': 0.01, 'kg1': 10, 'kp': 5, 'kvb': 3},
        n_points=40,
        converged=True,
        n_starts_tried=5,
        best_start_index=2,
    )
    assert fr.converged is True
    assert fr.n_points == 40


def test_fit_result_negative_residual_rejected() -> None:
    p = KorenTriodeParams(mu=100, ex=1.4, kg1=1060, kp=600, kvb=300)
    with pytest.raises(ValidationError):
        FitResult(
            params=p,
            rms_residual_ma=-0.05,
            per_param_stderr={},
            n_points=10,
            converged=True,
            n_starts_tried=1,
            best_start_index=0,
        )


def test_fit_result_zero_n_points_rejected() -> None:
    p = KorenTriodeParams(mu=100, ex=1.4, kg1=1060, kp=600, kvb=300)
    with pytest.raises(ValidationError):
        FitResult(
            params=p,
            rms_residual_ma=0.05,
            per_param_stderr={},
            n_points=0,
            converged=True,
            n_starts_tried=1,
            best_start_index=0,
        )
