"""
analyze_interleaved_leakage — use case для interleaved OPT leakage Lσ (T132).

Тонкий orchestration слой поверх `LeakageInductanceAnalyzer` port'а:
валидирует presence of `section_layout` на componenente (fail-loud если
None — spec Q9), затем делегирует расчёт adapter'у. Backend (analytical
formula / future FEM) скрыт за Protocol.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.magnetic import LeakageInductanceResult, MagneticComponent
    from ports.outbound.leakage_inductance_analyzer import (
        LeakageInductanceAnalyzer,
    )


async def analyze_interleaved_leakage(
    *,
    component: MagneticComponent,
    analyzer: LeakageInductanceAnalyzer,
    source_winding: str | None = None,
) -> LeakageInductanceResult:
    """
    Вычислить leakage Lσ от `source_winding` ко всем остальным обмоткам.

    Args:
        component: magnetic component spec. `section_layout` обязателен
            (None → ValueError, spec Q9 fail-loud).
        analyzer: `LeakageInductanceAnalyzer` port (analytical backend
            по умолчанию, см. composition).
        source_winding: имя обмотки-источника. None → primary winding.

    Returns:
        `LeakageInductanceResult` с per-target Lσ + coupling_factor.

    Raises:
        ValueError: если `component.section_layout is None`.
        Backend errors (`LeakageInductanceAnalyzerFailedError`) propagate
        as-is через port.

    """
    if component.section_layout is None:
        msg = (
            f'analyze_interleaved_leakage для {component.name!r}: '
            f'section_layout обязателен (interleaved расчёт без '
            f'explicit layout не определён, см. T132 spec §Q9)'
        )
        raise ValueError(msg)

    return await analyzer.calculate_leakage_inductance(
        component,
        source_winding=source_winding,
    )


__all__ = ['analyze_interleaved_leakage']
