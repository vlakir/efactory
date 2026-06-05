"""T189 persistence hook tests для mag_verify_field."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from application.mag_verify_field import mag_verify_field
from domain.magnetic import (
    Core,
    GapType,
    IsolationSide,
    MagneticComponent,
    OperatingPoint,
    Winding,
)

if TYPE_CHECKING:
    from domain.magnetic_summary import MagneticsSummary


class _FakeAnalytics:
    async def calculate_inductance(self, _component: object) -> float:
        return 6.96


class _RecordingMagWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[MagneticsSummary, Path]] = []

    async def write(self, *, summary: MagneticsSummary, project_root: Path) -> Path:
        self.calls.append((summary, project_root))
        return project_root / 'out' / 'fem' / 'fake' / 'summary.json'


def _component() -> MagneticComponent:
    return MagneticComponent(
        name='OPT_6P14P',
        core=Core(
            shape_name='E42/15',
            material_name='M6X',
            gap_length_m=0.0001,
            gap_type=GapType.SUBTRACTIVE,
        ),
        windings=(
            Winding(
                name='primary',
                number_turns=2000,
                isolation_side=IsolationSide.PRIMARY,
            ),
        ),
        operating_point=OperatingPoint(
            frequency_hz=1000.0,
            primary_peak_voltage_v=200.0,
            primary_dc_bias_a=0.05,
        ),
    )


@pytest.mark.asyncio
async def test_persistence_skipped_without_writer() -> None:
    writer = _RecordingMagWriter()
    await mag_verify_field(
        component=_component(),
        analytics=_FakeAnalytics(),
    )
    assert writer.calls == []


@pytest.mark.asyncio
async def test_persistence_invoked_when_paired(tmp_path: Path) -> None:
    project_root = tmp_path / 'proj'
    project_root.mkdir()
    writer = _RecordingMagWriter()
    await mag_verify_field(
        component=_component(),
        analytics=_FakeAnalytics(),
        magnetics_results_writer=writer,
        project_root=project_root,
    )
    assert len(writer.calls) == 1
    summary, root = writer.calls[0]
    assert root == project_root
    assert summary.component_name == 'OPT_6P14P'
    assert summary.analytical_inductance_h == 6.96
    assert summary.fem_inductance_h is None
    assert summary.core.shape_name == 'E42/15'
    assert summary.operating_point.frequency_hz == 1000.0


@pytest.mark.asyncio
async def test_partial_args_rejected(tmp_path: Path) -> None:
    writer = _RecordingMagWriter()
    with pytest.raises(ValueError, match='должны быть переданы парой'):
        await mag_verify_field(
            component=_component(),
            analytics=_FakeAnalytics(),
            magnetics_results_writer=writer,
        )
    with pytest.raises(ValueError, match='должны быть переданы парой'):
        await mag_verify_field(
            component=_component(),
            analytics=_FakeAnalytics(),
            project_root=tmp_path,
        )
