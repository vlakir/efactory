"""Domain layer для T187 off-grid cleanup — snap + VO + exceptions."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from domain.grid import (
    DEFAULT_CONNECTION_GRID_MM,
    GridStepMm,
    OffGridEndpoint,
    OffGridPositionError,
    OffGridReport,
    snap_to_grid,
)


# === snap_to_grid ===


def test_snap_default_grid_is_kicad_50mil() -> None:
    assert DEFAULT_CONNECTION_GRID_MM == 1.27


def test_snap_keeps_on_grid_values_unchanged() -> None:
    assert snap_to_grid(0.0) == 0.0
    assert snap_to_grid(1.27) == 1.27
    assert snap_to_grid(101.6) == 101.6
    assert snap_to_grid(-2.54) == -2.54


def test_snap_moves_off_grid_to_nearest_node() -> None:
    # 80.5 / 1.27 = 63.385 → round = 63 → 63 * 1.27 = 80.01
    assert snap_to_grid(80.5) == pytest.approx(80.01, abs=1e-9)
    # 103.81 / 1.27 = 81.74 → round = 82 → 82 * 1.27 = 104.14
    assert snap_to_grid(103.81) == pytest.approx(104.14, abs=1e-9)


def test_snap_handles_negative_values() -> None:
    assert snap_to_grid(-1.0) == pytest.approx(-1.27, abs=1e-9)
    assert snap_to_grid(-3.81) == pytest.approx(-3.81, abs=1e-9)


def test_snap_is_idempotent() -> None:
    for v in [0.5, 80.5, 103.81, -1.0, 99.06, 0.7492]:
        once = snap_to_grid(v)
        twice = snap_to_grid(once)
        assert twice == once


def test_snap_supports_custom_grid_step() -> None:
    # 0.5mm grid: 1.7 → round(3.4) = 3 → 1.5
    assert snap_to_grid(1.7, grid_mm=0.5) == pytest.approx(1.5, abs=1e-9)
    # imperial 25 mil = 0.635 mm: 0.7 / 0.635 = 1.102 → round = 1 → 0.635
    assert snap_to_grid(0.7, grid_mm=0.635) == pytest.approx(0.635, abs=1e-9)


def test_snap_rejects_non_positive_grid() -> None:
    with pytest.raises(ValueError, match='grid_mm must be > 0'):
        snap_to_grid(1.0, grid_mm=0.0)
    with pytest.raises(ValueError, match='grid_mm must be > 0'):
        snap_to_grid(1.0, grid_mm=-1.27)


def test_snap_cleans_fp_jitter() -> None:
    # 1.27 with floating-point fuzz round-trips back
    assert snap_to_grid(1.27 + 1e-12) == pytest.approx(1.27, abs=1e-9)
    assert snap_to_grid(1.27 - 1e-12) == pytest.approx(1.27, abs=1e-9)


# === GridStepMm semantic alias ===


def test_grid_step_mm_alias_resolves_to_float() -> None:
    step: GridStepMm = GridStepMm(1.27)
    assert isinstance(step, float)
    assert step == 1.27


# === OffGridEndpoint ===


def _sample_endpoint(uuid: str = 'abc') -> OffGridEndpoint:
    return OffGridEndpoint(
        kind='pin',
        description='Symbol R3 Pin 1 [Passive, Line]',
        pos=(99.06, 103.81),
        nearest_grid=(99.06, 104.14),
        delta_mm=(0.0, -0.33),
        uuid=uuid,
    )


def test_off_grid_endpoint_holds_all_fields() -> None:
    ep = _sample_endpoint()
    assert ep.kind == 'pin'
    assert ep.description.startswith('Symbol R3')
    assert ep.pos == (99.06, 103.81)
    assert ep.nearest_grid == (99.06, 104.14)
    assert ep.delta_mm == (0.0, -0.33)
    assert ep.uuid == 'abc'


def test_off_grid_endpoint_is_frozen() -> None:
    ep = _sample_endpoint()
    with pytest.raises(ValidationError):
        ep.description = 'mutated'  # type: ignore[misc]


def test_off_grid_endpoint_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        OffGridEndpoint(  # type: ignore[call-arg]
            kind='pin',
            description='d',
            pos=(0.0, 0.0),
            nearest_grid=(0.0, 0.0),
            delta_mm=(0.0, 0.0),
            uuid='u',
            extra='nope',
        )


def test_off_grid_endpoint_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        OffGridEndpoint(
            kind='gizmo',  # type: ignore[arg-type]
            description='d',
            pos=(0.0, 0.0),
            nearest_grid=(0.0, 0.0),
            delta_mm=(0.0, 0.0),
            uuid='u',
        )


def test_off_grid_endpoint_accepts_all_kinds() -> None:
    for kind in ('pin', 'wire', 'label', 'pwr-flag', 'no-connect'):
        ep = OffGridEndpoint(
            kind=kind,  # type: ignore[arg-type]
            description='d',
            pos=(0.0, 0.0),
            nearest_grid=(0.0, 0.0),
            delta_mm=(0.0, 0.0),
            uuid='u',
        )
        assert ep.kind == kind


def test_off_grid_endpoint_max_abs_delta_helper() -> None:
    """abs-Δ от grid — для сортировки приоритета ручного фикса."""
    ep = OffGridEndpoint(
        kind='wire',
        description='d',
        pos=(0.0, 0.0),
        nearest_grid=(0.0, 0.0),
        delta_mm=(-0.33, 0.12),
        uuid='u',
    )
    assert ep.max_abs_delta_mm == pytest.approx(0.33)


# === OffGridReport ===


def _sample_report(endpoints: list[OffGridEndpoint] | None = None) -> OffGridReport:
    if endpoints is None:
        endpoints = [_sample_endpoint('a'), _sample_endpoint('b')]
    return OffGridReport(
        kicad_version='10.0.3',
        schematic_path=Path('/tmp/test.kicad_sch'),
        timestamp=datetime(2026, 6, 5, 3, 30, 0, tzinfo=UTC),
        grid_step_mm=GridStepMm(1.27),
        endpoints=endpoints,
    )


def test_off_grid_report_count_matches_endpoints() -> None:
    report = _sample_report()
    assert report.count == 2


def test_off_grid_report_count_zero_for_empty() -> None:
    report = _sample_report(endpoints=[])
    assert report.count == 0


def test_off_grid_report_is_frozen() -> None:
    report = _sample_report()
    with pytest.raises(ValidationError):
        report.kicad_version = 'X'  # type: ignore[misc]


def test_off_grid_report_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        OffGridReport(  # type: ignore[call-arg]
            kicad_version='10.0.3',
            schematic_path=Path('/tmp/x.kicad_sch'),
            timestamp=datetime(2026, 6, 5, tzinfo=UTC),
            grid_step_mm=GridStepMm(1.27),
            endpoints=[],
            extra='nope',
        )


# === OffGridPositionError ===


def test_off_grid_position_error_carries_diagnostic_payload() -> None:
    err = OffGridPositionError(
        component_name='R3',
        requested=(99.06, 103.81),
        snapped=(99.06, 104.14),
        delta_mm=(0.0, -0.33),
    )
    assert err.component_name == 'R3'
    assert err.requested == (99.06, 103.81)
    assert err.snapped == (99.06, 104.14)
    assert err.delta_mm == (0.0, -0.33)
    msg = str(err)
    assert 'R3' in msg
    assert '99.06' in msg
    assert '103.81' in msg
