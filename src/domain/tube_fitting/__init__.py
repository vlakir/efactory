"""Tube-curve-fitting (T031): Koren triode / Ayumi pentode forward models + fitter."""

from __future__ import annotations

from domain.tube_fitting._fitter import (
    FitFailedError,
    fit_ayumi_pentode,
    fit_koren_triode,
)
from domain.tube_fitting._formulas import ayumi_pentode_ia, koren_triode_ia
from domain.tube_fitting._params import (
    AyumiPentodeParams,
    CurveData,
    FitResult,
    IVDataset,
    IVPoint,
    KorenTriodeParams,
    TubeType,
)

__all__ = [
    'AyumiPentodeParams',
    'CurveData',
    'FitFailedError',
    'FitResult',
    'IVDataset',
    'IVPoint',
    'KorenTriodeParams',
    'TubeType',
    'ayumi_pentode_ia',
    'fit_ayumi_pentode',
    'fit_koren_triode',
    'koren_triode_ia',
]
