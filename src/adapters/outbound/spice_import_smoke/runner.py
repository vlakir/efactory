"""
NgspiceSmokeRunner — T030 adapter.

Per-class fixture-driven OP analysis на свежеустановленной модели.
Acceptance: модель парсится ngspice'ом и transistor/diode/opamp выходит
из нулевого bias (i.e. модель синтаксически валидна и физически biased).

TUBE / TRANSFORMER / LOAD категории — skipped (основной flow для них
не URL-import, но import технически возможен).
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Final

from domain.simulation import OpAnalysis
from domain.spice_import import (
    SmokeFailedError,
    SmokeOutcome,
    SmokeStatus,
    SmokeTimeoutError,
)
from domain.spice_model import (
    BjtKind,
    ComponentCategory,
    JfetKind,
    MosfetKind,
)
from ports.outbound.simulator import SimulationFailedError, SimulatorUnavailableError

if TYPE_CHECKING:
    from adapters.outbound.ngspice.simulator import NgspiceSimulator
    from domain.spice_import import ClassificationResult, ParsedModelCard


_SKIP_CATEGORIES: Final = frozenset(
    {
        ComponentCategory.TUBE,
        ComponentCategory.TRANSFORMER,
        ComponentCategory.LOAD,
    },
)


class NgspiceSmokeRunner:
    def __init__(self, *, simulator: NgspiceSimulator) -> None:
        self._sim = simulator

    async def smoke(
        self,
        *,
        card: ParsedModelCard,
        classification: ClassificationResult,
        model_path: Path,
        timeout_seconds: float,
    ) -> SmokeOutcome:
        if classification.category in _SKIP_CATEGORIES:
            return SmokeOutcome(
                card_name=card.name,
                status=SmokeStatus.SKIPPED,
                details=f'category={classification.category.value} smoke unsupported',
            )

        try:
            template = _render_template(
                card=card,
                classification=classification,
                model_path=model_path,
            )
        except _NoSmokeTemplateError as exc:
            return SmokeOutcome(
                card_name=card.name,
                status=SmokeStatus.SKIPPED,
                details=str(exc),
            )

        with tempfile.TemporaryDirectory(prefix='spice-smoke-') as tmp:
            netlist = Path(tmp) / 'smoke.cir'
            netlist.write_text(template)
            try:
                result = await self._sim.run(
                    netlist,
                    OpAnalysis(),
                    timeout_seconds=timeout_seconds,
                )
            except SimulatorUnavailableError as exc:
                raise SmokeFailedError(
                    card_name=card.name,
                    stdout='',
                    stderr=str(exc),
                ) from exc
            except TimeoutError as exc:
                raise SmokeTimeoutError(
                    card_name=card.name,
                    timeout_seconds=timeout_seconds,
                ) from exc
            except SimulationFailedError as exc:
                raise SmokeFailedError(
                    card_name=card.name,
                    stdout='',
                    stderr=str(exc),
                ) from exc

        op = result.operating_points or {}
        details = _verify(op=op, classification=classification)
        return SmokeOutcome(
            card_name=card.name,
            status=SmokeStatus.PASSED,
            details=details,
        )


class _NoSmokeTemplateError(Exception):
    """Internal — нет шаблона для данной (category, subcategory)."""


_TemplateFn = Callable[[str, str], str]


def _tpl_bjt_npn(name: str, inc: str) -> str:
    return (
        f'* smoke NPN CE\n{inc}'
        f'VCC vcc 0 DC 10\nVB vb 0 DC 2\n'
        f'Rb vb b 100k\nRc vcc c 1k\n'
        f'Q1 c b 0 {name}\n.end\n'
    )


def _tpl_bjt_pnp(name: str, inc: str) -> str:
    return (
        f'* smoke PNP CE (emitter @ +V)\n{inc}'
        f'VEE vee 0 DC 10\nVB vb 0 DC 8\n'
        f'Rb vb b 100k\nRc c 0 1k\n'
        f'Q1 c b vee {name}\n.end\n'
    )


def _tpl_jfet_njf(name: str, inc: str) -> str:
    return (
        f'* smoke NJF CS (depletion-mode, Vgs<0)\n{inc}'
        f'VDD vdd 0 DC 10\nVG vg 0 DC -0.5\n'
        f'Rg vg g 1MEG\nRd vdd d 1k\n'
        f'J1 d g 0 {name}\n.end\n'
    )


def _tpl_jfet_pjf(name: str, inc: str) -> str:
    return (
        f'* smoke PJF CS\n{inc}'
        f'VSS vss 0 DC 10\nVG vg 0 DC 9.5\n'
        f'Rg vg g 1MEG\nRd d 0 1k\n'
        f'J1 d g vss {name}\n.end\n'
    )


def _tpl_mosfet_nmos(name: str, inc: str) -> str:
    return (
        f'* smoke NMOS CS\n{inc}'
        f'VDD vdd 0 DC 10\nVG vg 0 DC 5\n'
        f'Rg vg g 1MEG\nRd vdd d 1k\n'
        f'M1 d g 0 0 {name}\n.end\n'
    )


def _tpl_mosfet_pmos(name: str, inc: str) -> str:
    return (
        f'* smoke PMOS CS\n{inc}'
        f'VSS vss 0 DC 10\nVG vg 0 DC 5\n'
        f'Rg vg g 1MEG\nRd d 0 1k\n'
        f'M1 d g vss vss {name}\n.end\n'
    )


def _tpl_diode(name: str, inc: str) -> str:
    return (
        f'* smoke diode forward\n{inc}V1 vp 0 DC 5\nR1 vp a 1k\nD1 a 0 {name}\n.end\n'
    )


_TEMPLATES: Final[dict[tuple[ComponentCategory, str], _TemplateFn]] = {
    (ComponentCategory.BJT, BjtKind.NPN.value): _tpl_bjt_npn,
    (ComponentCategory.BJT, BjtKind.PNP.value): _tpl_bjt_pnp,
    (ComponentCategory.JFET, JfetKind.NJF.value): _tpl_jfet_njf,
    (ComponentCategory.JFET, JfetKind.PJF.value): _tpl_jfet_pjf,
    (ComponentCategory.MOSFET, MosfetKind.NMOS.value): _tpl_mosfet_nmos,
    (ComponentCategory.MOSFET, MosfetKind.PMOS.value): _tpl_mosfet_pmos,
}


def _render_template(
    *,
    card: ParsedModelCard,
    classification: ClassificationResult,
    model_path: Path,
) -> str:
    """Per-class smoke netlist template."""
    category = classification.category
    subcategory = classification.subcategory
    include_line = f'.include "{model_path}"\n'

    if (category, subcategory) in _TEMPLATES:
        return _TEMPLATES[(category, subcategory)](card.name, include_line)
    if category is ComponentCategory.DIODE:
        # Все subcategory диода (signal/schottky/zener/...) — один template.
        return _tpl_diode(card.name, include_line)
    if category is ComponentCategory.OPAMP:
        pins = card.pins or ()
        return _render_opamp_buffer(card.name, include_line, pins)
    msg = f'no smoke template for {category}/{subcategory}'
    raise _NoSmokeTemplateError(msg)


def _render_opamp_buffer(
    name: str,
    inc: str,
    pins: tuple[str, ...],
) -> str:
    """Unity-gain buffer вокруг op-amp SUBCKT, с auto-detect pin order."""
    role_of = _detect_opamp_roles(pins)
    nodes = _assign_opamp_nodes(pins, role_of)
    return (
        f'* smoke op-amp unity buffer\n{inc}'
        f'VCC vcc 0 DC 10\nVEE vee 0 DC -10\nVIN vin 0 DC 1\n'
        f'X1 {" ".join(nodes)} {name}\n.end\n'
    )


def _detect_opamp_roles(pins: tuple[str, ...]) -> dict[str, int]:
    role_of: dict[str, int] = {}
    for idx, p in enumerate(pin.upper() for pin in pins):
        if p in {'V+', 'VCC', 'VS+'}:
            role_of['vcc'] = idx
        elif p in {'V-', 'VEE', 'VS-'}:
            role_of['vee'] = idx
        elif p in {'INP', 'IN+', '+IN'}:
            role_of['inp'] = idx
        elif p in {'INM', 'IN-', '-IN'}:
            role_of['inm'] = idx
        elif p == 'OUT':
            role_of['out'] = idx
    return role_of


def _assign_opamp_nodes(
    pins: tuple[str, ...],
    role_of: dict[str, int],
) -> list[str]:
    if {'vcc', 'vee', 'inp', 'inm', 'out'}.issubset(role_of):
        mapping = {
            role_of['vcc']: 'vcc',
            role_of['vee']: 'vee',
            role_of['inp']: 'vin',
            role_of['inm']: 'vout',  # feedback в buffer
            role_of['out']: 'vout',
        }
    else:
        # Fallback positional: assume (VCC, VEE, INP, INM, OUT).
        fallback = ('vcc', 'vee', 'vin', 'vout', 'vout')
        mapping = dict(enumerate(fallback[: len(pins)]))
    return [mapping[i] for i in range(len(pins))]


_VERIFY_KEY: Final[dict[ComponentCategory, str]] = {
    ComponentCategory.BJT: 'v(c)',
    ComponentCategory.JFET: 'v(d)',
    ComponentCategory.MOSFET: 'v(d)',
    ComponentCategory.DIODE: 'v(a)',
    ComponentCategory.OPAMP: 'v(vout)',
}


def _verify(
    *,
    op: dict[str, float],
    classification: ClassificationResult,
) -> str:
    """Soft details-строка по OP-точкам (без жёстких assertion'ов)."""
    key = _VERIFY_KEY.get(classification.category)
    if key is None:
        return f'OP keys={sorted(op)[:5]}'
    return f'OP ok, {key}={op.get(key)}'
