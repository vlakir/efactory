"""Unit: GetDpFemSolver material_model parameter + Frohlich plumbing (T129 Phase A).

Mocked PyOM (без реального .so) для отвязки от env. Интеграционный
end-to-end через gmsh+getdp — в `tests/integration/adapters/fem_solver_getdp/`.
"""

from __future__ import annotations

from typing import Any

import pytest

from adapters.outbound.fem_solver_getdp.adapter import (
    GetDpFemSolver,
)


class _FakePyOM:
    """Минимальный stub PyOM для unit-тестов: get_core_materials + calculate_core_data."""

    def __init__(self, materials: list[dict[str, Any]] | None = None) -> None:
        self._materials = materials or _default_materials()

    def get_core_materials(self) -> list[dict[str, Any]]:
        return self._materials

    def calculate_core_data(  # noqa: PLR6301  - signature mirror PyOM
        self,
        core_fd: dict[str, Any],
        _verbose: bool,
    ) -> dict[str, Any]:
        # минимум для ECoreDimensions.from_pyom_core — не тестируем здесь,
        # тесты адаптера не доходят до geometry path.
        msg = 'fake calculate_core_data not used in these unit tests'
        raise NotImplementedError(msg)


def _default_materials() -> list[dict[str, Any]]:
    return [
        {
            'name': 'Nanoperm 8000',
            'permeability': {
                'initial': [
                    {'frequency': 11031.0, 'temperature': 25.0, 'value': 7968.0},
                    {'frequency': 13087.0, 'temperature': 25.0, 'value': 7908.0},
                ],
            },
            'saturation': [
                {'magneticField': 200.0, 'magneticFluxDensity': 1.2, 'temperature': 25.0},
            ],
        },
    ]


def test_default_material_model_is_linear() -> None:
    """Back-compat: без явного аргумента — linear (T113 baseline)."""
    solver = GetDpFemSolver(_FakePyOM())
    assert solver.material_model == 'linear'


def test_material_model_accepts_nonlinear_frohlich() -> None:
    solver = GetDpFemSolver(_FakePyOM(), material_model='nonlinear-frohlich')
    assert solver.material_model == 'nonlinear-frohlich'


def test_material_model_rejects_unknown_value() -> None:
    with pytest.raises(ValueError, match='material_model'):
        GetDpFemSolver(_FakePyOM(), material_model='magic-newton')  # type: ignore[arg-type]


