"""
Use case: `efactory tube fit-from-points` (T031 Phase 2, spec S1/S2/S3).

Pure compute (Clarify C7): orchestrates JSON load → domain fit →
.lib write + KG2 fallback для Ia-only pentode case. KB topic создаётся
slash-командой отдельно (Phase 3), не здесь.

A-W1 (Analyze 🟡): `--include-vct` ∈ triode-only (CLI отвергает с
pentode на argparse-уровне; use case дополнительно валидирует — defence
in depth).

DI ports: `TubeIVRepository` (load JSON) и `TubeLibWriter` (write .lib)
инжектятся через kwargs. Тесты используют простые stub-классы;
composition root связывает с filesystem-implementations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict

from domain.tube_fitting import (
    AyumiPentodeParams,
    FitResult,
    IVDataset,
    KorenTriodeParams,
    fit_ayumi_pentode,
    fit_koren_triode,
)
from ports.outbound.tube_lib_writer import HeaderTubeType, TubeLibMeta

if TYPE_CHECKING:
    from ports.outbound.tube_iv_repository import TubeIVRepository
    from ports.outbound.tube_lib_writer import TubeLibWriter


TubeType = Literal['triode', 'pentode']


class FitTubeFromPointsRequest(BaseModel):
    """CLI/use-case request: paths, flags, knobs."""

    model_config = ConfigDict(frozen=True, extra='forbid')

    spice_name: str
    """SPICE id для .SUBCKT и filename (валидируется writer'ом)."""

    tube_type: TubeType
    """`--type` CLI флаг. Должен совпадать с `IVDataset.tube_type`."""

    points_json: Path
    """`--points <file.json>`."""

    out_dir: Path
    """Куда положить `.lib` (CLI default — user overlay)."""

    header_type: HeaderTubeType = 'pentode'
    """`--header-type`. Не используется для triode (writer проверяет
    match). Default 'pentode' соответствует CLI default."""

    include_vct: bool = False
    """`--include-vct` (только для triode)."""

    seed_from: Path | None = None
    """`--seed-from <existing-tube-params.json>` (S3)."""

    kg2_ratio: float = 5.0
    """`--kg2-ratio` — typical KG2/KG1 ratio fallback для Ia-only
    pentode fit'а (Phase 1+ rationale)."""

    force: bool = False
    """`--force` — перезаписать existing .lib."""

    n_starts: int = 5
    seed: int = 42


@dataclass(frozen=True)
class FitTubeFromPointsResult:
    """Что вернул use case CLI'у для печати."""

    lib_path: Path
    fit_result: FitResult
    used_joint_ig2_fit: bool
    kg2_was_overridden: bool
    """True если pentode + no screen_curves → KG2 заменён typical ratio."""


class FitTubeUseCaseError(RuntimeError):
    """Use case не смог завершиться (incompatible flags / type mismatch / IO)."""


def fit_tube_from_points(
    request: FitTubeFromPointsRequest,
    *,
    iv_repository: TubeIVRepository,
    lib_writer: TubeLibWriter,
    today: date | None = None,
) -> FitTubeFromPointsResult:
    """Orchestration. Domain ↔ ports only; никаких прямых adapter-импортов."""
    today = today or date.today()  # noqa: DTZ011 — domain date, не UTC moment
    ds = _load_dataset(iv_repository, request)
    _validate_request_against_dataset(request, ds)

    seed_from = _load_seed_from(iv_repository, request)

    if request.tube_type == 'triode':
        triode_params, fr, used_joint, kg2_override = _fit_triode(
            request, ds, seed_from
        )
        header_tube_type: HeaderTubeType = 'triode'
        params_for_write: KorenTriodeParams | AyumiPentodeParams = triode_params
    else:
        pentode_params, fr, used_joint, kg2_override = _fit_pentode(
            request, ds, seed_from
        )
        header_tube_type = request.header_type
        params_for_write = pentode_params

    meta = _make_meta(ds, fr, today=today)
    lib_path = request.out_dir / f'{request.spice_name}.lib'
    try:
        lib_writer.write(
            lib_path,
            request.spice_name,
            params_for_write,
            header_tube_type=header_tube_type,
            meta=meta,
            force=request.force,
        )
    except (ValueError, OSError, RuntimeError) as exc:
        raise FitTubeUseCaseError(str(exc)) from exc

    return FitTubeFromPointsResult(
        lib_path=lib_path,
        fit_result=fr,
        used_joint_ig2_fit=used_joint,
        kg2_was_overridden=kg2_override,
    )


def _load_dataset(
    repo: TubeIVRepository, request: FitTubeFromPointsRequest
) -> IVDataset:
    try:
        return repo.load_iv_dataset(request.points_json)
    except RuntimeError as exc:
        raise FitTubeUseCaseError(str(exc)) from exc


def _validate_request_against_dataset(
    request: FitTubeFromPointsRequest, ds: IVDataset
) -> None:
    if request.tube_type != ds.tube_type:
        msg = (
            f"CLI --type='{request.tube_type}' but JSON has "
            f"tube_type='{ds.tube_type}' — fix one to match"
        )
        raise FitTubeUseCaseError(msg)
    if request.include_vct and request.tube_type != 'triode':
        msg = (
            '--include-vct is valid only for --type triode '
            f'(got --type {request.tube_type})'
        )
        raise FitTubeUseCaseError(msg)


def _load_seed_from(
    repo: TubeIVRepository, request: FitTubeFromPointsRequest
) -> KorenTriodeParams | AyumiPentodeParams | None:
    if request.seed_from is None:
        return None
    try:
        return repo.load_seed_from_params(request.seed_from, request.tube_type)
    except RuntimeError as exc:
        raise FitTubeUseCaseError(str(exc)) from exc


def _fit_triode(
    request: FitTubeFromPointsRequest,
    ds: IVDataset,
    seed_from: KorenTriodeParams | AyumiPentodeParams | None,
) -> tuple[KorenTriodeParams, FitResult, bool, bool]:
    triode_seed = seed_from if isinstance(seed_from, KorenTriodeParams) else None
    fr = fit_koren_triode(
        ds,
        include_vct=request.include_vct,
        n_starts=request.n_starts,
        seed=request.seed,
        seed_from=triode_seed,
    )
    if not isinstance(fr.params, KorenTriodeParams):
        msg = 'fit_koren_triode did not return KorenTriodeParams'
        raise FitTubeUseCaseError(msg)
    return fr.params, fr, False, False


def _fit_pentode(
    request: FitTubeFromPointsRequest,
    ds: IVDataset,
    seed_from: KorenTriodeParams | AyumiPentodeParams | None,
) -> tuple[AyumiPentodeParams, FitResult, bool, bool]:
    pentode_seed = seed_from if isinstance(seed_from, AyumiPentodeParams) else None
    fr = fit_ayumi_pentode(
        ds,
        n_starts=request.n_starts,
        seed=request.seed,
        seed_from=pentode_seed,
    )
    if not isinstance(fr.params, AyumiPentodeParams):
        msg = 'fit_ayumi_pentode did not return AyumiPentodeParams'
        raise FitTubeUseCaseError(msg)
    used_joint = bool(ds.screen_curves)
    if used_joint:
        return fr.params, fr, True, False
    # Ia-only fit: KG2 не identifiable → подставляем typical ratio.
    fixed = fr.params.model_copy(update={'kg2': request.kg2_ratio * fr.params.kg1})
    fr_fixed = fr.model_copy(update={'params': fixed})
    return fixed, fr_fixed, False, True


def _make_meta(ds: IVDataset, fr: FitResult, *, today: date) -> TubeLibMeta:
    return TubeLibMeta(
        display_name=ds.tube_name,
        source=ds.source,
        date_extracted=ds.date_extracted,
        date_fitted=today,
        rms_residual_ma=fr.rms_residual_ma,
        n_points=fr.n_points,
    )
