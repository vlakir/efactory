"""
Tube-curve-fitting: scipy.optimize.curve_fit с multi-start (T031 Phase 1).

A-C1 (Analyze 🔴): `curve_fit(..., bounds=..., method='trf')` явно.
LM (`method='lm'`) не поддерживает bounds — silent error.

A-C2 (Analyze 🔴): multi-start с `numpy.random.default_rng(seed)`;
default seed 42 для unit-tests determinism.

Возвращаемые KG1/KG2 — в **ngspice convention** (т.е. как в built-in
`.lib` файлах, например KG1=1060 для 12AX7). Pipeline далее в mA;
конвертация .lib → mA делается ×1000 (см. `_formulas.py`).
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

import numpy as np
import scipy.optimize as scipy_opt
from numpy.random import default_rng

from domain.tube_fitting._bounds import (
    AYUMI_PENTODE_BOUNDS,
    AYUMI_PENTODE_TYPICAL,
    KOREN_TRIODE_BOUNDS,
    KOREN_TRIODE_TYPICAL,
)
from domain.tube_fitting._formulas import SOFTPLUS_DEEP_CUTOFF, SOFTPLUS_LARGE_ARG
from domain.tube_fitting._params import (
    AyumiPentodeParams,
    FitResult,
    IVDataset,
    KorenTriodeParams,
)

if TYPE_CHECKING:
    from numpy.typing import NDArray


class FitFailedError(RuntimeError):
    """Все multi-start попытки fitter'а не сошлись."""


# ============================== vectorized forward Ia ==============================


def _koren_triode_ia_vec(
    vgs: NDArray[np.float64],
    vas: NDArray[np.float64],
    mu: float,
    ex: float,
    kg1: float,
    kp: float,
    kvb: float,
    vct: float = 0.0,
) -> NDArray[np.float64]:
    """Vectorized Koren triode Ia (mA). Совпадает с `koren_triode_ia` поточечно."""
    plate_norm = np.sqrt(kvb + vas * vas)
    arg = kp * (1.0 / mu + (vgs + vct) / plate_norm)
    arg_clipped = np.clip(arg, SOFTPLUS_DEEP_CUTOFF, SOFTPLUS_LARGE_ARG)
    softplus = np.where(arg > SOFTPLUS_LARGE_ARG, arg, np.log1p(np.exp(arg_clipped)))
    softplus = np.where(arg < SOFTPLUS_DEEP_CUTOFF, 0.0, softplus)
    e1 = (vas / kp) * softplus
    e1_pos = np.maximum(e1, 1e-30)
    ia_a = 2.0 * (e1_pos**ex) / kg1
    ia_a = np.where(e1 <= 0.0, 0.0, ia_a)
    return ia_a * 1000.0  # → mA


def _ayumi_pentode_ia_vec(
    vgs: NDArray[np.float64],
    vas: NDArray[np.float64],
    mu: float,
    ex: float,
    kg1: float,
    kp: float,
    kvb: float,
    screen_v: float,
) -> NDArray[np.float64]:
    """Vectorized Ayumi pentode plate-current Ia (mA)."""
    arg = kp * (1.0 / mu + vgs / screen_v)
    arg_clipped = np.clip(arg, SOFTPLUS_DEEP_CUTOFF, SOFTPLUS_LARGE_ARG)
    softplus = np.where(arg > SOFTPLUS_LARGE_ARG, arg, np.log1p(np.exp(arg_clipped)))
    softplus = np.where(arg < SOFTPLUS_DEEP_CUTOFF, 0.0, softplus)
    e1 = (screen_v / kp) * softplus
    e1_pos = np.maximum(e1, 1e-30)
    ia_a = (2.0 * (e1_pos**ex) / kg1) * np.arctan(vas / kvb)
    ia_a = np.where(e1 <= 0.0, 0.0, ia_a)
    return ia_a * 1000.0


# ============================== fitter — Koren triode ==============================


_TRIODE_FIT_KEYS = ('mu', 'ex', 'kg1', 'kp', 'kvb')
_TRIODE_FIT_KEYS_WITH_VCT = (*_TRIODE_FIT_KEYS, 'vct')


def _triode_initial_guesses(
    n_starts: int,
    rng: np.random.Generator,
    *,
    include_vct: bool,
    seed_from: KorenTriodeParams | None,
) -> list[list[float]]:
    """
    Multi-start initial guesses (≥ n_starts).

    Структура: [typical] + ([seed_from] если задан) + N randomized.
    Random — log-uniform для KG1/KP/KVB, linear-uniform для MU/EX/VCT.
    """
    keys = _TRIODE_FIT_KEYS_WITH_VCT if include_vct else _TRIODE_FIT_KEYS

    def _from_dict(d: dict[str, float]) -> list[float]:
        return [d[k] for k in keys]

    starts: list[list[float]] = [_from_dict(KOREN_TRIODE_TYPICAL)]
    if seed_from is not None:
        seed_dict = seed_from.model_dump()
        seed_dict.setdefault('vct', 0.5 if include_vct else 0.0)
        starts.append(_from_dict(seed_dict))

    while len(starts) < n_starts:
        guess: list[float] = []
        for k in keys:
            lo, hi = KOREN_TRIODE_BOUNDS[k]
            if k in ('kg1', 'kp', 'kvb'):
                guess.append(float(np.exp(rng.uniform(np.log(lo), np.log(hi)))))
            else:
                guess.append(float(rng.uniform(lo, hi)))
        starts.append(guess)
    return starts


