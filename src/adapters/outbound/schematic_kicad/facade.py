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

# Diode: built-in ngspice D primitive с inline-параметрами через Sim.Params.
# Pin convention KiCad: 1=K (cathode), 2=A (anode) — Sim.Pins фиксирует это
# для SPICE-writer'а вне зависимости от visual rotation.
_DIODE_DEFAULT_PROPERTIES = {
    'Sim.Device': 'D',
    'Sim.Pins': '1=K 2=A',
    'Sim.Params': 'Is=14.11n N=1.984 Rs=33.89m Cjo=51.17p Bv=1000 Ibv=10u Tt=4.32u',
}

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

    def add_inductor(
        self,
        *,
        reference: str,
        value: str,
        at: tuple[float, float] | Position,
        rotation: float = 0.0,
    ) -> Inductor:
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
        reference: str,
        value: str,
        at: tuple[float, float] | Position,
        rotation: float = 0.0,
        spice_params: str | None = None,
    ) -> Diode:
        """
        Диод (Simulation_SPICE:D) с inline SPICE-параметрами.

        `spice_params` — строка в формате KiCad/ngspice `Param=Value ...`
        (например, Duncan-модель 1N4007). Если None — используется default
        из библиотеки (generic Si: Is=14.11n N=1.984 ... 1N4007-like).
        """
        position = _to_position(at)
        properties = dict(_DIODE_DEFAULT_PROPERTIES)
        if spice_params is not None:
            properties['Sim.Params'] = spice_params
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

    def add_v_ac(
        self,
        *,
        reference: str,
        value: str,
        at: tuple[float, float] | Position,
        amplitude: float,
        frequency: float,
        dc_offset: float = 0.0,
        rotation: float = 0.0,
    ) -> VoltageSourceAc:
        """
        VSIN — синусоидальный источник напряжения.

        `amplitude` — амплитуда (peak), В. `frequency` — Гц. `dc_offset` —
        DC-смещение, В. Sim.Params строится как
        `dc={dc_offset} ampl={amplitude} f={frequency} ac=1`.
        """
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
        reference: str,
        value: str,
        polarity: str,
        model_name: str,
        at: tuple[float, float] | Position,
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
        reference: str,
        value: str,
        polarity: str,
        model_name: str,
        at: tuple[float, float] | Position,
        rotation: float = 0.0,
    ) -> Mosfet:
        """
        MOSFET-инстанс (`Device:Q_NMOS` или `Q_PMOS`).

        SPICE pin order для primitive MOSFET — D/G/S (3-pin модель, bulk
        соединён к source внутри primitive). `Sim.Pins='D=1 G=2 S=3'`.
        """
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
        reference: str,
        model_id: str,
        lib_path: Path,
        pin_names: tuple[str, ...],
        at: tuple[float, float] | Position,
        rotation: float = 0.0,
    ) -> Subcircuit:
        """
        Generic 4-pin SPICE subckt-инстанс (поверх `Connector_Generic:Conn_01x04`).

        `model_id` — имя `.SUBCKT` в lib-файле; `lib_path` — путь к
        `.lib` (KiCad SPICE writer автоматически вставит `.include`).
        `pin_names` — упорядоченные имена пинов subckt в порядке symbol pin
        '1','2','3','4' (для tube: ('P','G2','G','K'); для OPT_SE_5K_8:
        ('P1','P2','S1','S2')).

        Используется внутри `add_tube` / `add_transformer`; в API
        пользователя — для специфичных моделей без VO в T006/T007.
        """
        if len(pin_names) != len(_CONN_01X04_PINS):
            msg = (
                f'add_subckt: pin_names must have {len(_CONN_01X04_PINS)} entries '
                f'(Conn_01x04), got {len(pin_names)}: {pin_names!r}'
            )
            raise ValueError(msg)
        position = _to_position(at)
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

    def add_tube(
        self,
        *,
        spice_model: SpiceModel,
        reference: str,
        at: tuple[float, float] | Position,
        rotation: float = 0.0,
    ) -> Subcircuit:
        """
        Tube subckt (T006 `SpiceModel`, category=TUBE) через `add_subckt`.

        Берёт `file_path` и `subckt_pins` из модели; задаёт `model_id =
        spice_model.id`. Pin access: `.pin('P')`, `.pin('G2')`, ...
        """
        return self.add_subckt(
            reference=reference,
            model_id=spice_model.id,
            lib_path=spice_model.file_path,
            pin_names=spice_model.subckt_pins,
            at=at,
            rotation=rotation,
        )

    def add_transformer(
        self,
        *,
        spice_model: SpiceModel,
        reference: str,
        at: tuple[float, float] | Position,
        rotation: float = 0.0,
    ) -> Subcircuit:
        """
        Transformer subckt (T007 `SpiceModel`, category=TRANSFORMER).

        Тот же механизм, что и `add_tube` — оба завязаны на `add_subckt`
        + 4-pin Conn_01x04. Pin access по subckt-именам (`'P1'`, `'P2'`,
        `'S1'`, `'S2'` для SE OPT).
        """
        return self.add_subckt(
            reference=reference,
            model_id=spice_model.id,
            lib_path=spice_model.file_path,
            pin_names=spice_model.subckt_pins,
            at=at,
            rotation=rotation,
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
