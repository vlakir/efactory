"""
MagneticFieldSolver — outbound port для FEM-расчёта поля (T113 Phase 2 + T129).

Точный численный расчёт магнитного поля + индуктивности через FEM:
учёт 3D-геометрии, leakage, fringing. Backend — GetDP+Gmsh (выбран в
ADR `2026-05-20 — Magnetic field verification: GetDP+Gmsh выбран` в
`DECISIONS.md` по результатам T113 Phase 1 pilot).

В отличие от `MagneticAnalytics` — медленнее (~1 sec на простой
2D-magnetostatic), но точнее на complex geometries.

T129: расширен на nonlinear material (Frohlich-Kennelly) +
DC-bias central-difference incremental inductance. Возвращаемый DTO
`FemSolveOutcome` несёт метод формулировки и diagnostic поля.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.magnetic import FemMethod, MagneticComponent


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


@dataclass(frozen=True)
class FemSolveOutcome:
    """
    Результат FEM-расчёта индуктивности.

    `inductance_h` — индуктивность (Henries). Для `method='linear'` —
    self-inductance L_p из energy method (W = 0.5·L·I²). Для
    `method='nonlinear-frohlich'` — incremental L_inc вокруг
    `OperatingPoint.primary_dc_bias_a` через central finite difference
    на двух nonlinear solve'ах (`I_dc ± ΔI/2`; middle solve `I_dc`
    был в первоначальном дизайне для `peak_flux_density_t` diagnostic,
    но удалён в ultrareview revision — peak отложен на follow-up T-ID).

    `peak_flux_density_t` — max |B| по mesh после nonlinear solve [T];
    None в linear режиме или если diagnostic не реализован.
    """

    inductance_h: float
    method: FemMethod
    peak_flux_density_t: float | None = None


class MagneticFieldSolver(Protocol):
    """FEM-расчёт магнитной индуктивности через outbound port."""

    async def solve(self, component: MagneticComponent) -> FemSolveOutcome:
        """
        Вычислить primary inductance методом FEM (Henries) + diagnostics.

        Бросает `MagneticFieldSolverUnavailableError`, если solver
        не доступен в окружении; `MagneticFieldSolverFailedError` —
        при runtime error (mesh failure, convergence, parse);
        `UnsupportedGeometryError` — если geometry shape не E-core.
        """
        ...