def fit_koren_triode(
    ds: IVDataset,
    *,
    include_vct: bool = False,
    n_starts: int = 5,
    seed: int = 42,
    seed_from: KorenTriodeParams | None = None,
    max_nfev: int = 5000,
) -> FitResult:
    """
    Fit Koren triode формулы по IV-датасету.

    Multi-start (A-C2): `n_starts` initial guesses (типовой + опц.
    seed_from + randomized в bounds через seeded RNG); выбирается start
    с минимальным RMS residual.
    """
    if ds.tube_type != 'triode':
        msg = f"fit_koren_triode expects tube_type='triode', got '{ds.tube_type}'"
        raise ValueError(msg)
    if n_starts < 1:
        msg = f'n_starts must be ≥ 1, got {n_starts}'
        raise ValueError(msg)

    vgs_t, vas_t, ias_t = ds.flatten()
    vgs = np.asarray(vgs_t, dtype=np.float64)
    vas = np.asarray(vas_t, dtype=np.float64)
    ias = np.asarray(ias_t, dtype=np.float64)
    n_points = len(ias)

    keys = _TRIODE_FIT_KEYS_WITH_VCT if include_vct else _TRIODE_FIT_KEYS
    lower = np.asarray([KOREN_TRIODE_BOUNDS[k][0] for k in keys], dtype=np.float64)
    upper = np.asarray([KOREN_TRIODE_BOUNDS[k][1] for k in keys], dtype=np.float64)

    def _callback(x: NDArray[np.float64], *theta: float) -> NDArray[np.float64]:
        # x.shape = (2, n_points): [vgs, vas].
        if include_vct:
            mu, ex, kg1, kp, kvb, vct = theta
        else:
            mu, ex, kg1, kp, kvb = theta
            vct = 0.0
        return _koren_triode_ia_vec(x[0], x[1], mu, ex, kg1, kp, kvb, vct=vct)

    xdata = np.vstack([vgs, vas])

    rng = default_rng(seed)
    starts = _triode_initial_guesses(
        n_starts, rng, include_vct=include_vct, seed_from=seed_from
    )

    best: tuple[float, list[float], NDArray[np.float64], int] | None = None
    for i, p0 in enumerate(starts):
        # Clip p0 to bounds (избегаем "x0 infeasible" если seed_from
        # из старой spec'и с params outside текущих bounds).
        p0_clipped = list(np.clip(p0, lower, upper))
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', scipy_opt.OptimizeWarning)
                popt, pcov = scipy_opt.curve_fit(
                    _callback,
                    xdata,
                    ias,
                    p0=p0_clipped,
                    bounds=(lower, upper),
                    method='trf',  # A-C1
                    max_nfev=max_nfev,
                )
        except (RuntimeError, scipy_opt.OptimizeWarning, ValueError):
            # start не сошёлся → пропускаем.
            continue
        residuals = ias - _callback(xdata, *popt)
        rms = float(np.sqrt(np.mean(residuals * residuals)))
        if best is None or rms < best[0]:
            best = (rms, list(popt), pcov, i)

    if best is None:
        msg = f'All {n_starts} multi-start fits failed for {ds.tube_name}'
        raise FitFailedError(msg)

    rms_best, popt_best, pcov_best, best_idx = best
    fit_dict = dict(zip(keys, popt_best, strict=True))
    if not include_vct:
        fit_dict['vct'] = None  # type: ignore[assignment]
    params = KorenTriodeParams(**fit_dict)  # type: ignore[arg-type]
    stderr = _diag_stderr(pcov_best, keys)

    return FitResult(
        params=params,
        rms_residual_ma=rms_best,
        per_param_stderr=stderr,
        n_points=n_points,
        converged=True,
        n_starts_tried=len(starts),
        best_start_index=best_idx,
    )


# ============================== fitter — Ayumi pentode ==============================


_PENTODE_FIT_KEYS = ('mu', 'ex', 'kg1', 'kg2', 'kp', 'kvb')


def _pentode_initial_guesses(
    n_starts: int,
    rng: np.random.Generator,
    *,
    seed_from: AyumiPentodeParams | None,
) -> list[list[float]]:
    def _from_dict(d: dict[str, float]) -> list[float]:
        return [d[k] for k in _PENTODE_FIT_KEYS]

    starts: list[list[float]] = [_from_dict(AYUMI_PENTODE_TYPICAL)]
    if seed_from is not None:
        starts.append(_from_dict(seed_from.model_dump()))

    while len(starts) < n_starts:
        guess: list[float] = []
        for k in _PENTODE_FIT_KEYS:
            lo, hi = AYUMI_PENTODE_BOUNDS[k]
            if k in ('kg1', 'kg2', 'kp', 'kvb'):
                guess.append(float(np.exp(rng.uniform(np.log(lo), np.log(hi)))))
            else:
                guess.append(float(rng.uniform(lo, hi)))
        starts.append(guess)
    return starts


