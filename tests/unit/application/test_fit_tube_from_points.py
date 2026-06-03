"""fit_tube_from_points use case tests (T031 Phase 2)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from application.fit_tube_from_points import (
    FitTubeFromPointsRequest,
    FitTubeUseCaseError,
    fit_tube_from_points,
)
from domain.tube_fitting import (
    AyumiPentodeParams,
    KorenTriodeParams,
    ayumi_pentode_ia,
    koren_triode_ia,
)

if TYPE_CHECKING:
    from ports.outbound.tube_iv_repository import TubeIVRepository
    from ports.outbound.tube_lib_writer import (
        HeaderTubeType,
        TubeLibMeta,
        TubeLibWriter,
    )


# ============================== Stubs ==============================


class _StubLibWriter:
    """In-memory TubeLibWriter stub — captures invocation args."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def write(
        self,
        path: Path,
        spice_name: str,
        params: KorenTriodeParams | AyumiPentodeParams,
        *,
        header_tube_type: HeaderTubeType,
        meta: TubeLibMeta,
        force: bool = False,
    ) -> None:
        self.calls.append(
            {
                'path': path,
                'spice_name': spice_name,
                'params': params,
                'header_tube_type': header_tube_type,
                'meta': meta,
                'force': force,
            }
        )


# ============================== Helpers — synth JSON fixtures ==============================


_TWELVE_AX7 = KorenTriodeParams(mu=100, ex=1.4, kg1=1060, kp=600, kvb=300)
_EL34 = AyumiPentodeParams(
    mu=11, ex=1.35, kg1=650, kg2=4500, kp=60, kvb=24, screen_v=250
)


def _synthesize_triode_json(tmp_path: Path, name: str = '12AX7_FIX') -> Path:
    payload = {
        'tube_name': name,
        'tube_type': 'triode',
        'source': 'synth',
        'date_extracted': '2026-06-03',
        'curves': [
            {
                'vg': vg,
                'points': [
                    [va, koren_triode_ia(vg, va, _TWELVE_AX7)]
                    for va in (50.0, 100.0, 200.0, 300.0, 400.0)
                ],
            }
            for vg in (-0.5, -1.0, -2.0, -3.0)
        ],
    }
    p = tmp_path / 'triode_synth.json'
    p.write_text(json.dumps(payload), encoding='utf-8')
    return p


def _synthesize_pentode_json(
    tmp_path: Path, *, with_screen: bool = False, name: str = 'EL34_FIX'
) -> Path:
    vg_values = (-5.0, -10.0, -15.0)
    va_values = (50.0, 100.0, 200.0, 300.0, 400.0)
    payload: dict[str, object] = {
        'tube_name': name,
        'tube_type': 'pentode',
        'source': 'synth',
        'date_extracted': '2026-06-03',
        'screen_voltage_v': 250.0,
        'curves': [
            {
                'vg': vg,
                'points': [
                    [va, ayumi_pentode_ia(vg, va, _EL34)] for va in va_values
                ],
            }
            for vg in vg_values
        ],
    }
    if with_screen:
        # Ig2 — Va-independent в Koren-pentode formulation; same value per
        # curve, варьируем по Vg (one point per Vg достаточно для KG2).
        payload['screen_curves'] = [
            {
                'vg': vg,
                'points': [[200.0, ayumi_pentode_ia(vg, 200.0, _EL34) / 7.0]],
            }
            for vg in vg_values
        ]
        # Поправка: realistic Ig2 via existing function. Используем правильное:
        # из domain._fitter._ayumi_pentode_ig2_vec, но не импортируем private.
        # Считаем вручную через 2*E1^EX/KG2 эквивалент → возьмём реально.
    p = tmp_path / 'pentode_synth.json'
    p.write_text(json.dumps(payload), encoding='utf-8')
    return p


def _make_repo() -> TubeIVRepository:
    from adapters.outbound.spice_models.tube_json import (  # noqa: PLC0415
        FilesystemTubeIVRepository,
    )

    return FilesystemTubeIVRepository()


# ============================== Happy path ==============================


def test_triode_end_to_end_writes_lib_and_returns_paths(tmp_path: Path) -> None:
    json_path = _synthesize_triode_json(tmp_path)
    writer = _StubLibWriter()
    out_dir = tmp_path / 'out'
    request = FitTubeFromPointsRequest(
        spice_name='X12AX7',
        tube_type='triode',
        points_json=json_path,
        out_dir=out_dir,
    )
    result = fit_tube_from_points(
        request,
        iv_repository=_make_repo(),
        lib_writer=writer,
        today=date(2026, 6, 3),
    )

    assert result.lib_path == out_dir / 'X12AX7.lib'
    assert len(writer.calls) == 1
    call = writer.calls[0]
    assert call['header_tube_type'] == 'triode'
    assert isinstance(call['params'], KorenTriodeParams)
    assert result.used_joint_ig2_fit is False
    assert result.kg2_was_overridden is False
    # Round-trip ≤5% после fit:
    p = call['params']
    assert abs(p.mu - 100) / 100 <= 0.05


def test_pentode_ia_only_applies_kg2_ratio_fallback(tmp_path: Path) -> None:
    json_path = _synthesize_pentode_json(tmp_path)
    writer = _StubLibWriter()
    request = FitTubeFromPointsRequest(
        spice_name='XEL34',
        tube_type='pentode',
        points_json=json_path,
        out_dir=tmp_path / 'out',
        kg2_ratio=5.0,
    )
    result = fit_tube_from_points(
        request,
        iv_repository=_make_repo(),
        lib_writer=writer,
    )

    assert result.kg2_was_overridden is True
    assert result.used_joint_ig2_fit is False
    written_params = writer.calls[0]['params']
    assert isinstance(written_params, AyumiPentodeParams)
    # KG2 = 5 * KG1 точно.
    assert written_params.kg2 == pytest.approx(5.0 * written_params.kg1)


