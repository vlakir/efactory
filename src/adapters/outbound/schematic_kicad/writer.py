"""
KicadSchematicWriter — `SchematicSpec` → `.kicad_sch` (KiCad 10 s-expr).

Реализует `SchematicWriter` port. Формат файла соответствует выводу
KiCad eeschema 10.0 (version 20240128): root `kicad_sch` с секциями
`lib_symbols`, `wire`, `junction`, `symbol`, `label`, `sheet_instances`.

`lib_symbols` собирается из embedded snippets — frozen-copy секций
`(symbol "X:Y" ...)` из стандартной библиотеки KiCad (`Device:R`,
`Device:C`, `Simulation_SPICE:VDC`, `power:GND`, ...). Это позволяет
сгенерированному файлу открываться на машине без настроенного
`KICAD_SYMBOL_DIR`.

Tab-индентация специально подогнана под формат eeschema, чтобы diff
между ручной и programmatic фикстурой оставался читабельным.
"""

from __future__ import annotations

import uuid as uuid_module
from importlib import resources
from typing import TYPE_CHECKING

from ports.outbound.schematic_writer import SchematicWriteError

if TYPE_CHECKING:
    from pathlib import Path

    from domain.schematic import (
        ComponentSpec,
        JunctionSpec,
        LabelSpec,
        Position,
        SchematicSpec,
        WireSpec,
    )


_LIB_SYMBOLS_PACKAGE = 'adapters.outbound.schematic_kicad.lib_symbols'
_KICAD_FILE_VERSION = '20240128'
_KICAD_GENERATOR = 'efactory'
_KICAD_GENERATOR_VERSION = '10.0'
_DEFAULT_EFFECT = '(effects (font (size 1.27 1.27)) (hide yes))'


def _fmt(value: float) -> str:
    """KiCad использует фикс-формат вида `50.8`/`62.23` (без trailing zeros)."""
    formatted = f'{value:.6g}'
    return formatted if formatted != '-0' else '0'


def _new_uuid() -> str:
    return str(uuid_module.uuid4())


def _load_lib_symbol(lib_id: str) -> str:
    """
    Прочитать embedded snippet для `lib_id` (`Device:R` → Device.R.sexp).

    Включает уже tab-отступленный `(symbol ...)` блок — кладётся внутрь
    `(lib_symbols ...)` без дополнительной обработки.
    """
    fname = lib_id.replace(':', '.') + '.sexp'
    try:
        resource = resources.files(_LIB_SYMBOLS_PACKAGE) / fname
        return resource.read_text(encoding='utf-8').rstrip('\n')
    except FileNotFoundError as exc:
        msg = (
            f'Unknown KiCad lib_id {lib_id!r}: embedded snippet '
            f'{fname!r} not found in {_LIB_SYMBOLS_PACKAGE}.'
        )
        raise SchematicWriteError(msg) from exc


def _at_fragment(position: Position, rotation: float = 0.0) -> str:
    return f'(at {_fmt(position.x_mm)} {_fmt(position.y_mm)} {_fmt(rotation)})'


def _wire_block(wire: WireSpec) -> str:
    return (
        f'\t(wire (pts (xy {_fmt(wire.start.x_mm)} {_fmt(wire.start.y_mm)}) '
        f'(xy {_fmt(wire.end.x_mm)} {_fmt(wire.end.y_mm)})) '
        f'(stroke (width 0) (type default)) (uuid "{_new_uuid()}"))'
    )


def _junction_block(junction: JunctionSpec) -> str:
    return (
        f'\t(junction (at {_fmt(junction.at.x_mm)} {_fmt(junction.at.y_mm)}) '
        f'(diameter 0) (color 0 0 0 0) (uuid "{_new_uuid()}"))'
    )


def _label_block(label: LabelSpec) -> str:
    return (
        f'\t(label "{label.text}" {_at_fragment(label.position)}\n'
        f'\t\t(effects (font (size 1.27 1.27)) (justify left bottom))\n'
        f'\t\t(uuid "{_new_uuid()}")\n'
        f'\t)'
    )