def fit_ayumi_pentode(
    ds: IVDataset,
    *,
    n_starts: int = 5,
    seed: int = 42,
    seed_from: AyumiPentodeParams | None = None,
    max_nfev: int = 5000,
) -> FitResult:
    """
    Fit Ayumi-style pentode (Koren-pentode form) по IV-датасету.

    `screen_voltage_v` берётся из `ds`, **не** fit'ится — это known input.
    Fit'ятся 6 параметров: mu, ex, kg1, kg2, kp, kvb.

    Замечание про identifiability: KG2 входит **только** в формулу Ig2
    (screen current), не в Ia. IVDataset содержит только Ia точки → fit
    KG2 не identifiable; scipy сходится в произвольное значение в bounds,
    `per_param_stderr['kg2']` отразит это (large / inf). Это known
    limitation: для production KG2 либо передаётся через `seed_from`,
    либо в .lib пишется typical ratio (KG2 ≈ 5·KG1) post-fit (Phase 2
    .lib writer). Round-trip tests на KG2 не assert'им.
    """
    if ds.tube_type != 'pentode':
        msg = f"fit_ayumi_pentode expects tube_type='pentode', got '{ds.tube_type}'"
        raise ValueError(msg)
    if ds.screen_voltage_v is None:
        msg = 'fit_ayumi_pentode requires screen_voltage_v'
        raise ValueError(msg)
    if n_starts < 1:
        msg = f'n_starts must be ≥ 1, got {n_starts}'
        raise ValueError(msg)

    screen_v = ds.screen_voltage_v
    vgs_t, vas_t, ias_t = ds.flatten()
    vgs = np.asarray(vgs_t, dtype=np.float64)
    vas = np.asarray(vas_t, dtype=np.float64)
    ias = np.asarray(ias_t, dtype=np.float64)
    n_points = len(ias)

    keys = _PENTODE_FIT_KEYS
    lower = np.asarray([AYUMI_PENTODE_BOUNDS[k][0] for k in keys], dtype=np.float64)
    upper = np.asarray([AYUMI_PENTODE_BOUNDS[k][1] for k in keys], dtype=np.float64)

    def _callback(x: NDArray[np.float64], *theta: float) -> NDArray[np.float64]:
        # KG2 fit'ится но не identifiable из Ia (см. docstring fit_ayumi_pentode).
        mu, ex, kg1, _kg2, kp, kvb = theta
        return _ayumi_pentode_ia_vec(x[0], x[1], mu, ex, kg1, kp, kvb, screen_v)

    xdata = np.vstack([vgs, vas])

    rng = default_rng(seed)
    starts = _pentode_initial_guesses(n_starts, rng, seed_from=seed_from)

    best: tuple[float, list[float], NDArray[np.float64], int] | None = None
    for i, p0 in enumerate(starts):
        p0_clipped = list(np.clip(p0, lower, upper))
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', scipy_opt.OptimizeWarning)
                popt, pcov = scipy_opt.curve_fit(
                    _callback,
                    xdata,
                    ias,
                    p0=p0_clipped,
                    bounds=(lower, upper),
                    method='trf',
                    max_nfev=max_nfev,
                )
        except (RuntimeError, scipy_opt.OptimizeWarning, ValueError):
            continue
        residuals = ias - _callback(xdata, *popt)
        rms = float(np.sqrt(np.mean(residuals * residuals)))
        if best is None or rms < best[0]:
            best = (rms, list(popt), pcov, i)

    if best is None:
        msg = f'All {n_starts} multi-start fits failed for {ds.tube_name}'
        raise FitFailedError(msg)

    rms_best, popt_best, pcov_best, best_idx = best
    fit_dict = dict(zip(keys, popt_best, strict=True))
    fit_dict['screen_v'] = screen_v
    params = AyumiPentodeParams(**fit_dict)  # type: ignore[arg-type]
    stderr = _diag_stderr(pcov_best, keys)

    return FitResult(
        params=params,
        rms_residual_ma=rms_best,
        per_param_stderr=stderr,
        n_points=n_points,
        converged=True,
        n_starts_tried=len(starts),
        best_start_index=best_idx,
    )


# ============================== shared helpers ==============================


def _diag_stderr(pcov: NDArray[np.float64], keys: tuple[str, ...]) -> dict[str, float]:
    """Stderr per parameter из covariance diagonal; ill-conditioned → inf."""
    diag = np.diag(pcov)
    stderr_arr = np.where(diag >= 0, np.sqrt(np.abs(diag)), np.inf)
    return dict(zip(keys, (float(s) for s in stderr_arr), strict=True))
