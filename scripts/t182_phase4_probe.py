"""T182 Phase 4 acceptance probe — EL34 (SC#2) + 300B (SC#4) + 6П13С (SC#6).

Не unit-test: standalone runner, генерирующий JSON metrics для
ручного code review + markdown summary. Запуск:

    PYTHONPATH=src uv run python scripts/t182_phase4_probe.py

Артефакт: `specs/T182-koren-modified-knee/phase-4-results.json`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from adapters.outbound.spice_models.tube_json import FilesystemTubeIVRepository
from domain.tube_fitting import (
    AyumiPentodeParams,
    IVDataset,
    KorenModifiedCutoffTriodeParams,
    KorenModifiedKneePentodeParams,
    KorenTriodeParams,
    ayumi_pentode_ia,
    fit_ayumi_pentode,
    fit_koren_modified_cutoff_triode,
    fit_koren_modified_knee_pentode,
    fit_koren_triode,
    koren_modified_cutoff_triode_ia,
    koren_modified_knee_pentode_ia,
    koren_triode_ia,
)

_FIXTURES = (
    Path(__file__).parent.parent / 'specs' / 'T182-koren-modified-knee' / 'fixtures'
)
_RESULTS = (
    Path(__file__).parent.parent
    / 'specs' / 'T182-koren-modified-knee' / 'phase-4-results.json'
)


def _load(filename: str) -> IVDataset:
    repo = FilesystemTubeIVRepository()
    return repo.load_iv_dataset(_FIXTURES / filename)


def _errors_pentode(
    ds: IVDataset,
    params: AyumiPentodeParams | KorenModifiedKneePentodeParams,
) -> tuple[list[float], list[tuple[float, float, float, float]]]:
    """Возвращает (per-point relative errors, list of (vg, va, ia_obs, ia_pred))."""
    is_modified = isinstance(params, KorenModifiedKneePentodeParams)
    errs: list[float] = []
    rows: list[tuple[float, float, float, float]] = []
    for curve in ds.curves:
        for va, ia_obs in curve.points:
            if is_modified:
                ia_pred = koren_modified_knee_pentode_ia(curve.vg, va, params)
            else:
                ia_pred = ayumi_pentode_ia(curve.vg, va, params)
            rel = abs(ia_pred - ia_obs) / ia_obs if ia_obs > 0 else 0.0
            errs.append(rel)
            rows.append((curve.vg, va, ia_obs, ia_pred))
    return errs, rows


def _errors_triode(
    ds: IVDataset,
    params: KorenTriodeParams | KorenModifiedCutoffTriodeParams,
) -> tuple[list[float], list[tuple[float, float, float, float]]]:
    is_modified = isinstance(params, KorenModifiedCutoffTriodeParams)
    errs: list[float] = []
    rows: list[tuple[float, float, float, float]] = []
    for curve in ds.curves:
        for va, ia_obs in curve.points:
            if is_modified:
                ia_pred = koren_modified_cutoff_triode_ia(curve.vg, va, params)
            else:
                ia_pred = koren_triode_ia(curve.vg, va, params)
            rel = abs(ia_pred - ia_obs) / ia_obs if ia_obs > 0 else 0.0
            errs.append(rel)
            rows.append((curve.vg, va, ia_obs, ia_pred))
    return errs, rows


def _region_stats(
    rows: list[tuple[float, float, float, float]],
    errs: list[float],
    *,
    region_name: str,
    predicate: 'callable[[float, float], bool]',  # noqa: F821
) -> dict[str, Any]:
    """Filter rows by predicate(vg, va), compute mean/max relative error."""
    sub_errs = [e for (vg, va, _io, _ip), e in zip(rows, errs, strict=True) if predicate(vg, va)]
    if not sub_errs:
        return {'region': region_name, 'n': 0, 'mean': None, 'max': None}
    return {
        'region': region_name,
        'n': len(sub_errs),
        'mean': float(np.mean(sub_errs)),
        'max': float(np.max(sub_errs)),
    }


def el34_acceptance() -> dict[str, Any]:
    """SC#2: knee error <30% mean / <40% max в knee region (Va<150, Vg∈[-10,-20])."""
    ds = _load('el34_mullard.json')
    fr_can = fit_ayumi_pentode(ds, n_starts=5, seed=42)
    assert isinstance(fr_can.params, AyumiPentodeParams)
    fr_mod = fit_koren_modified_knee_pentode(ds, n_starts=8, seed=42)
    assert isinstance(fr_mod.params, KorenModifiedKneePentodeParams)

    errs_can, rows_can = _errors_pentode(ds, fr_can.params)
    errs_mod, rows_mod = _errors_pentode(ds, fr_mod.params)

    knee_pred = lambda vg, va: va < 150 and -20 <= vg <= -10  # noqa: E731
    plateau_pred = lambda vg, va: va >= 200  # noqa: E731

    return {
        'tube': 'EL34 Mullard (36 points, Vg2=250V)',
        'n_points': len(errs_can),
        'canonical': {
            'params': fr_can.params.model_dump(),
            'rms_residual_ma': fr_can.rms_residual_ma,
            'knee': _region_stats(rows_can, errs_can, region_name='knee (Va<150, Vg∈[-10,-20])', predicate=knee_pred),
            'plateau': _region_stats(rows_can, errs_can, region_name='plateau (Va≥200)', predicate=plateau_pred),
            'overall': {'mean': float(np.mean(errs_can)), 'max': float(np.max(errs_can))},
        },
        'modified_knee': {
            'params': fr_mod.params.model_dump(),
            'rms_residual_ma': fr_mod.rms_residual_ma,
            'knee': _region_stats(rows_mod, errs_mod, region_name='knee (Va<150, Vg∈[-10,-20])', predicate=knee_pred),
            'plateau': _region_stats(rows_mod, errs_mod, region_name='plateau (Va≥200)', predicate=plateau_pred),
            'overall': {'mean': float(np.mean(errs_mod)), 'max': float(np.max(errs_mod))},
        },
        'sc2_pass': None,  # filled below
    }


