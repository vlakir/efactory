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
    TextSpec,
    WireSpec,
)
from domain.spice_model import ComponentCategory

if TYPE_CHECKING:
    from pathlib import Path

    from domain.spice_model import SpiceModel


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
_INDUCTOR_PINS = (_PinLayout('1', (0.0, 3.81)), _PinLayout('2', (0.0, -3.81)))
_VDC_PINS = (_PinLayout('1', (0.0, 5.08)), _PinLayout('2', (0.0, -5.08)))
_VAC_PINS = (_PinLayout('1', (0.0, 5.08)), _PinLayout('2', (0.0, -5.08)))
# Diode (Simulation_SPICE:D) — horizontal: pin 1 K слева, pin 2 A справа.
_DIODE_PINS = (_PinLayout('1', (-3.81, 0.0)), _PinLayout('2', (3.81, 0.0)))
_GND_PINS = (_PinLayout('1', (0.0, 0.0)),)
_PWR_FLAG_PINS = (_PinLayout('1', (0.0, 0.0)),)
# === ВНИМАНИЕ: Y-flip для asymmetric-по-Y компонентов ===
# KiCad symbol library использует Y-up convention (+Y = «вверху» в symbol),
# а .kicad_sch — Y-down. KiCad GUI инвертирует Y при placement, поэтому
# pin "C" Q_NPN в библиотеке at (2.54, +5.08) живёт в schematic at
# (cx+2.54, cy-5.08). Наш `_transform_pin` Y не инвертирует — это
# исторически работает для R/C/L/V_DC/V_AC/Diode (либо симметричны по Y,
# либо assertions используют abs()). Для НОВЫХ компонентов с Y-аsymmetry
# и assertion'ами по polarity (BJT/MOSFET/Conn) кодируем Y уже как
# schematic-abs offset (т.е. отрицательный Y от library).
#
# Известный side-effect для R/C/L/V_DC/V_AC: pin_plus у V_DC возвращает
# координату pin '1' (cy+5.08), но реальный «+» терминал в schematic at
# (cy-5.08) — т.е. наш pin_plus попадает на real pin '-'. Phase 0/1
# тесты этого не замечают (abs() в asserts); в новых тестах с активными
# компонентами обходится swap'ом подключения GND/supply (см. CE/SE-amp).
_BJT_PINS = (
    _PinLayout('B', (-5.08, 0.0)),
    _PinLayout('C', (2.54, -5.08)),
    _PinLayout('E', (2.54, 5.08)),
)
_MOSFET_PINS = (
    _PinLayout('G', (-5.08, 0.0)),
    _PinLayout('D', (2.54, -5.08)),
    _PinLayout('S', (2.54, 5.08)),
)
_CONN_01X04_PINS = (
    _PinLayout('1', (-5.08, -2.54)),
    _PinLayout('2', (-5.08, 0.0)),
    _PinLayout('3', (-5.08, 2.54)),
    _PinLayout('4', (-5.08, 5.08)),
)


@dataclass(frozen=True)
class _SymbolDef:
    """
    Описание ламповой `lib_id` из стандартной KiCad-библиотеки `Valve.*`.

    `pins` — physical pin'ы в порядке появления в registry; `spice_pin_names`
    параллельна `pins` и задаёт SPICE-имя для каждого физического pin'а
    (`Sim.Pins = '<num>=<name> ...'`). `unit` — индекс multi-unit символа;
    для headless-SPICE обычно `1` (body), filament-юниты (например, EL84
    unit 2 = F1/F2) не инстанцируем — KiCad их просто не рисует.

    Coords в `_PinLayout` уже **schematic-абсолютные** (Y-down), т.е.
    инвертированы относительно library symbol coords (которые Y-up).
    Pattern совпадает с BJT/MOSFET в этом же модуле.
    """

    lib_id: str
    pins: tuple[_PinLayout, ...]
    spice_pin_names: tuple[str, ...]
    unit: int
    label_offsets: _LabelOffsets


