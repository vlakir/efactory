"""
Schematic — domain VO для programmatic `.kicad_sch` (T100 facade).

Адаптер `adapters.outbound.schematic_kicad` сериализует `SchematicSpec` в
KiCad 10 s-expression. Координаты — в миллиметрах, Y-down (KiCad eeschema
convention), как и принято внутренним форматом .kicad_sch.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Position(BaseModel):
    """Координата на канвасе KiCad, мм. Y-down (origin top-left)."""

    model_config = ConfigDict(frozen=True)

    x_mm: float
    y_mm: float


class PinRef(BaseModel):
    """Handle на конкретный pin компонента — `(reference, pin_number)`."""

    model_config = ConfigDict(frozen=True)

    component_reference: str
    pin_number: str
    position: Position


class ComponentSpec(BaseModel):
    """
    Один экземпляр символа в схеме (R/C/V/GND/...).

    `lib_id` — KiCad library reference, например `Device:R`. Должен
    соответствовать ключу из embedded `lib_symbols/` snippets. `properties`
    — словарь дополнительных KiCad-полей (`Sim.Type`, `Sim.Params` и т.п.),
    идущих ПОСЛЕ обязательных `Reference`/`Value`/`Footprint`/`Datasheet`.
    `pins` — упорядоченный список pin-номеров символа (нужен для генерации
    `(pin "n" (uuid ...))` блоков внутри symbol).
    """

    model_config = ConfigDict(frozen=True)

    lib_id: str
    reference: str
    value: str
    position: Position
    rotation: float = 0.0
    properties: dict[str, str] = Field(default_factory=dict)
    pins: tuple[str, ...]
    # Multi-unit symbol index. Default 1 — single-unit символы и тело
    # multi-unit (например, EL84 unit 1 = пентод-body, unit 2 = filament).
    # Headless-SPICE без накала: используем только unit 1, filament не
    # инстанцируется и не рисуется.
    unit: int = 1
    # Координаты Reference/Value текста (absolute). Если None — writer
    # ставит на `position` (overlap с символом). Фасад заполняет через
    # `_LabelOffsets` под каждый component kind.
    ref_position: Position | None = None
    value_position: Position | None = None
    # Rotation в `(property ... (at x y rot))` — KiCad GUI ставит =
    # symbol rotation. Безопасные значения {0, 90, 180, 270}; отрицательные
    # вешают GUI с OOM (T100 incident).
    ref_rotation: float = 0.0
    value_rotation: float = 0.0


class WireSpec(BaseModel):
    """
    Прямой сегмент провода `(wire (pts (xy ...) (xy ...)))`.

    Manhattan-маршрутизация (вертикаль + горизонталь) реализуется фасадом
    как последовательность `WireSpec` с общей промежуточной точкой;
    domain хранит только один линейный сегмент.
    """

    model_config = ConfigDict(frozen=True)

    start: Position
    end: Position

    @model_validator(mode='after')
    def _check_not_degenerate(self) -> Self:
        if self.start == self.end:
            msg = f'WireSpec: zero-length segment at {self.start}'
            raise ValueError(msg)
        return self


class JunctionSpec(BaseModel):
    """Точка соединения трёх+ wire'ов: `(junction (at x y))`."""

    model_config = ConfigDict(frozen=True)

    at: Position


class LabelSpec(BaseModel):
    """
    Локальный net label — даёт имя цепи, доступное в SPICE netlist'е.

    KiCad экспортирует `(label "in")` как net `/in` (slash-prefix —
    convention KiCad SPICE writer'а).
    """

    model_config = ConfigDict(frozen=True)

    text: str
    position: Position


class TextSpec(BaseModel):
    """
    Schematic-text node — несёт SPICE-директивы (`.tran`, `.ac`, `.op` ...).

    Если `text` начинается с `.`, KiCad SPICE-writer включает его в
    netlist как директиву. `exclude_from_sim no` (всегда выставляется
    writer'ом) обязателен — иначе текст считается декоративным.
    """

    model_config = ConfigDict(frozen=True)

    text: str
    position: Position


class SchematicSpec(BaseModel):
    """
    Полное содержимое одного листа `.kicad_sch`.

    `name` идёт в `(instances (project "<name>" ...))` блок каждого
    symbol — KiCad связывает root project с UUID листа.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    components: tuple[ComponentSpec, ...] = ()
    wires: tuple[WireSpec, ...] = ()
    junctions: tuple[JunctionSpec, ...] = ()
    labels: tuple[LabelSpec, ...] = ()
    texts: tuple[TextSpec, ...] = ()