def we_300b_acceptance() -> dict[str, Any]:
    """SC#4: strong-cutoff error <30% (Vg∈[-100,-60]); mid <15% (Vg∈[-30,-60])."""
    ds = _load('300b_we.json')
    fr_can = fit_koren_triode(ds, n_starts=5, seed=42)
    assert isinstance(fr_can.params, KorenTriodeParams)
    fr_mod = fit_koren_modified_cutoff_triode(ds, n_starts=8, seed=42)
    assert isinstance(fr_mod.params, KorenModifiedCutoffTriodeParams)

    errs_can, rows_can = _errors_triode(ds, fr_can.params)
    errs_mod, rows_mod = _errors_triode(ds, fr_mod.params)

    cutoff_pred = lambda vg, va: -100 <= vg <= -60  # noqa: E731
    mid_pred = lambda vg, va: -60 <= vg <= -30  # noqa: E731

    return {
        'tube': '300B Western Electric (31 points)',
        'n_points': len(errs_can),
        'canonical': {
            'params': fr_can.params.model_dump(),
            'rms_residual_ma': fr_can.rms_residual_ma,
            'cutoff': _region_stats(rows_can, errs_can, region_name='cutoff (Vg∈[-100,-60])', predicate=cutoff_pred),
            'mid': _region_stats(rows_can, errs_can, region_name='mid (Vg∈[-60,-30])', predicate=mid_pred),
            'overall': {'mean': float(np.mean(errs_can)), 'max': float(np.max(errs_can))},
        },
        'modified_cutoff': {
            'params': fr_mod.params.model_dump(),
            'rms_residual_ma': fr_mod.rms_residual_ma,
            'cutoff': _region_stats(rows_mod, errs_mod, region_name='cutoff (Vg∈[-100,-60])', predicate=cutoff_pred),
            'mid': _region_stats(rows_mod, errs_mod, region_name='mid (Vg∈[-60,-30])', predicate=mid_pred),
            'overall': {'mean': float(np.mean(errs_mod)), 'max': float(np.max(errs_mod))},
        },
        'sc4_pass': None,
    }


