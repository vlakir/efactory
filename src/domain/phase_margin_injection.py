"""
Injection strategies для loop-gain measurement (T153 Phase B.2).

`InjectionStrategy` ABC + 4 concrete impl:

* `MiddlebrookVoltageStrategy` — single sweep, `T = -V_rev/V_fwd`.
* `MiddlebrookCurrentStrategy` — single sweep, `T = -I_rev/I_fwd`.
* `TianStrategy` — два sweeps (V+I), `T = (T_v·T_i − 1)/(T_v + T_i + 2)`.
* `RosenstarkReturnRatioStrategy` — два sweeps (OC+SC),
  `T = (T_oc·T_sc + T_oc + T_sc)/(T_oc·T_sc − 1)`.

Strategy инжектирует `InjectionNetlistPatcher` (ADR-T153c) в
конструктор и делегирует patching netlist'а — domain не знает SPICE
syntax. Combine math чисто-арифметическая (pure).

Источники методологий: Middlebrook R.D., IJE 38(4), 1975; Tian M.
et al., IEEE C&D Mag. 17(1), 2001; Rosenstark S., IJE 57(3), 1984.

Note (T153 Phase C): Tian / Rosenstark combine-формулы — hypothesis,
verified TDD-style cross-validation на reference op-amp circuit
(IEEE papers за paywall, WebFetch недоступен).
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ports.outbound.injection_netlist_patcher import (
    NetlistPatchResult,
    ProbePair,
)

if TYPE_CHECKING:
    from domain.phase_margin import InjectionMethod
    from domain.simulation import AcSweep
    from ports.outbound.injection_netlist_patcher import InjectionNetlistPatcher


_FROZEN = ConfigDict(frozen=True, extra='forbid')


# ----------------------------------------------------- InjectionSetup ----


class InjectionSetup(BaseModel):
    """
    Результат `strategy.prepare()`: patched netlist'ы + probe-пары.

    Длина `patches` равна числу sweeps, нужных стратегии: 1 для
    Middlebrook V/I, 2 для Tian / Rosenstark.
    """

    model_config = _FROZEN

    patches: tuple[NetlistPatchResult, ...] = Field(min_length=1)


# ------------------------------------------------------------ LoopGain ----


class LoopGain(BaseModel):
    """
    T(jω) — комплексная контурная передача loop-gain.

    Хранится как параллельные tuples (frequency, real, imag) для
    consistency с `AcSweep`. Phase margin вычисляется downstream
    (Phase B.3 / B.4).
    """

    model_config = _FROZEN

    frequency: tuple[float, ...] = Field(min_length=1)
    real: tuple[float, ...]
    imag: tuple[float, ...]

    @model_validator(mode='after')
    def _check_consistency(self) -> Self:
        n = len(self.frequency)
        if len(self.real) != n:
            msg = (
                f'LoopGain: real has length {len(self.real)} but frequency '
                f'has length {n}.'
            )
            raise ValueError(msg)
        if len(self.imag) != n:
            msg = (
                f'LoopGain: imag has length {len(self.imag)} but frequency '
                f'has length {n}.'
            )
            raise ValueError(msg)
        prev = -1.0
        for idx, f in enumerate(self.frequency):
            if f <= 0.0:
                msg = (
                    f'LoopGain.frequency[{idx}]: {f!r} must be > 0 '
                    f'(monotonically increasing positive).'
                )
                raise ValueError(msg)
            if f <= prev:
                msg = (
                    f'LoopGain.frequency[{idx}]: {f!r} must be greater '
                    f'than previous frequency {prev!r}.'
                )
                raise ValueError(msg)
            prev = f
        for idx, v in enumerate(self.real):
            if not math.isfinite(v):
                msg = f'LoopGain.real[{idx}]: {v!r} must be finite (no NaN).'
                raise ValueError(msg)
        for idx, v in enumerate(self.imag):
            if not math.isfinite(v):
                msg = f'LoopGain.imag[{idx}]: {v!r} must be finite (no NaN).'
                raise ValueError(msg)
        return self


# ----------------------------------------- combine() helper functions ----


def _trace_complex(sweep: AcSweep, name: str) -> tuple[complex, ...]:
    if name not in sweep.traces_real:
        msg = (
            f'Trace {name!r} not present in AcSweep '
            f'(available: {sorted(sweep.traces_real)!r}).'
        )
        raise ValueError(msg)
    real = sweep.traces_real[name]
    imag = sweep.traces_imag[name]
    return tuple(complex(r, i) for r, i in zip(real, imag, strict=True))


def _loop_gain_from_complex(
    frequency: tuple[float, ...],
    t: tuple[complex, ...],
) -> LoopGain:
    return LoopGain(
        frequency=frequency,
        real=tuple(c.real for c in t),
        imag=tuple(c.imag for c in t),
    )


def _negated_ratio(sweep: AcSweep, probe: ProbePair) -> tuple[complex, ...]:
    """T = -trace(rev) / trace(fwd) — common Middlebrook math."""
    fwd = _trace_complex(sweep, probe.fwd)
    rev = _trace_complex(sweep, probe.rev)
    return tuple(-r / f for r, f in zip(rev, fwd, strict=True))


def _bare_ratio(sweep: AcSweep, probe: ProbePair) -> tuple[complex, ...]:
    """T = trace(rev) / trace(fwd) — Rosenstark (no inserted source)."""
    fwd = _trace_complex(sweep, probe.fwd)
    rev = _trace_complex(sweep, probe.rev)
    return tuple(r / f for r, f in zip(rev, fwd, strict=True))


def _expect_n_sweeps(
    sweeps: tuple[AcSweep, ...],
    setup: InjectionSetup,
    n: int,
    method: str,
) -> None:
    if len(sweeps) != n:
        msg = f'{method}: expected {n} sweep(s), got {len(sweeps)}.'
        raise ValueError(msg)
    if len(setup.patches) != n:
        msg = f'{method}: setup has {len(setup.patches)} patches, expected {n}.'
        raise ValueError(msg)


# ------------------------------------------- InjectionStrategy ABC ----


class InjectionStrategy(ABC):
    """
    Abstract base для loop-gain injection methodologies.

    `prepare(netlist, *, break_node, break_element_ref)` — edge задаётся
    парой `(node, element_ref)` (ADR-T153d, 2026-06-01).
    """

    method_name: ClassVar[InjectionMethod]

    @abstractmethod
    def prepare(
        self,
        netlist: str,
        *,
        break_node: str,
        break_element_ref: str,
    ) -> InjectionSetup:
        """Patch netlist по методологии strategy. Возвращает 1-2 patches."""

    @abstractmethod
    def combine(
        self,
        sweeps: tuple[AcSweep, ...],
        setup: InjectionSetup,
    ) -> LoopGain:
        """Свести AcSweep'ы в комплексную контурную передачу T(jω)."""


