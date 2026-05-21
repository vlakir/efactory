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
from domain.magnetic import (
    Core,
    GapType,
    IsolationSide,
    MagneticComponent,
    OperatingPoint,
    Winding,
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


def _component() -> MagneticComponent:
    return MagneticComponent(
        name='dummy',
        core=Core(
            shape_name='E 42/21/15',
            material_name='Nanoperm 8000',
            bobbin_name='Bobbin E42/15',
            gap_length_m=0.0001,
            gap_type=GapType.SUBTRACTIVE,
        ),
        windings=(
            Winding(
                name='primary',
                number_turns=2500,
                isolation_side=IsolationSide.PRIMARY,
            ),
            Winding(
                name='secondary',
                number_turns=100,
                isolation_side=IsolationSide.SECONDARY,
            ),
        ),
        operating_point=OperatingPoint(
            frequency_hz=1000.0,
            primary_peak_voltage_v=250.0,
        ),
    )


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


def test_extract_frohlich_params_reads_first_initial_and_first_saturation() -> None:
    """W2 mitigation: explicit material query до nonlinear solve."""
    solver = GetDpFemSolver(_FakePyOM(), material_model='nonlinear-frohlich')
    mu_initial, b_sat = solver._extract_frohlich_params('Nanoperm 8000')  # noqa: SLF001
    assert mu_initial == pytest.approx(7968.0)
    assert b_sat == pytest.approx(1.2)


def test_extract_frohlich_params_raises_on_unknown_material() -> None:
    solver = GetDpFemSolver(_FakePyOM(), material_model='nonlinear-frohlich')
    with pytest.raises(LookupError, match='unknown-material'):
        solver._extract_frohlich_params('unknown-material')  # noqa: SLF001


def test_extract_frohlich_params_raises_on_empty_initial_permeability() -> None:
    bad = [
        {
            'name': 'Broken',
            'permeability': {'initial': []},
            'saturation': [{'magneticField': 1.0, 'magneticFluxDensity': 1.0}],
        },
    ]
    solver = GetDpFemSolver(
        _FakePyOM(bad),
        material_model='nonlinear-frohlich',
    )
    with pytest.raises(LookupError, match='permeability.initial'):
        solver._extract_frohlich_params('Broken')  # noqa: SLF001


def test_extract_frohlich_params_raises_on_missing_saturation() -> None:
    bad = [
        {
            'name': 'NoSat',
            'permeability': {'initial': [{'value': 5000.0}]},
            'saturation': [],
        },
    ]
    solver = GetDpFemSolver(_FakePyOM(bad), material_model='nonlinear-frohlich')
    with pytest.raises(LookupError, match='saturation'):
        solver._extract_frohlich_params('NoSat')  # noqa: SLF001


def test_extract_frohlich_params_accepts_dict_initial_too() -> None:
    """PyOM может вернуть permeability.initial как одиночный dict (более старый MAS)."""
    materials = [
        {
            'name': 'OldSchema',
            'permeability': {'initial': {'value': 4200.0}},
            'saturation': {'magneticFluxDensity': 0.4},
        },
    ]
    solver = GetDpFemSolver(_FakePyOM(materials), material_model='nonlinear-frohlich')
    mu_initial, b_sat = solver._extract_frohlich_params('OldSchema')  # noqa: SLF001
    assert mu_initial == pytest.approx(4200.0)
    assert b_sat == pytest.approx(0.4)
