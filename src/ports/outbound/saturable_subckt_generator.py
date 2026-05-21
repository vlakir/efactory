"""
SaturableSubcktGenerator — outbound port для SPICE saturable transformer
subckt (T131 Phase E architecture cleanup).

Изолирует use case `analyze_distortion_spectrum` от конкретного SPICE-
формата generator'а (XSPICE gyrator-capacitor lcouple+core в дефолтной
implementation, но возможны альтернативы — Jiles-Atherton CORE model,
custom B-source PWL для тестирования и т.п.).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.material import FrohlichBHCurve


class SaturableSubcktGenerator(Protocol):
    """Генератор ngspice `.subckt`-текста для saturable transformer."""

    def generate(
        self,
        *,
        subckt_name: str,
        n_primary: int,
        n_secondary: int,
        a_core_m2: float,
        l_path_m: float,
        r_primary_ohm: float,
        r_secondary_ohm: float,
        bh_curve: FrohlichBHCurve,
    ) -> str:
        """
        Сгенерировать subckt-текст с 4 терминалами (P1, P2, S1, S2).

        Args:
            subckt_name: имя subckt'а, должно совпадать с именем
                X-инстанса в netlist'е, который заменяет.
            n_primary: количество витков первичной обмотки.
            n_secondary: количество витков вторичной обмотки.
            a_core_m2: cross-section area, м² (>0).
            l_path_m: mean magnetic path length, м (>0).
            r_primary_ohm: DCR первичной обмотки, Ω (≥0).
            r_secondary_ohm: DCR вторичной обмотки, Ω (≥0).
            bh_curve: B-H curve материала.

        Returns:
            Text subckt'а для inline-substitution в netlist.

        Raises:
            ValueError: при невалидных входах.

        """
        ...
