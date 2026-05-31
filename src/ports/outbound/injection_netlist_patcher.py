"""
InjectionNetlistPatcher — outbound port для SPICE netlist topology
surgery в контексте loop-gain measurement (T153, ADR-T153c).

Семантически отделён от `NetlistEditor` (T131), который занимается
sourcing / library inclusion. Здесь — четыре операции, нужные
strategy-impl для loop-gain injection:

* `insert_voltage_source` — Middlebrook voltage method.
* `insert_current_source` — Middlebrook current method.
* `open_break` / `short_break` — Rosenstark return-ratio method.

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
        source_ref: str,
        ac_magnitude: float = 1.0,
    ) -> NetlistPatchResult:
        """
        Middlebrook voltage injection.

        Разрезать петлю в `break_node`: split нод на N_left / N_right,
        вставить `<source_ref> N_left N_right AC <ac_magnitude> 0`.
        Probe pair — voltage traces fwd (N_left) и rev (N_right).

        Raises:
            ValueError: break_node не найден / некорректный netlist.

        """
        ...

    def insert_current_source(
        self,
        netlist: str,
        *,
        break_node: str,
        source_ref: str,
        ac_magnitude: float = 1.0,
    ) -> NetlistPatchResult:
        """
        Middlebrook current injection.

        Вставить current source параллельно в `break_node` + probe-
        резисторы 0 Ω для current measurement (`i(R_fwd)`, `i(R_rev)`).

        Raises:
            ValueError: break_node не найден.

        """
        ...

    def open_break(
        self,
        netlist: str,
        *,
        break_node: str,
    ) -> NetlistPatchResult:
        """
        Rosenstark: разрезать петлю в `break_node` (open-circuit).

        Probe pair — fwd = драйв-сигнал, rev = open-circuit response
        в зависающем конце петли.

        Raises:
            ValueError: break_node не найден.

        """
        ...

    def short_break(
        self,
        netlist: str,
        *,
        break_node: str,
        gnd_node: str = '0',
    ) -> NetlistPatchResult:
        """
        Rosenstark: закоротить `break_node` на `gnd_node` (short-circuit).

        Probe pair — fwd = драйв-сигнал, rev = short-circuit response.

        Raises:
            ValueError: break_node не найден.

        """
        ...