# EL84 (Valve.kicad_sym): multi-unit пентод. Unit 1 — тело (anode A pin 7,
# control grid G1 pin 2, cathode K_G3 pin 3, screen G2 pin 9). Unit 2 —
# накал F1/F2 (pins 4/5), не используется в headless-SPICE.
# Library-coords Y-up → schematic Y-down: знак Y инвертирован.
_VALVE_EL84 = _SymbolDef(
    lib_id='Valve:EL84',
    pins=(
        _PinLayout('2', (-7.62, 1.27)),  # G1 (control grid), library (-7.62, -1.27)
        _PinLayout('3', (-2.54, 8.89)),  # K_G3 (cathode), library (-2.54, -8.89)
        _PinLayout('7', (0.0, -11.43)),  # A (anode/plate), library (0.0, +11.43)
        _PinLayout('9', (7.62, -1.27)),  # G2 (screen), library (+7.62, +1.27)
    ),
    spice_pin_names=('G', 'K', 'P', 'G2'),
    unit=1,
    # Reference сверху-справа, Value снизу — canonical для Valve symbols.
    label_offsets=_LabelOffsets(ref=(7.62, -10.16), value=(7.62, 7.62)),
)

# Triode physical pin layout — общая геометрия для всех ECC*/EC* dual-
# triodes из Valve.kicad_sym (unit 1 = одна половина). Pin numbers
# разные, координаты одинаковые.
_TRIODE_LABEL_OFFSETS = _LabelOffsets(ref=(5.08, -8.89), value=(5.08, 7.62))

# ECC81 (T105) — 12AT7 dual-triode. Unit 1 pins: A=6, G=7, K=8.
# Маппинг для советских: 6Н1П (low-µ alternative), 6Н3П.
# Library coords Y-up → schematic Y-down (знак Y инвертирован).
_VALVE_ECC81 = _SymbolDef(
    lib_id='Valve:ECC81',
    pins=(
        _PinLayout('6', (0.0, -10.16)),  # A (anode)
        _PinLayout('7', (-7.62, 0.0)),  # G (grid)
        _PinLayout('8', (-2.54, 10.16)),  # K (cathode)
    ),
    spice_pin_names=('P', 'G', 'K'),
    unit=1,
    label_offsets=_TRIODE_LABEL_OFFSETS,
)

# ECC83 (12AX7) — pin-compatible с ECC81, derived (extends) в KiCad
# library. **Отложено в T105 Phase 1**: writer `_collect_lib_symbols`
# умеет авто-подгружать parent через `(extends ...)`, но KiCad pin
# resolution для derived `extends`-symbol работает иначе чем ожидалось
# (нашёл в попытке embed — pins NC при equal coords как у parent).
# Для 6Н2П сейчас используйте `Valve:ECC81` напрямую (pinout идентичен,
# отличается только µ — это в T006 SPICE модели).

# ECC88 (T105) — 6DJ8 dual-triode. Unit 1 pins: A=1, G=2, K=3.
# Маппинг для советских: 6Н23П, 6Н1П (alt).
_VALVE_ECC88 = _SymbolDef(
    lib_id='Valve:ECC88',
    pins=(
        _PinLayout('1', (0.0, -10.16)),
        _PinLayout('2', (-7.62, 0.0)),
        _PinLayout('3', (-2.54, 10.16)),
    ),
    spice_pin_names=('P', 'G', 'K'),
    unit=1,
    label_offsets=_TRIODE_LABEL_OFFSETS,
)

# EC92 (T105) — single-section triode (тоже встречается в KiCad lib).
# Unit 1 pins: A=1, G=6, K=7.
_VALVE_EC92 = _SymbolDef(
    lib_id='Valve:EC92',
    pins=(
        _PinLayout('1', (0.0, -10.16)),
        _PinLayout('6', (-7.62, 0.0)),
        _PinLayout('7', (-2.54, 10.16)),
    ),
    spice_pin_names=('P', 'G', 'K'),
    unit=1,
    label_offsets=_TRIODE_LABEL_OFFSETS,
)

# Transformer_1P_1S (T105/T103 follow-up, 2026-05-19) — generic 4-pin
# transformer: 1 primary (AA/AB) + 1 secondary (SA/SB). Pin coords
# (library Y-up → schematic Y-down):
#   1 (AA): library (-10.16, +5.08) → schematic (-10.16, -5.08), primary top
#   2 (AB): library (-10.16, -5.08) → schematic (-10.16, +5.08), primary bottom
#   3 (SA): library (+10.16, -5.08) → schematic (+10.16, +5.08), secondary bottom
#   4 (SB): library (+10.16, +5.08) → schematic (+10.16, -5.08), secondary top
# Маппинг для OPT_SE_5K_8 (`.SUBCKT P1 P2 S1 S2`): P1→1, P2→2, S1→3, S2→4.
_TRANSFORMER_1P_1S = _SymbolDef(
    lib_id='Device:Transformer_1P_1S',
    pins=(
        _PinLayout('1', (-10.16, -5.08)),  # AA primary top
        _PinLayout('2', (-10.16, 5.08)),  # AB primary bottom
        _PinLayout('3', (10.16, 5.08)),  # SA secondary bottom
        _PinLayout('4', (10.16, -5.08)),  # SB secondary top
    ),
    spice_pin_names=('P1', 'P2', 'S1', 'S2'),
    unit=1,
    # Reference / Value по бокам — canonical для Transformer_1P_1S.
    label_offsets=_LabelOffsets(ref=(0.0, -8.89), value=(0.0, 8.89)),
)

