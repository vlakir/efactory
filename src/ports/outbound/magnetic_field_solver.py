"""
MagneticFieldSolver — outbound port для FEM-расчёта поля (T113 Phase 2).

Точный численный расчёт магнитного поля + индуктивности через FEM:
учёт 3D-геометрии, leakage, fringing. Backend — GetDP+Gmsh (выбран в
ADR `2026-05-20 — Magnetic field verification: GetDP+Gmsh выбран` в
`DECISIONS.md` по результатам T113 Phase 1 pilot).

В отличие от `MagneticAnalytics` — медленнее (~1 sec на простой
2D-magnetostatic), но точнее на complex geometries.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.magnetic import MagneticComponent


class MagneticFieldSolverUnavailableError(Exception):
    """FEM-solver не доступен (бинарь не в PATH, mesh tool отсутствует)."""


class MagneticFieldSolverFailedError(Exception):
    """Solver стартовал, но fail'нул (mesh error, convergence, parse)."""


class UnsupportedGeometryError(MagneticFieldSolverFailedError):
    """
    Геометрия (core shape) не поддерживается данным adapter'ом.

    Phase 2 MVP: только E-core 2D-planar; toroidal/U/EC/PQ и т.п. —
    follow-up'ы (см. spec T113 §"Out of scope").
    """


class MagneticFieldSolver(Protocol):
    """FEM-расчёт магнитной индуктивности через outbound port."""

    async def solve_inductance(
        self,
        component: MagneticComponent,
    ) -> float:
        """
        Вычислить primary self-inductance методом FEM в Henries.

        Бросает `MagneticFieldSolverUnavailableError`, если solver
        не доступен в окружении; `MagneticFieldSolverFailedError` —
        при runtime error (mesh failure, convergence, parse);
        `UnsupportedGeometryError` — если geometry shape не E-core.
        """
        ...