# --------------------------------- MiddlebrookVoltageStrategy ----


class MiddlebrookVoltageStrategy(InjectionStrategy):
    """Middlebrook 1975, voltage injection, single sweep."""

    method_name: ClassVar[InjectionMethod] = 'middlebrook_voltage'

    def __init__(self, patcher: InjectionNetlistPatcher) -> None:
        self._patcher = patcher

    def prepare(
        self,
        netlist: str,
        *,
        break_node: str,
        break_element_ref: str,
    ) -> InjectionSetup:
        result = self._patcher.insert_voltage_source(
            netlist,
            break_node=break_node,
            break_element_ref=break_element_ref,
            source_ref='Vinj',
            ac_magnitude=1.0,
        )
        return InjectionSetup(patches=(result,))

    def combine(
        self,
        sweeps: tuple[AcSweep, ...],
        setup: InjectionSetup,
    ) -> LoopGain:
        _expect_n_sweeps(sweeps, setup, 1, self.method_name)
        sweep = sweeps[0]
        t = _negated_ratio(sweep, setup.patches[0].probe_pair)
        return _loop_gain_from_complex(sweep.frequency, t)


# --------------------------------- MiddlebrookCurrentStrategy ----


class MiddlebrookCurrentStrategy(InjectionStrategy):
    """Middlebrook 1975, current injection, single sweep."""

    method_name: ClassVar[InjectionMethod] = 'middlebrook_current'

    def __init__(self, patcher: InjectionNetlistPatcher) -> None:
        self._patcher = patcher

    def prepare(
        self,
        netlist: str,
        *,
        break_node: str,
        break_element_ref: str,
    ) -> InjectionSetup:
        result = self._patcher.insert_current_source(
            netlist,
            break_node=break_node,
            break_element_ref=break_element_ref,
            source_ref='Iinj',
            ac_magnitude=1.0,
        )
        return InjectionSetup(patches=(result,))

    def combine(
        self,
        sweeps: tuple[AcSweep, ...],
        setup: InjectionSetup,
    ) -> LoopGain:
        _expect_n_sweeps(sweeps, setup, 1, self.method_name)
        sweep = sweeps[0]
        t = _negated_ratio(sweep, setup.patches[0].probe_pair)
        return _loop_gain_from_complex(sweep.frequency, t)


