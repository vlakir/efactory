"""
MagneticAnalytics — outbound port для analytical inductance (T113 Phase 2).

Быстрый аналитический расчёт магнитной индуктивности по геометрии
сердечника, материалу и числу витков. Не требует mesh / FEM; использует
PyOpenMagnetics `calculate_inductance_from_number_turns_and_gapping`
как первичный backend (см. ADR `2026-05-20 — Magnetic analytical
toolkit: PyOpenMagnetics` в `DECISIONS.md`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.magnetic import MagneticComponent


class MagneticAnalyticsUnavailableError(Exception):
    """PyOpenMagnetics не доступен (wheel не установлен, .so не найден)."""


class MagneticAnalyticsFailedError(Exception):
    """Расчёт стартовал, но fail'нул (unknown shape/material, bad geometry)."""


class MagneticAnalytics(Protocol):
    """Аналитический расчёт магнитной индуктивности через outbound port."""

    async def calculate_inductance(
        self,
        component: MagneticComponent,
    ) -> float:
        """
        Вычислить magnetizing inductance (primary winding) в Henries.

        Бросает `MagneticAnalyticsUnavailableError`, если backend
        не доступен; `MagneticAnalyticsFailedError` — при runtime
        ошибке (несовместимая геометрия, неизвестный материал, и т.п.).
        """
        ...
