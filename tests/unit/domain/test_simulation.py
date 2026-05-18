"""Domain: Simulation + SimulationStatus + SimulationResult (T004)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from domain.simulation import (
    Simulation,
    SimulationResult,
    SimulationStatus,
)


def test_simulation_status_enum() -> None:
    assert set(SimulationStatus) == {
        SimulationStatus.PENDING,
        SimulationStatus.NETLIST_READY,
        SimulationStatus.SIMULATED,
        SimulationStatus.FAILED,
    }


def test_simulation_minimum_fields() -> None:
    sim = Simulation(
        project_id=uuid4(),
        schematic_path=Path('/p/proj/schematic/x.kicad_sch'),
    )
    assert sim.status is SimulationStatus.PENDING
    assert sim.netlist_path is None
    assert sim.result is None
    assert isinstance(sim.id, UUID)
    assert isinstance(sim.created_at, datetime)


def test_simulation_with_netlist_ready_status() -> None:
    sim = Simulation(
        project_id=uuid4(),
        schematic_path=Path('/p/proj/schematic/x.kicad_sch'),
        netlist_path=Path('/p/proj/sim/x.cir'),
        status=SimulationStatus.NETLIST_READY,
    )
    assert sim.status is SimulationStatus.NETLIST_READY
    assert sim.netlist_path == Path('/p/proj/sim/x.cir')


def test_simulation_is_frozen() -> None:
    sim = Simulation(
        project_id=uuid4(),
        schematic_path=Path('/p/x.kicad_sch'),
    )
    with pytest.raises(ValidationError):
        sim.status = SimulationStatus.SIMULATED  # type: ignore[misc]


def test_simulation_result_defaults_empty() -> None:
    result = SimulationResult()
    assert result.operating_points == {}


def test_simulation_result_with_op_values() -> None:
    result = SimulationResult(
        operating_points={'V(out)': 5.0, 'I(R1)': 0.001},
    )
    assert result.operating_points['V(out)'] == 5.0
    assert result.operating_points['I(R1)'] == 0.001


def test_simulation_result_is_frozen() -> None:
    result = SimulationResult()
    with pytest.raises(ValidationError):
        result.operating_points = {'a': 1.0}  # type: ignore[misc]