def t6p13s_acceptance() -> dict[str, Any]:
    """SC#6: 6П13С re-fit, check if modified-knee гонит KG1 ∈ [500, 10000], EX ∈ [1.0, 2.0]."""
    ds = _load('6p13s_iv.json')
    fr_can = fit_ayumi_pentode(ds, n_starts=5, seed=42)
    assert isinstance(fr_can.params, AyumiPentodeParams)
    fr_mod = fit_koren_modified_knee_pentode(ds, n_starts=8, seed=42)
    assert isinstance(fr_mod.params, KorenModifiedKneePentodeParams)

    errs_can, _ = _errors_pentode(ds, fr_can.params)
    errs_mod, _ = _errors_pentode(ds, fr_mod.params)

    return {
        'tube': '6П13С (USSR beam tetrode, Vg2=150V)',
        'n_points': len(errs_can),
        'canonical': {
            'params': fr_can.params.model_dump(),
            'rms_residual_ma': fr_can.rms_residual_ma,
            'mean_err': float(np.mean(errs_can)),
            'max_err': float(np.max(errs_can)),
        },
        'modified_knee': {
            'params': fr_mod.params.model_dump(),
            'rms_residual_ma': fr_mod.rms_residual_ma,
            'mean_err': float(np.mean(errs_mod)),
            'max_err': float(np.max(errs_mod)),
        },
        'sc6_check': {
            'kg1_in_physical_range': 500.0 <= fr_mod.params.kg1 <= 10000.0,
            'ex_in_physical_range': 1.0 <= fr_mod.params.ex <= 2.0,
        },
    }


def main() -> None:
    out: dict[str, Any] = {}
    print('=== T182 Phase 4 acceptance ===\n')

    print('-- EL34 (SC#2 knee improvement) --')
    el34 = el34_acceptance()
    sc2_knee_mean = el34['modified_knee']['knee']['mean']
    sc2_knee_max = el34['modified_knee']['knee']['max']
    sc2_plateau_mean = el34['modified_knee']['plateau']['mean']
    sc2_pass = (
        sc2_knee_mean is not None
        and sc2_knee_mean < 0.30
        and sc2_knee_max < 0.40
        and sc2_plateau_mean < 0.15
    )
    el34['sc2_pass'] = sc2_pass
    print(f'  canonical:  knee mean={el34["canonical"]["knee"]["mean"]:.3f} '
          f'max={el34["canonical"]["knee"]["max"]:.3f}, '
          f'plateau mean={el34["canonical"]["plateau"]["mean"]:.3f}')
    print(f'  modified:   knee mean={sc2_knee_mean:.3f} max={sc2_knee_max:.3f}, '
          f'plateau mean={sc2_plateau_mean:.3f}')
    print(f'  SC#2 verdict: {"PASS" if sc2_pass else "FAIL"}\n')
    out['el34'] = el34

    print('-- 300B (SC#4 cutoff improvement) --')
    we300b = we_300b_acceptance()
    sc4_cutoff_mean = we300b['modified_cutoff']['cutoff']['mean']
    sc4_mid_mean = we300b['modified_cutoff']['mid']['mean']
    sc4_pass = (
        sc4_cutoff_mean is not None
        and sc4_cutoff_mean < 0.30
        and sc4_mid_mean is not None
        and sc4_mid_mean < 0.15
    )
    we300b['sc4_pass'] = sc4_pass
    print(f'  canonical:  cutoff mean={we300b["canonical"]["cutoff"]["mean"]:.3f}, '
          f'mid mean={we300b["canonical"]["mid"]["mean"]:.3f}')
    print(f'  modified:   cutoff mean={sc4_cutoff_mean:.3f}, mid mean={sc4_mid_mean:.3f}')
    print(f'  SC#4 verdict: {"PASS" if sc4_pass else "FAIL"}\n')
    out['300b'] = we300b

    print('-- 6П13С (SC#6 sanity-check) --')
    sc6 = t6p13s_acceptance()
    print(f'  canonical params:  KG1={sc6["canonical"]["params"]["kg1"]:.1f}, '
          f'EX={sc6["canonical"]["params"]["ex"]:.3f}, mean err={sc6["canonical"]["mean_err"]:.3f}')
    print(f'  modified params:   KG1={sc6["modified_knee"]["params"]["kg1"]:.1f}, '
          f'EX={sc6["modified_knee"]["params"]["ex"]:.3f}, '
          f'Vk={sc6["modified_knee"]["params"]["vk"]:.1f}, mean err={sc6["modified_knee"]["mean_err"]:.3f}')
    print(f'  KG1 ∈ [500, 10000]: {sc6["sc6_check"]["kg1_in_physical_range"]}')
    print(f'  EX ∈ [1.0, 2.0]:    {sc6["sc6_check"]["ex_in_physical_range"]}\n')
    out['6p13s'] = sc6

    _RESULTS.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Results written to: {_RESULTS}')


if __name__ == '__main__':
    main()
