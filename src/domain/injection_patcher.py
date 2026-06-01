"""
InjectionNetlistPatcher — SPICE netlist topology surgery для loop-gain
measurement (T153, ADR-T153c + ADR-T153d edge-vs-node refinement
2026-06-01).

Protocol живёт в `domain/`, а не в `ports/outbound/`, чтобы
`domain.phase_margin_injection` мог импортировать его без нарушения
hexagonal layers (domain не имеет права import port — T153 B.6 fix).
Adapter (`adapters/outbound/ngspice/injection_patcher.py`) реализует
Protocol structurally — оставлять port в `ports/` как тонкий
re-export не нужно, contracts по-прежнему работают через structural
typing.

Семантически отделён от `NetlistEditor` (T131), который занимается
sourcing / library inclusion. Здесь — четыре операции, нужные
strategy-impl для loop-gain injection:

* `insert_voltage_source` — Middlebrook voltage method.
* `insert_current_source` — Middlebrook current method.
* `open_break` / `short_break` — Rosenstark return-ratio method.

Break контракт определяется парой `(break_node, break_element_ref)`
— ровно один wire в circuit graph (ADR-T153d). Adapter режет именно
в строке элемента `break_element_ref` — переименовывает в ней ссылку
на `break_node` в `<break_node>__fwd`, остальные ссылки на
`break_node` не трогает.

Adapter: `NgspiceInjectionNetlistPatcher` (T153 Phase B.3, в
`adapters/outbound/ngspice/`).
"""

from __future__ import annotations

from typing import Annotated, Protocol

from pydantic import BaseModel, ConfigDict, Field

_FROZEN = ConfigDict(frozen=True, extra='forbid')


class ProbePair(BaseModel):
    """
    Имена fwd/rev traces в результирующем AC sweep'е.

    Strategy в `combine()` использует именно эти имена для извлечения
    complex-значений из `AcSweep.traces_real` / `traces_imag`. Adapter
    решает naming (ngspice-style 'v(node)' / 'i(element)').
    """

    model_config = _FROZEN

    fwd: Annotated[str, Field(min_length=1)]
    rev: Annotated[str, Field(min_length=1)]


class NetlistPatchResult(BaseModel):
    """Результат единичного patch'а netlist'а: модифицированный текст + probe."""

    model_config = _FROZEN

    patched_netlist: Annotated[str, Field(min_length=1)]
    probe_pair: ProbePair


class InjectionNetlistPatcher(Protocol):
    """Topology surgery поверх SPICE netlist'а."""

    def insert_voltage_source(
        self,
        netlist: str,
        *,
        break_node: str,
        break_element_ref: str,
        source_ref: str,
        ac_magnitude: float = 1.0,
    ) -> NetlistPatchResult:
        """
        Middlebrook voltage injection.

        Разрезать loop в edge `(break_node, break_element_ref)`:
        переименовать в строке элемента `break_element_ref` ссылку
        на `break_node` в `<break_node>__fwd`; вставить
        `<source_ref> <break_node>__fwd <break_node> AC <ac_magnitude> 0`.
        Probe pair — voltage traces fwd (`v(<break_node>__fwd)`) и
        rev (`v(<break_node>)`).

        Raises:
            ValueError: break_node не найден / break_element_ref не
                найден / `break_node` не присутствует в строке этого
                элемента / некорректный netlist.

        """
        ...

    def insert_current_source(
        self,
        netlist: str,
        *,
        break_node: str,
        break_element_ref: str,
        source_ref: str,
        ac_magnitude: float = 1.0,
    ) -> NetlistPatchResult:
        """
        Middlebrook current injection.

        Edge `(break_node, break_element_ref)` режется аналогично
        voltage-injection; вместо voltage source — current source +
        probe-резисторы 0 Ω для current measurement
        (`i(R_fwd)`, `i(R_rev)`).

        Raises:
            ValueError: break_node / break_element_ref не найден.

        """
        ...

    def open_break(
        self,
        netlist: str,
        *,
        break_node: str,
        break_element_ref: str,
    ) -> NetlistPatchResult:
        """
        Rosenstark: разрезать loop в edge `(break_node,
        break_element_ref)` (open-circuit).

        Probe pair — fwd = драйв-сигнал (`v(<break_node>__fwd)`),
        rev = open-circuit response в зависающем конце петли
        (`v(<break_node>)`).

        Raises:
            ValueError: break_node / break_element_ref не найден.

        """
        ...

    def short_break(
        self,
        netlist: str,
        *,
        break_node: str,
        break_element_ref: str,
        gnd_node: str = '0',
    ) -> NetlistPatchResult:
        """
        Rosenstark: edge `(break_node, break_element_ref)` режется,
        response-сторона короче на `gnd_node` (short-circuit).

        Probe pair — fwd = ток драйв-источника, rev = ток короткой
        перемычки на gnd.

        Raises:
            ValueError: break_node / break_element_ref не найден.

        """
        ...