def _is_power_symbol(component: ComponentSpec) -> bool:
    """`power:*` symbols пишутся без Footprint/Datasheet (KiCad convention)."""
    return component.lib_id.startswith('power:')


def _base_property_lines(component: ComponentSpec) -> list[str]:
    px, py = _fmt(component.position.x_mm), _fmt(component.position.y_mm)
    if _is_power_symbol(component):
        return [
            (
                f'\t\t(property "Reference" "{component.reference}" '
                f'(at {px} {py} 0) {_DEFAULT_EFFECT})'
            ),
            (
                f'\t\t(property "Value" "{component.value}" (at {px} {py} 0) '
                f'(effects (font (size 1.27 1.27))))'
            ),
        ]
    return [
        f'\t\t(property "Reference" "{component.reference}" (at {px} {py} 0))',
        f'\t\t(property "Value" "{component.value}" (at {px} {py} 0))',
        f'\t\t(property "Footprint" "" (at {px} {py} 0) {_DEFAULT_EFFECT})',
        f'\t\t(property "Datasheet" "" (at {px} {py} 0) {_DEFAULT_EFFECT})',
    ]


def _symbol_block(
    component: ComponentSpec,
    project_name: str,
    sheet_uuid: str,
) -> str:
    px, py = _fmt(component.position.x_mm), _fmt(component.position.y_mm)
    rot = _fmt(component.rotation)
    lines: list[str] = [
        (
            f'\t(symbol (lib_id "{component.lib_id}") '
            f'(at {px} {py} {rot}) '
            f'(unit 1) (exclude_from_sim no) (in_bom yes) (on_board yes) '
            f'(dnp no) (uuid "{_new_uuid()}")'
        ),
        *_base_property_lines(component),
    ]
    for key, value in component.properties.items():
        lines.append(
            f'\t\t(property "{key}" "{value}" (at {px} {py} 0) {_DEFAULT_EFFECT})',
        )
    lines.extend(
        f'\t\t(pin "{pin_number}" (uuid "{_new_uuid()}"))'
        for pin_number in component.pins
    )
    lines.append(
        f'\t\t(instances (project "{project_name}" '
        f'(path "/{sheet_uuid}" (reference "{component.reference}") '
        f'(unit 1))))',
    )
    lines.append('\t)')
    return '\n'.join(lines)


class KicadSchematicWriter:
    """Сериализует `SchematicSpec` в `.kicad_sch` файл (атомарная запись)."""

    def write(self, spec: SchematicSpec, path: Path) -> Path:
        text = self._serialize(spec)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + '.tmp')
        tmp.write_text(text, encoding='utf-8')
        tmp.replace(path)
        return path

    def _serialize(self, spec: SchematicSpec) -> str:
        sheet_uuid = _new_uuid()
        lines: list[str] = [
            '(kicad_sch',
            f'\t(version {_KICAD_FILE_VERSION})',
            f'\t(generator "{_KICAD_GENERATOR}")',
            f'\t(generator_version "{_KICAD_GENERATOR_VERSION}")',
            f'\t(uuid "{sheet_uuid}")',
            '\t(paper "A4")',
            '\t(lib_symbols',
        ]
        seen: set[str] = set()
        for component in spec.components:
            if component.lib_id in seen:
                continue
            seen.add(component.lib_id)
            lines.append(_load_lib_symbol(component.lib_id))
        lines.append('\t)')
        lines.extend(_wire_block(w) for w in spec.wires)
        lines.extend(_junction_block(j) for j in spec.junctions)
        lines.extend(_symbol_block(c, spec.name, sheet_uuid) for c in spec.components)
        lines.extend(_label_block(label) for label in spec.labels)
        lines.append('\t(sheet_instances')
        lines.append('\t\t(path "/" (page "1"))')
        lines.append('\t)')
        lines.append(')')
        return '\n'.join(lines) + '\n'


__all__ = ['KicadSchematicWriter']