# ----------------------------------------------------- TianStrategy ----


class TianStrategy(InjectionStrategy):
    """
    Tian et al. 2001, symmetric voltage+current injection, two sweeps.

    `T = (T_v · T_i − 1) / (T_v + T_i + 2)`.
    """

    method_name: ClassVar[InjectionMethod] = 'tian'

    def __init__(self, patcher: InjectionNetlistPatcher) -> None:
        self._patcher = patcher
        self._v = MiddlebrookVoltageStrategy(patcher)
        self._i = MiddlebrookCurrentStrategy(patcher)

    def prepare(
        self,
        netlist: str,
        *,
        break_node: str,
        break_element_ref: str,
    ) -> InjectionSetup:
        v_setup = self._v.prepare(
            netlist,
            break_node=break_node,
            break_element_ref=break_element_ref,
        )
        i_setup = self._i.prepare(
            netlist,
            break_node=break_node,
            break_element_ref=break_element_ref,
        )
        return InjectionSetup(patches=v_setup.patches + i_setup.patches)

    def combine(
        self,
        sweeps: tuple[AcSweep, ...],
        setup: InjectionSetup,
    ) -> LoopGain:
        _expect_n_sweeps(sweeps, setup, 2, self.method_name)
        v_sweep, i_sweep = sweeps
        if v_sweep.frequency != i_sweep.frequency:
            msg = (
                f'{self.method_name}: V and I sweeps must share frequency '
                f'axis (V: {len(v_sweep.frequency)} pts, I: '
                f'{len(i_sweep.frequency)} pts).'
            )
            raise ValueError(msg)
        t_v = _negated_ratio(v_sweep, setup.patches[0].probe_pair)
        t_i = _negated_ratio(i_sweep, setup.patches[1].probe_pair)
        t = tuple(
            (tv * ti - 1) / (tv + ti + 2) for tv, ti in zip(t_v, t_i, strict=True)
        )
        return _loop_gain_from_complex(v_sweep.frequency, t)


# ----------------------------- RosenstarkReturnRatioStrategy ----


class RosenstarkReturnRatioStrategy(InjectionStrategy):
    """
    Rosenstark 1984, open-circuit + short-circuit topology mods.

    `T = (T_oc · T_sc + T_oc + T_sc) / (T_oc · T_sc − 1)`.
    """

    method_name: ClassVar[InjectionMethod] = 'rosenstark_return_ratio'

    def __init__(self, patcher: InjectionNetlistPatcher) -> None:
        self._patcher = patcher

    def prepare(
        self,
        netlist: str,
        *,
        break_node: str,
        break_element_ref: str,
    ) -> InjectionSetup:
        oc = self._patcher.open_break(
            netlist,
            break_node=break_node,
            break_element_ref=break_element_ref,
        )
        sc = self._patcher.short_break(
            netlist,
            break_node=break_node,
            break_element_ref=break_element_ref,
        )
        return InjectionSetup(patches=(oc, sc))

    def combine(
        self,
        sweeps: tuple[AcSweep, ...],
        setup: InjectionSetup,
    ) -> LoopGain:
        _expect_n_sweeps(sweeps, setup, 2, self.method_name)
        oc_sweep, sc_sweep = sweeps
        if oc_sweep.frequency != sc_sweep.frequency:
            msg = (
                f'{self.method_name}: OC and SC sweeps must share '
                f'frequency axis (OC: {len(oc_sweep.frequency)} pts, '
                f'SC: {len(sc_sweep.frequency)} pts).'
            )
            raise ValueError(msg)
        t_oc = _bare_ratio(oc_sweep, setup.patches[0].probe_pair)
        t_sc = _bare_ratio(sc_sweep, setup.patches[1].probe_pair)
        t = tuple(
            (oc * sc + oc + sc) / (oc * sc - 1)
            for oc, sc in zip(t_oc, t_sc, strict=True)
        )
        return _loop_gain_from_complex(oc_sweep.frequency, t)


__all__ = [
    'InjectionSetup',
    'InjectionStrategy',
    'LoopGain',
    'MiddlebrookCurrentStrategy',
    'MiddlebrookVoltageStrategy',
    'RosenstarkReturnRatioStrategy',
    'TianStrategy',
]
