"""
NetlistEditor — outbound port для SPICE netlist text manipulation
(T131 Phase E architecture cleanup).

Изолирует use case `analyze_distortion_spectrum` от ngspice-specific
текстовых паттернов (`.include` syntax, `SIN(...)` sourcing). Адаптер
для ngspice — `NgspiceNetlistEditor` в
`adapters/outbound/ngspice/netlist_substitution.py`.
"""

from __future__ import annotations

from typing import Protocol


class NetlistEditor(Protocol):
    """Text-level операции над SPICE netlist'ами."""

    def substitute_subckt_library(
        self,
        netlist_text: str,
        target_subckt_name: str,
        new_subckt_text: str,
    ) -> str:
        """
        Заменить library reference (`.include` или inline `.SUBCKT` block)
        с заданным subckt-name на новый subckt-текст.

        Идемпотентно: повторный вызов с тем же replacement — noop.

        Raises:
            ValueError: если target subckt не найден в netlist'е.

        """
        ...

    def set_sin_source_amplitude(
        self,
        netlist_text: str,
        *,
        source_ref: str,
        amplitude_peak: float,
        frequency_hz: float,
        offset: float = 0.0,
    ) -> str:
        """
        Переписать аргументы `SIN(...)` у указанного voltage source.

        Узлы и pre-SIN параметры (AC, DC, и т.п.) сохраняются;
        только аргументы внутри `SIN(...)` заменяются.

        Raises:
            ValueError: если source с таким ref не найден.

        """
        ...

    def ensure_ac_modifier(
        self,
        netlist_text: str,
        *,
        source_ref: str,
        ac_magnitude: float = 1.0,
    ) -> str:
        """
        Добавить `AC <magnitude>` modifier к V-source'у, если его ещё нет.

        Идемпотентно: при наличии любого `AC ...` параметра возвращает
        netlist без изменений (текущая magnitude сохраняется). Нужен для
        AC-based use case'ов (T023 measure_gain --mode small,
        measure_bandwidth) на фикстурах, где V-source изначально
        SIN-only / DC-only без AC modifier'а.

        Raises:
            ValueError: если source с таким ref не найден / empty ref /
                non-positive magnitude.

        """
        ...

    def find_top_level_v_sources(self, netlist_text: str) -> tuple[str, ...]:
        """
        Найти top-level V-source refs в netlist'е (исключая subckt-internal).

        Используется для auto-detect input source в T023 measure_*
        use case'ах (Clarify Q-G → c): если ровно один V-source —
        берётся он; иначе — caller обязан указать через `--input-source`.

        Returns:
            Tuple V-source refs в порядке появления (пустой если нет).

        """
        ...