def test_pentode_with_screen_curves_uses_joint_fit(tmp_path: Path) -> None:
    # Pentode JSON с screen_curves — добавим вручную realistic Ig2 точки.
    # Ig2 в Koren-pentode = 2*E1^EX/KG2, не зависит от Va. Поэтому одной
    # точки per Vg достаточно (любая Va).
    from domain.tube_fitting._fitter import _ayumi_pentode_ig2_vec  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    vg_values = (-5.0, -10.0, -15.0, -20.0)
    va_values = (50.0, 100.0, 200.0, 300.0, 400.0, 500.0)
    payload = {
        'tube_name': 'EL34_FIX',
        'tube_type': 'pentode',
        'source': 'synth',
        'date_extracted': '2026-06-03',
        'screen_voltage_v': 250.0,
        'curves': [
            {
                'vg': vg,
                'points': [
                    [va, ayumi_pentode_ia(vg, va, _EL34)] for va in va_values
                ],
            }
            for vg in vg_values
        ],
        'screen_curves': [
            {
                'vg': vg,
                'points': [
                    [
                        va,
                        float(
                            _ayumi_pentode_ig2_vec(
                                np.array([vg]),
                                _EL34.mu,
                                _EL34.ex,
                                _EL34.kg2,
                                _EL34.kp,
                                _EL34.screen_v,
                            )[0]
                        ),
                    ]
                    for va in va_values
                ],
            }
            for vg in vg_values
        ],
    }
    json_path = tmp_path / 'pentode_full.json'
    json_path.write_text(json.dumps(payload), encoding='utf-8')

    writer = _StubLibWriter()
    request = FitTubeFromPointsRequest(
        spice_name='XEL34',
        tube_type='pentode',
        points_json=json_path,
        out_dir=tmp_path / 'out',
    )
    result = fit_tube_from_points(
        request, iv_repository=_make_repo(), lib_writer=writer
    )

    assert result.used_joint_ig2_fit is True
    assert result.kg2_was_overridden is False
    written = writer.calls[0]['params']
    assert isinstance(written, AyumiPentodeParams)
    # KG2 теперь identifiable из Ig2 → ≤5%.
    assert abs(written.kg2 - 4500) / 4500 <= 0.05


def test_tetrode_header_passed_through(tmp_path: Path) -> None:
    json_path = _synthesize_pentode_json(tmp_path, name='KT88_FIX')
    writer = _StubLibWriter()
    request = FitTubeFromPointsRequest(
        spice_name='XKT88',
        tube_type='pentode',
        points_json=json_path,
        out_dir=tmp_path / 'out',
        header_type='tetrode',
    )
    fit_tube_from_points(
        request, iv_repository=_make_repo(), lib_writer=writer
    )
    assert writer.calls[0]['header_tube_type'] == 'tetrode'


# ============================== Validation errors ==============================


def test_cli_type_mismatch_raises(tmp_path: Path) -> None:
    json_path = _synthesize_triode_json(tmp_path)
    writer = _StubLibWriter()
    request = FitTubeFromPointsRequest(
        spice_name='X',
        tube_type='pentode',  # JSON has triode
        points_json=json_path,
        out_dir=tmp_path / 'out',
    )
    with pytest.raises(FitTubeUseCaseError, match='tube_type'):
        fit_tube_from_points(
            request, iv_repository=_make_repo(), lib_writer=writer
        )
    assert writer.calls == []


def test_include_vct_with_pentode_raises(tmp_path: Path) -> None:
    json_path = _synthesize_pentode_json(tmp_path)
    writer = _StubLibWriter()
    request = FitTubeFromPointsRequest(
        spice_name='X',
        tube_type='pentode',
        points_json=json_path,
        out_dir=tmp_path / 'out',
        include_vct=True,
    )
    with pytest.raises(FitTubeUseCaseError, match='include-vct'):
        fit_tube_from_points(
            request, iv_repository=_make_repo(), lib_writer=writer
        )


def test_missing_json_file_raises(tmp_path: Path) -> None:
    writer = _StubLibWriter()
    request = FitTubeFromPointsRequest(
        spice_name='X',
        tube_type='triode',
        points_json=tmp_path / 'absent.json',
        out_dir=tmp_path / 'out',
    )
    with pytest.raises(FitTubeUseCaseError, match='cannot read'):
        fit_tube_from_points(
            request, iv_repository=_make_repo(), lib_writer=writer
        )


# ============================== seed_from ==============================


def test_seed_from_triode_threads_into_fitter(tmp_path: Path) -> None:
    json_path = _synthesize_triode_json(tmp_path)
    seed_path = tmp_path / 'seed.json'
    seed_path.write_text(_TWELVE_AX7.model_dump_json(), encoding='utf-8')

    writer = _StubLibWriter()
    request = FitTubeFromPointsRequest(
        spice_name='X12AX7',
        tube_type='triode',
        points_json=json_path,
        out_dir=tmp_path / 'out',
        seed_from=seed_path,
    )
    result = fit_tube_from_points(
        request, iv_repository=_make_repo(), lib_writer=writer
    )
    # Fit с seed_from = ground truth → должен попасть точно.
    p = result.fit_result.params
    assert abs(p.mu - 100) / 100 <= 0.05