_SYMBOL_REGISTRY: dict[str, _SymbolDef] = {
    sym.lib_id: sym
    for sym in (
        _VALVE_EL84,
        _VALVE_ECC81,
        _VALVE_ECC88,
        _VALVE_EC92,
        _TRANSFORMER_1P_1S,
    )
}

# R/C/L Reference/Value — справа от horizontal-rendered body, разнесены по Y.
# Числа взяты из user-perfected layout (T100 Phase 0 final, KiCad 10 PPA save).
_RC_LABEL_OFFSETS = _LabelOffsets(ref=(1.016, -4.572), value=(1.016, -2.54))
_INDUCTOR_LABEL_OFFSETS = _RC_LABEL_OFFSETS  # тот же 2-pin вертикальный layout
# VDC/VAC — Reference/Value справа сбоку (canonical V1 in T008 fixture).
_VDC_LABEL_OFFSETS = _LabelOffsets(ref=(5.08, -1.27), value=(5.08, 1.27))
_VAC_LABEL_OFFSETS = _VDC_LABEL_OFFSETS
# Diode (horizontal symbol) — Reference над, Value под телом (canonical lib).
_DIODE_LABEL_OFFSETS = _LabelOffsets(ref=(0.0, -2.54), value=(0.0, 2.54))
_GND_LABEL_OFFSETS = _LabelOffsets(ref=(0.0, 6.35), value=(0.0, 3.81))
# PWR_FLAG offsets под user-perfected layout (PWR_FLAG at rotation 180 на
# уровне GND): Reference над, Value под перевёрнутым символом.
_PWR_FLAG_LABEL_OFFSETS = _LabelOffsets(ref=(0.0, -1.9), value=(0.0, 6.096))
# BJT/MOSFET: canonical KiCad lib defaults — Reference сверху-справа,
# Value снизу-справа от body.
_BJT_LABEL_OFFSETS = _LabelOffsets(ref=(5.08, 1.27), value=(5.08, -1.27))
_MOSFET_LABEL_OFFSETS = _BJT_LABEL_OFFSETS
# Conn_01x04: Reference сверху, Value снизу — canonical Connector_Generic.
_CONN_01X04_LABEL_OFFSETS = _LabelOffsets(ref=(0.0, 5.08), value=(0.0, -7.62))

# Sim.Device='V' (built-in voltage source) + Sim.Type='DC' — без Sim.Library.
# Пустая Sim.Library триггерит KiCad GUI warning «Не найдено определение
# модели симуляции» (blocks GUI Simulator run), хотя ngspice netlist при
# этом валидный. Convention идёт от VSIN (Phase 1) — без Sim.Library.
_VDC_DEFAULT_PROPERTIES = {
    'Sim.Pins': '1=+ 2=-',
    'Sim.Type': 'DC',
    'Sim.Device': 'V',
    'Sim.Params': 'dc=1 ac=1',
}

# Diode SPICE: KiCad symbol `Simulation_SPICE:D` (визуальный диод).
# Pin convention: 1=K (cathode), 2=A (anode) — Sim.Pins фиксирует это
# для SPICE-writer'а вне зависимости от visual rotation. Параметры
# модели либо inline через `spice_params` (D-primitive),  либо из
# `spice_model` (T101 library, subckt-instance).
_DIODE_SIM_PINS = '1=K 2=A'

