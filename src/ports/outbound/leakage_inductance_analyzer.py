"""
LeakageInductanceAnalyzer — outbound port для leakage inductance Lσ (T132).

Расчёт leakage inductance для interleaved sandwich-намотки OPT (P-S,
P-S-P, P-S-P-S-P и т.п.). Domain operand — `MagneticComponent` с
обязательным `section_layout` полем. Backend — PyOpenMagnetics
`calculate_leakage_inductance` (через adapter, см. T132 Phase B).

Отдельный port от `MagneticAnalytics` (magnetizing inductance) — SRP
per Protocol: один и тот же PyOM adapter implement'ит оба port'а, но
domain consumer'ы (use case'ы) зависят только от того, что им нужно.
См. T132 spec Q5/Q6.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.magnetic import LeakageInductanceResult, MagneticComponent


class LeakageInductanceAnalyzerUnavailableError(Exception):
    """Backend недоступен (PyOpenMagnetics не установлен / .so не найден)."""


class LeakageInductanceAnalyzerFailedError(Exception):
    """
    Backend стартовал, но fail'нул.

    Типовые причины:
    - `component.section_layout is None` (leakage требует explicit layout);
    - bobbin геометрия не позволяет уложить turns с заданным wire;
    - PyOM эмитит exception-as-data (см. T132 Analyze §W1).
    """


class LeakageInductanceAnalyzer(Protocol):
    """Расчёт leakage inductance Lσ через outbound port."""

    async def calculate_leakage_inductance(
        self,
        component: MagneticComponent,
        source_winding: str | None = None,
    ) -> LeakageInductanceResult:
        """
        Вычислить leakage от `source_winding` ко всем остальным обмоткам.

        `source_winding=None` — используется `component.primary_winding.name`.
        Возвращает `LeakageInductanceResult` с `leakage_to[target] = Lσ [H]`
        для каждой target обмотки и единым `coupling_factor` k.

        Бросает `LeakageInductanceAnalyzerUnavailableError`, если backend
        не доступен; `LeakageInductanceAnalyzerFailedError` — при runtime
        ошибке (отсутствие `section_layout`, несовместимая геометрия,
        unknown source_winding name, и т.п.).
        """
        ...
