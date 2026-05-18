"""
`Schematic` fluent facade — programmatic builder для `.kicad_sch` (T100).

Уровень абстракции: пользователь указывает координаты в миллиметрах
(KiCad-native), компоненты возвращают handles на пины (`pin_plus`,
`pin_a`, ...). `connect()` рисует Manhattan-маршрут (вертикаль + горизонталь),
`label()` ставит net-label по абсолютной координате.

Phase 0 namespace: Resistor (`Device:R`), Capacitor (`Device:C`),
VoltageSource DC (`Simulation_SPICE:VDC`), Ground (`power:GND`).
Auto-layout (grid) — Phase 1+; в Phase 0 пользователь даёт явные
координаты, повторяя layout текущих ручных фикстур.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from adapters.outbound.schematic_kicad.writer import KicadSchematicWriter
from domain.schematic import (
    ComponentSpec,
    JunctionSpec,
    LabelSpec,
    Position,
    SchematicSpec,
    WireSpec,
)

if TYPE_CHECKING:
    from pathlib import Path


# Локальные позиции пинов и lib_id для каждого known kind. Числа взяты
# из стандартной библиотеки KiCad (см. `lib_symbols/*.sexp`).
@dataclass(frozen=True)
class _PinLayout:
    name: str
    local: tuple[float, float]  # (x_mm, y_mm) до вращения


@dataclass(frozen=True)
class _LabelOffsets:
    """
    Absolute (post-rotation) offsets для Reference/Value текста.

    KiCad eeschema convention: text labels не вращаются с символом —
    placement в screen coords независимо от symbol rotation. Числа взяты
    из canonical KiCad save output, чтобы наш фасад писал layout как
    KiCad GUI после ручного placement.
    """

    ref: tuple[float, float]
    value: tuple[float, float]


_RESISTOR_PINS = (_PinLayout('1', (0.0, 3.81)), _PinLayout('2', (0.0, -3.81)))
_CAPACITOR_PINS = (_PinLayout('1', (0.0, 3.81)), _PinLayout('2', (0.0, -3.81)))
_VDC_PINS = (_PinLayout('1', (0.0, 5.08)), _PinLayout('2', (0.0, -5.08)))
_GND_PINS = (_PinLayout('1', (0.0, 0.0)),)
_PWR_FLAG_PINS = (_PinLayout('1', (0.0, 0.0)),)

# R/C Reference/Value — справа от horizontal-rendered body, разнесены по Y.
# Числа взяты из user-perfected layout (T100 Phase 0 final, KiCad 10 PPA save).
_RC_LABEL_OFFSETS = _LabelOffsets(ref=(1.016, -4.572), value=(1.016, -2.54))
# VDC — Reference/Value справа сбоку (canonical V1 in T008 fixture).
_VDC_LABEL_OFFSETS = _LabelOffsets(ref=(5.08, -1.27), value=(5.08, 1.27))
_GND_LABEL_OFFSETS = _LabelOffsets(ref=(0.0, 6.35), value=(0.0, 3.81))
# PWR_FLAG offsets под user-perfected layout (PWR_FLAG at rotation 180 на
# уровне GND): Reference над, Value под перевёрнутым символом.
_PWR_FLAG_LABEL_OFFSETS = _LabelOffsets(ref=(0.0, -1.9), value=(0.0, 6.096))

_VDC_DEFAULT_PROPERTIES = {
    'Sim.Pins': '1=+ 2=-',
    'Sim.Type': 'V',
    'Sim.Device': 'SPICE',
    'Sim.Library': '',
    'Sim.Params': 'dc=1 ac=1',
}


def _round_grid(value: float) -> float:
    """KiCad grid — 0.01 мм; устраняем float-jitter в pin coords."""
    return round(value, 2)


def _transform_pin(
    component_pos: Position,
    rotation_deg: float,
    local: tuple[float, float],
) -> Position:
    """CCW-вращение локального pin → абсолютные мм."""
    theta = math.radians(rotation_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    lx, ly = local
    gx = component_pos.x_mm + lx * cos_t - ly * sin_t
    gy = component_pos.y_mm + lx * sin_t + ly * cos_t
    return Position(x_mm=_round_grid(gx), y_mm=_round_grid(gy))


@dataclass(frozen=True)
class _ComponentHandle:
    """Базовый handle: координаты пинов вычислены, доступны по `pin_by_number`."""

    reference: str
    pin_positions: dict[str, Position]

    def pin_by_number(self, number: str) -> Position:
        try:
            return self.pin_positions[number]
        except KeyError as exc:
            available = sorted(self.pin_positions)
            msg = f'{self.reference}: no pin {number!r} (have {available})'
            raise KeyError(msg) from exc


@dataclass(frozen=True)
class Resistor(_ComponentHandle):
    @property
    def pin_a(self) -> Position:
        return self.pin_positions['1']

    @property
    def pin_b(self) -> Position:
        return self.pin_positions['2']


@dataclass(frozen=True)
class Capacitor(_ComponentHandle):
    @property
    def pin_a(self) -> Position:
        return self.pin_positions['1']

    @property
    def pin_b(self) -> Position:
        return self.pin_positions['2']


@dataclass(frozen=True)
class VoltageSourceDc(_ComponentHandle):
    @property
    def pin_plus(self) -> Position:
        return self.pin_positions['1']

    @property
    def pin_minus(self) -> Position:
        return self.pin_positions['2']


@dataclass(frozen=True)
class Ground(_ComponentHandle):
    @property
    def pin(self) -> Position:
        return self.pin_positions['1']


@dataclass(frozen=True)
class PwrFlag(_ComponentHandle):
    """Удовлетворяет ERC `power_pin_not_driven` для simulation-схем."""

    @property
    def pin(self) -> Position:
        return self.pin_positions['1']


def _to_position(at: tuple[float, float] | Position) -> Position:
    if isinstance(at, Position):
        return at
    return Position(x_mm=at[0], y_mm=at[1])


def _pin_positions(
    component_pos: Position,
    rotation: float,
    pins: tuple[_PinLayout, ...],
) -> dict[str, Position]:
    return {p.name: _transform_pin(component_pos, rotation, p.local) for p in pins}


def _label_positions(
    component_pos: Position,
    labels: _LabelOffsets,
) -> tuple[Position, Position]:
    ref = Position(
        x_mm=_round_grid(component_pos.x_mm + labels.ref[0]),
        y_mm=_round_grid(component_pos.y_mm + labels.ref[1]),
    )
    value = Position(
        x_mm=_round_grid(component_pos.x_mm + labels.value[0]),
        y_mm=_round_grid(component_pos.y_mm + labels.value[1]),
    )
    return ref, value


@dataclass
class Schematic:
    """Fluent builder: add компоненты → connect → label → save."""

    name: str
    _components: list[ComponentSpec] = field(default_factory=list)
    _wires: list[WireSpec] = field(default_factory=list)
    _junctions: list[JunctionSpec] = field(default_factory=list)
    _labels: list[LabelSpec] = field(default_factory=list)
    _pwr_counter: int = 0
    _flg_counter: int = 0

    def add_resistor(
        self,
        *,
        reference: str,
        value: str,
        at: tuple[float, float] | Position,
        rotation: float = 0.0,
    ) -> Resistor:
        position = _to_position(at)
        ref_pos, value_pos = _label_positions(position, _RC_LABEL_OFFSETS)
        self._components.append(
            ComponentSpec(
                lib_id='Device:R',
                reference=reference,
                value=value,
                position=position,
                rotation=rotation,
                pins=tuple(p.name for p in _RESISTOR_PINS),
                ref_position=ref_pos,
                value_position=value_pos,
                ref_rotation=rotation,
                value_rotation=rotation,
            ),
        )
        return Resistor(
            reference=reference,
            pin_positions=_pin_positions(position, rotation, _RESISTOR_PINS),
        )

    def add_capacitor(
        self,
        *,
        reference: str,
        value: str,
        at: tuple[float, float] | Position,
        rotation: float = 0.0,
    ) -> Capacitor:
        position = _to_position(at)
        ref_pos, value_pos = _label_positions(position, _RC_LABEL_OFFSETS)
        self._components.append(
            ComponentSpec(
                lib_id='Device:C',
                reference=reference,
                value=value,
                position=position,
                rotation=rotation,
                pins=tuple(p.name for p in _CAPACITOR_PINS),
                ref_position=ref_pos,
                value_position=value_pos,
                ref_rotation=rotation,
                value_rotation=rotation,
            ),
        )
        return Capacitor(
            reference=reference,
            pin_positions=_pin_positions(position, rotation, _CAPACITOR_PINS),
        )

    def add_v_dc(
        self,
        *,
        reference: str,
        value: str,
        at: tuple[float, float] | Position,
        rotation: float = 0.0,
    ) -> VoltageSourceDc:
        position = _to_position(at)
        properties = dict(_VDC_DEFAULT_PROPERTIES)
        properties['Sim.Params'] = f'dc={value} ac=1'
        ref_pos, value_pos = _label_positions(position, _VDC_LABEL_OFFSETS)
        self._components.append(
            ComponentSpec(
                lib_id='Simulation_SPICE:VDC',
                reference=reference,
                value=value,
                position=position,
                rotation=rotation,
                properties=properties,
                pins=tuple(p.name for p in _VDC_PINS),
                ref_position=ref_pos,
                value_position=value_pos,
            ),
        )
        return VoltageSourceDc(
            reference=reference,
            pin_positions=_pin_positions(position, rotation, _VDC_PINS),
        )

    def add_ground(
        self,
        *,
        at: tuple[float, float] | Position,
        reference: str | None = None,
    ) -> Ground:
        position = _to_position(at)
        if reference is None:
            self._pwr_counter += 1
            reference = f'#PWR{self._pwr_counter:02d}'
        ref_pos, value_pos = _label_positions(position, _GND_LABEL_OFFSETS)
        self._components.append(
            ComponentSpec(
                lib_id='power:GND',
                reference=reference,
                value='GND',
                position=position,
                rotation=0.0,
                pins=tuple(p.name for p in _GND_PINS),
                ref_position=ref_pos,
                value_position=value_pos,
            ),
        )
        return Ground(
            reference=reference,
            pin_positions=_pin_positions(position, 0.0, _GND_PINS),
        )

    def add_pwr_flag(
        self,
        *,
        at: tuple[float, float] | Position,
        rotation: float = 0.0,
        reference: str | None = None,
    ) -> PwrFlag:
        """
        `power:PWR_FLAG` symbol для удовлетворения ERC `power_pin_not_driven`.

        `rotation`: 0 — стрелка вверх (default), 180 — стрелка вниз (placement
        под GND на одном уровне, см. user-perfected RC fixture).
        """
        position = _to_position(at)
        if reference is None:
            self._flg_counter += 1
            reference = f'#FLG{self._flg_counter:02d}'
        ref_pos, value_pos = _label_positions(position, _PWR_FLAG_LABEL_OFFSETS)
        self._components.append(
            ComponentSpec(
                lib_id='power:PWR_FLAG',
                reference=reference,
                value='PWR_FLAG',
                position=position,
                rotation=rotation,
                pins=tuple(p.name for p in _PWR_FLAG_PINS),
                ref_position=ref_pos,
                value_position=value_pos,
            ),
        )
        return PwrFlag(
            reference=reference,
            pin_positions=_pin_positions(position, rotation, _PWR_FLAG_PINS),
        )

    def connect(self, start: Position, end: Position) -> None:
        """
        Соединить две точки Manhattan-маршрутом (вертикаль → горизонталь).

        Если точки collinear (общий x или y) — один сегмент. Иначе — два
        сегмента через corner `(start.x, end.y)`.
        """
        if start == end:
            return
        if math.isclose(start.x_mm, end.x_mm) or math.isclose(
            start.y_mm,
            end.y_mm,
        ):
            self._wires.append(WireSpec(start=start, end=end))
            return
        corner = Position(x_mm=start.x_mm, y_mm=end.y_mm)
        self._wires.append(WireSpec(start=start, end=corner))
        self._wires.append(WireSpec(start=corner, end=end))

    def junction(self, at: tuple[float, float] | Position) -> None:
        self._junctions.append(JunctionSpec(at=_to_position(at)))

    def label(self, text: str, *, at: tuple[float, float] | Position) -> None:
        self._labels.append(LabelSpec(text=text, position=_to_position(at)))

    def to_spec(self) -> SchematicSpec:
        return SchematicSpec(
            name=self.name,
            components=tuple(self._components),
            wires=tuple(self._wires),
            junctions=tuple(self._junctions),
            labels=tuple(self._labels),
        )

    def save(self, path: Path) -> Path:
        return KicadSchematicWriter().write(self.to_spec(), path)


__all__ = [
    'Capacitor',
    'Ground',
    'Resistor',
    'Schematic',
    'VoltageSourceDc',
]