# VSIN: sin-источник (Sim.Type=SIN) с встроенным Sim.Params в формате KiCad
# (`dc=0 ampl=X f=Y ac=1`). KiCad SPICE writer эмитит `Vn n+ n- SIN(...)`.
_VAC_DEFAULT_PROPERTIES = {
    'Sim.Pins': '1=+ 2=-',
    'Sim.Type': 'SIN',
    'Sim.Device': 'V',
    'Sim.Params': 'dc=0 ampl=1 f=1k ac=1',
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
class Inductor(_ComponentHandle):
    @property
    def pin_a(self) -> Position:
        return self.pin_positions['1']

    @property
    def pin_b(self) -> Position:
        return self.pin_positions['2']


@dataclass(frozen=True)
class Diode(_ComponentHandle):
    """Sim.Pins='1=K 2=A' — pin_k = катод, pin_a = анод."""

    @property
    def pin_k(self) -> Position:
        return self.pin_positions['1']

    @property
    def pin_a(self) -> Position:
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
class VoltageSourceAc(_ComponentHandle):
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


@dataclass(frozen=True)
class Bjt(_ComponentHandle):
    """BJT-handle для Device:Q_NPN / Q_PNP. Pin numbers — буквы B/C/E."""

    @property
    def pin_b(self) -> Position:
        return self.pin_positions['B']

    @property
    def pin_c(self) -> Position:
        return self.pin_positions['C']

    @property
    def pin_e(self) -> Position:
        return self.pin_positions['E']


@dataclass(frozen=True)
class Mosfet(_ComponentHandle):
    """MOSFET-handle для Device:Q_NMOS / Q_PMOS. Pin numbers — буквы D/G/S."""

    @property
    def pin_g(self) -> Position:
        return self.pin_positions['G']

    @property
    def pin_d(self) -> Position:
        return self.pin_positions['D']

    @property
    def pin_s(self) -> Position:
        return self.pin_positions['S']


@dataclass(frozen=True)
class Subcircuit(_ComponentHandle):
    """
    Generic SPICE subckt-инстанс поверх Connector_Generic:Conn_01x0N.

    Используется для tube/transformer моделей: symbol — нейтральный
    N-pin connector; semantic access к пинам — через `.pin(<subckt_name>)`
    ('P'/'G2'/'G'/'K' для tube, 'P1'/'P2'/'S1'/'S2' для OPT). Mapping
    держится в `pin_by_name` — заполняется фабрикой `add_subckt`.
    """

    pin_by_name: dict[str, Position]

    def pin(self, name: str) -> Position:
        try:
            return self.pin_by_name[name]
        except KeyError as exc:
            available = sorted(self.pin_by_name)
            msg = f'{self.reference}: no pin {name!r} (have {available})'
            raise KeyError(msg) from exc


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
    _texts: list[TextSpec] = field(default_factory=list)
    _pwr_counter: int = 0
    _flg_counter: int = 0

    def _auto_ref(self, prefix: str) -> str:
        """
        Найти наименьший свободный `<prefix><N>` среди уже добавленных.

        Используется когда пользователь не передал `reference` явно. Заполняет
        «дыры» — если есть R1 и R3, то возвращает R2 для следующего auto-add.
        Power markers (#PWR##/#FLG##) имеют отдельные счётчики и не учитываются.
        """
        used = {c.reference for c in self._components}
        n = 1
        while f'{prefix}{n}' in used:
            n += 1
        return f'{prefix}{n}'

    def add_resistor(
        self,
        *,
        value: str,
        at: tuple[float, float] | Position,
        reference: str | None = None,
        rotation: float = 0.0,
    ) -> Resistor:
        if reference is None:
            reference = self._auto_ref('R')
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
        value: str,
        at: tuple[float, float] | Position,
        reference: str | None = None,
        rotation: float = 0.0,
    ) -> Capacitor:
        if reference is None:
            reference = self._auto_ref('C')
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

    def add_inductor(
        self,
        *,
        value: str,
        at: tuple[float, float] | Position,
        reference: str | None = None,
        rotation: float = 0.0,
    ) -> Inductor:
        if reference is None:
            reference = self._auto_ref('L')
        position = _to_position(at)
        ref_pos, value_pos = _label_positions(position, _INDUCTOR_LABEL_OFFSETS)
        self._components.append(
            ComponentSpec(
                lib_id='Device:L',
                reference=reference,
                value=value,
                position=position,
                rotation=rotation,
                pins=tuple(p.name for p in _INDUCTOR_PINS),
                ref_position=ref_pos,
                value_position=value_pos,
                ref_rotation=rotation,
                value_rotation=rotation,
            ),
        )
        return Inductor(
            reference=reference,
            pin_positions=_pin_positions(position, rotation, _INDUCTOR_PINS),
        )

    def add_diode(
        self,
        *,
        at: tuple[float, float] | Position,
        spice_model: SpiceModel | None = None,
        spice_params: str | None = None,
        value: str | None = None,
        reference: str | None = None,
        rotation: float = 0.0,
    ) -> Diode:
        """
        Диод (Simulation_SPICE:D) с привязкой к SPICE-модели.

        Один из двух режимов параметров:

        * `spice_model` (T101 library) — `SpiceModel` категории DIODE из
          `SpiceModelLibrary`. Фасад эмитит subckt-instance: `Sim.Device=
          subckt`, `Sim.Library=<file_path>`, `Sim.Name=<id>`. Reference
          auto = `X<N>` (SPICE convention для subckt). `value` по
          умолчанию = `spice_model.id`.
        * `spice_params` (legacy inline) — строка `Param=Value ...` для
          built-in ngspice D primitive (`Sim.Device='D'`). Reference auto
          = `D<N>`. `value` обязателен (например `'1N4007'`).

        Если ни `spice_model`, ни `spice_params` не переданы —
        `ValueError`. Hardcoded default (T100 Phase 1) убран в T101.
        """
        if spice_model is None and spice_params is None:
            msg = (
                'add_diode requires either spice_model (T101 library) '
                'or spice_params (inline D-primitive). Hardcoded 1N4007 '
                'default удалён в T101.'
            )
            raise ValueError(msg)
        if spice_model is not None and spice_params is not None:
            msg = 'add_diode: укажите только один из spice_model / spice_params'
            raise ValueError(msg)
        if spice_model is not None:
            if spice_model.category is not ComponentCategory.DIODE:
                msg = (
                    f'add_diode: spice_model.category должна быть DIODE, '
                    f'получена {spice_model.category.value}'
                )
                raise ValueError(msg)
            if reference is None:
                reference = self._auto_ref('X')
            if value is None:
                value = spice_model.id
            properties = {
                'Sim.Device': 'subckt',
                'Sim.Library': str(spice_model.file_path),
                'Sim.Name': spice_model.id,
                'Sim.Pins': _DIODE_SIM_PINS,
            }
        else:
            # legacy inline path: spice_params is not None (validated выше)
            if reference is None:
                reference = self._auto_ref('D')
            if value is None:
                msg = 'add_diode with spice_params: укажите value (model name)'
                raise ValueError(msg)
            properties = {
                'Sim.Device': 'D',
                'Sim.Pins': _DIODE_SIM_PINS,
                'Sim.Params': spice_params,  # type: ignore[dict-item]
            }
        position = _to_position(at)
        ref_pos, value_pos = _label_positions(position, _DIODE_LABEL_OFFSETS)
        self._components.append(
            ComponentSpec(
                lib_id='Simulation_SPICE:D',
                reference=reference,
                value=value,
                position=position,
                rotation=rotation,
                properties=properties,
                pins=tuple(p.name for p in _DIODE_PINS),
                ref_position=ref_pos,
                value_position=value_pos,
            ),
        )
        return Diode(
            reference=reference,
            pin_positions=_pin_positions(position, rotation, _DIODE_PINS),
        )

    def add_v_dc(
        self,
        *,
        value: str,
        at: tuple[float, float] | Position,
        reference: str | None = None,
        rotation: float = 0.0,
    ) -> VoltageSourceDc:
        if reference is None:
            reference = self._auto_ref('V')
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

    def add_v_ac(
        self,
        *,
        value: str,
        at: tuple[float, float] | Position,
        amplitude: float,
        frequency: float,
        dc_offset: float = 0.0,
        reference: str | None = None,
        rotation: float = 0.0,
    ) -> VoltageSourceAc:
        """
        VSIN — синусоидальный источник напряжения.

        `amplitude` — амплитуда (peak), В. `frequency` — Гц. `dc_offset` —
        DC-смещение, В. Sim.Params строится как
        `dc={dc_offset} ampl={amplitude} f={frequency} ac=1`.
        """
        if reference is None:
            reference = self._auto_ref('V')
        position = _to_position(at)
        properties = dict(_VAC_DEFAULT_PROPERTIES)
        properties['Sim.Params'] = f'dc={dc_offset} ampl={amplitude} f={frequency} ac=1'
        ref_pos, value_pos = _label_positions(position, _VAC_LABEL_OFFSETS)
        self._components.append(
            ComponentSpec(
                lib_id='Simulation_SPICE:VSIN',
                reference=reference,
                value=value,
                position=position,
                rotation=rotation,
                properties=properties,
                pins=tuple(p.name for p in _VAC_PINS),
                ref_position=ref_pos,
                value_position=value_pos,
            ),
        )
        return VoltageSourceAc(
            reference=reference,
            pin_positions=_pin_positions(position, rotation, _VAC_PINS),
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

    def add_bjt(
        self,
        *,
        value: str,
        polarity: str,
        model_name: str,
        at: tuple[float, float] | Position,
        reference: str | None = None,
        rotation: float = 0.0,
    ) -> Bjt:
        """
        BJT-инстанс (`Device:Q_NPN` или `Q_PNP`) с привязкой к SPICE .model.

        `polarity` — 'NPN' / 'PNP'; задаёт KiCad symbol и `Sim.Device`.
        `model_name` — имя .model card (определяется отдельно через
        `spice_directive('.model <name> NPN(...)')` или из external lib).
        SPICE pin order для primitive BJT — C/B/E, что фиксируется
        `Sim.Pins='C=1 B=2 E=3'`.
        """
        if reference is None:
            reference = self._auto_ref('Q')
        if polarity == 'NPN':
            lib_id = 'Device:Q_NPN'
        elif polarity == 'PNP':
            lib_id = 'Device:Q_PNP'
        else:
            msg = f"BJT polarity must be 'NPN' or 'PNP', got {polarity!r}"
            raise ValueError(msg)
        position = _to_position(at)
        properties = {
            'Sim.Device': polarity,
            'Sim.Model': model_name,
            'Sim.Pins': 'C=1 B=2 E=3',
        }
        ref_pos, value_pos = _label_positions(position, _BJT_LABEL_OFFSETS)
        self._components.append(
            ComponentSpec(
                lib_id=lib_id,
                reference=reference,
                value=value,
                position=position,
                rotation=rotation,
                properties=properties,
                pins=tuple(p.name for p in _BJT_PINS),
                ref_position=ref_pos,
                value_position=value_pos,
            ),
        )
        return Bjt(
            reference=reference,
            pin_positions=_pin_positions(position, rotation, _BJT_PINS),
        )

    def add_mosfet(
        self,
        *,
        value: str,
        polarity: str,
        model_name: str,
        at: tuple[float, float] | Position,
        reference: str | None = None,
        rotation: float = 0.0,
    ) -> Mosfet:
        """
        MOSFET-инстанс (`Device:Q_NMOS` или `Q_PMOS`).

        SPICE pin order для primitive MOSFET — D/G/S (3-pin модель, bulk
        соединён к source внутри primitive). `Sim.Pins='D=1 G=2 S=3'`.
        """
        if reference is None:
            reference = self._auto_ref('M')
        if polarity == 'NMOS':
            lib_id = 'Device:Q_NMOS'
        elif polarity == 'PMOS':
            lib_id = 'Device:Q_PMOS'
        else:
            msg = f"MOSFET polarity must be 'NMOS' or 'PMOS', got {polarity!r}"
            raise ValueError(msg)
        position = _to_position(at)
        properties = {
            'Sim.Device': polarity,
            'Sim.Model': model_name,
            'Sim.Pins': 'D=1 G=2 S=3',
        }
        ref_pos, value_pos = _label_positions(position, _MOSFET_LABEL_OFFSETS)
        self._components.append(
            ComponentSpec(
                lib_id=lib_id,
                reference=reference,
                value=value,
                position=position,
                rotation=rotation,
                properties=properties,
                pins=tuple(p.name for p in _MOSFET_PINS),
                ref_position=ref_pos,
                value_position=value_pos,
            ),
        )
        return Mosfet(
            reference=reference,
            pin_positions=_pin_positions(position, rotation, _MOSFET_PINS),
        )

    def add_subckt(
        self,
        *,
        model_id: str,
        lib_path: Path,
        pin_names: tuple[str, ...],
        at: tuple[float, float] | Position,
        reference: str | None = None,
        rotation: float = 0.0,
        symbol: str | None = None,
    ) -> Subcircuit:
        """
        SPICE subckt-инстанс с настраиваемым lib_id.

        Default (`symbol=None`) — generic 4-pin `Connector_Generic:Conn_01x04`,
        совместимо с T100 Phase 2 fixtures (SE-amp, common-emitter).
        `pin_names` — упорядоченные SPICE-имена в порядке physical pin
        '1','2','3','4' (для tube: ('P','G2','G','K'); для OPT_SE_5K_8:
        ('P1','P2','S1','S2')).

        `symbol` (T104) — ключ из `_SYMBOL_REGISTRY` (`'Valve:EL84'` и др.).
        Когда передан, символ берётся из стандартной библиотеки KiCad
        (`Valve.kicad_sym`); фасад автоматически использует физические
        pin-номера символа и mapping `Sim.Pins` через registry. В этом
        режиме `pin_names` должны как multiset совпадать с
        `_SymbolDef.spice_pin_names` (иначе `ValueError`).

        Используется внутри `add_tube` / `add_transformer`; в API
        пользователя — для специфичных моделей без VO в T006/T007.
        """
        if reference is None:
            reference = self._auto_ref('X')
        position = _to_position(at)
        if symbol is None:
            return self._add_generic_conn_subckt(
                reference=reference,
                model_id=model_id,
                lib_path=lib_path,
                pin_names=pin_names,
                position=position,
                rotation=rotation,
            )
        valve = _SYMBOL_REGISTRY.get(symbol)
        if valve is None:
            msg = (
                f'add_subckt: unknown symbol {symbol!r}; '
                f'known: {sorted(_SYMBOL_REGISTRY)}'
            )
            raise ValueError(msg)
        return self._add_valve_subckt(
            reference=reference,
            model_id=model_id,
            lib_path=lib_path,
            pin_names=pin_names,
            position=position,
            rotation=rotation,
            valve=valve,
        )

    def _add_generic_conn_subckt(
        self,
        *,
        reference: str,
        model_id: str,
        lib_path: Path,
        pin_names: tuple[str, ...],
        position: Position,
        rotation: float,
    ) -> Subcircuit:
        if len(pin_names) != len(_CONN_01X04_PINS):
            msg = (
                f'add_subckt: pin_names must have {len(_CONN_01X04_PINS)} '
                f'entries (Conn_01x04), got {len(pin_names)}: {pin_names!r}'
            )
            raise ValueError(msg)
        sim_pins = ' '.join(
            f'{p.name}={name}'
            for p, name in zip(_CONN_01X04_PINS, pin_names, strict=True)
        )
        properties = {
            'Sim.Device': 'subckt',
            'Sim.Library': str(lib_path),
            'Sim.Name': model_id,
            'Sim.Pins': sim_pins,
        }
        ref_pos, value_pos = _label_positions(position, _CONN_01X04_LABEL_OFFSETS)
        self._components.append(
            ComponentSpec(
                lib_id='Connector_Generic:Conn_01x04',
                reference=reference,
                value=model_id,
                position=position,
                rotation=rotation,
                properties=properties,
                pins=tuple(p.name for p in _CONN_01X04_PINS),
                ref_position=ref_pos,
                value_position=value_pos,
            ),
        )
        pin_positions = _pin_positions(position, rotation, _CONN_01X04_PINS)
        pin_by_name = {
            name: pin_positions[p.name]
            for p, name in zip(_CONN_01X04_PINS, pin_names, strict=True)
        }
        return Subcircuit(
            reference=reference,
            pin_positions=pin_positions,
            pin_by_name=pin_by_name,
        )

    def _add_valve_subckt(
        self,
        *,
        reference: str,
        model_id: str,
        lib_path: Path,
        pin_names: tuple[str, ...],
        position: Position,
        rotation: float,
        valve: _SymbolDef,
    ) -> Subcircuit:
        # Multiset-проверка: SPICE-имена subckt должны совпадать с
        # ожидаемыми именами для этого Valve-символа (порядок не важен).
        if sorted(pin_names) != sorted(valve.spice_pin_names):
            msg = (
                f'add_subckt: pin_names {pin_names!r} не совпадают со SPICE-'
                f'именами для {valve.lib_id} ({valve.spice_pin_names!r})'
            )
            raise ValueError(msg)
        # Mapping: SPICE-имя → physical pin number, через registry.
        spice_to_kicad: dict[str, str] = {
            spice_name: pin.name
            for pin, spice_name in zip(
                valve.pins,
                valve.spice_pin_names,
                strict=True,
            )
        }
        # Sim.Pins: KiCad SPICE writer берёт mapping `kicad_pin=spice_name`
        # для каждого физического pin'а; порядок не критичен для писателя,
        # сохраняем registry-порядок для детерминированного diff.
        sim_pins = ' '.join(
            f'{spice_to_kicad[name]}={name}' for name in valve.spice_pin_names
        )
        properties = {
            'Sim.Device': 'subckt',
            'Sim.Library': str(lib_path),
            'Sim.Name': model_id,
            'Sim.Pins': sim_pins,
        }
        ref_pos, value_pos = _label_positions(position, valve.label_offsets)
        self._components.append(
            ComponentSpec(
                lib_id=valve.lib_id,
                reference=reference,
                value=model_id,
                position=position,
                rotation=rotation,
                properties=properties,
                pins=tuple(p.name for p in valve.pins),
                ref_position=ref_pos,
                value_position=value_pos,
                unit=valve.unit,
            ),
        )
        pin_positions = _pin_positions(position, rotation, valve.pins)
        pin_by_name = {
            spice_name: pin_positions[pin.name]
            for pin, spice_name in zip(
                valve.pins,
                valve.spice_pin_names,
                strict=True,
            )
        }
        return Subcircuit(
            reference=reference,
            pin_positions=pin_positions,
            pin_by_name=pin_by_name,
        )

    def add_tube(
        self,
        *,
        spice_model: SpiceModel,
        at: tuple[float, float] | Position,
        reference: str | None = None,
        rotation: float = 0.0,
        symbol: str | None = None,
    ) -> Subcircuit:
        """
        Tube subckt (T006 `SpiceModel`, category=TUBE) через `add_subckt`.

        Берёт `file_path` и `subckt_pins` из модели; задаёт `model_id =
        spice_model.id`. Pin access: `.pin('P')`, `.pin('G2')`, ...

        `symbol` (T104, optional) — ключ Valve-символа (`'Valve:EL84'` и
        др. из `_SYMBOL_REGISTRY`). Без него — generic Conn_01x04 stand-in
        (legacy T100 path). С ним — реальное изображение лампы в KiCad GUI,
        SPICE-numerics идентичны.
        """
        return self.add_subckt(
            reference=reference,
            model_id=spice_model.id,
            lib_path=spice_model.file_path,
            pin_names=spice_model.subckt_pins,
            at=at,
            rotation=rotation,
            symbol=symbol,
        )

    def add_transformer(
        self,
        *,
        spice_model: SpiceModel,
        at: tuple[float, float] | Position,
        reference: str | None = None,
        rotation: float = 0.0,
        symbol: str | None = None,
    ) -> Subcircuit:
        """
        Transformer subckt (T007 `SpiceModel`, category=TRANSFORMER).

        Тот же механизм, что и `add_tube` — оба завязаны на `add_subckt`.

        `symbol` (optional, 2026-05-19 follow-up) — ключ symbol-registry
        для красивого rendering. Например, `'Device:Transformer_1P_1S'` —
        canonical generic 4-pin OPT с visual coil + core lines. Без
        `symbol` — generic Conn_01x04 stand-in (legacy T100 path).

        Pin access по subckt-именам (`'P1'`, `'P2'`, `'S1'`, `'S2'` для
        SE OPT). Pin positions берутся из registry — primary слева,
        secondary справа для Transformer_1P_1S (vs все на левой стороне
        у Conn_01x04). Layout требует пересмотра при switch'е.
        """
        return self.add_subckt(
            reference=reference,
            model_id=spice_model.id,
            lib_path=spice_model.file_path,
            pin_names=spice_model.subckt_pins,
            at=at,
            rotation=rotation,
            symbol=symbol,
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

    def spice_directive(
        self,
        text: str,
        *,
        at: tuple[float, float] | Position,
    ) -> None:
        """
        Положить SPICE-директиву (`.tran`, `.ac`, `.op`, `.include`, ...).

        KiCad GUI Simulator подхватывает её при Open → Run; распознаётся
        по leading `.`. Координата `at` — куда поставить text node в схеме.
        """
        self._texts.append(TextSpec(text=text, position=_to_position(at)))

    def to_spec(self) -> SchematicSpec:
        return SchematicSpec(
            name=self.name,
            components=tuple(self._components),
            wires=tuple(self._wires),
            junctions=tuple(self._junctions),
            labels=tuple(self._labels),
            texts=tuple(self._texts),
        )

    def save(self, path: Path) -> Path:
        return KicadSchematicWriter().write(self.to_spec(), path)


__all__ = [
    'Bjt',
    'Capacitor',
    'Diode',
    'Ground',
    'Inductor',
    'Mosfet',
    'PwrFlag',
    'Resistor',
    'Schematic',
    'Subcircuit',
    'VoltageSourceAc',
    'VoltageSourceDc',
]
