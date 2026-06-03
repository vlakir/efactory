"""
KicadSchematicWriter — `SchematicSpec` → `.kicad_sch` (KiCad 10 multiline).

Реализует `SchematicWriter` port. Формат файла — `(version 20260306)`,
текущий KiCad 10 eeschema output (multiline expanded s-expression).

`lib_symbols` собирается из embedded snippets (single-file KiCad-library
format, совпадают с тем что лежит в /usr/share/kicad/symbols/*.kicad_sym
у apt-installed KiCad). Это позволяет сгенерированному файлу
открываться на машине без настроенного `KICAD_SYMBOL_DIR` и не
получать `lib_symbol_mismatch` warning'ов в ERC.

Tab-индентация и набор обязательных полей (`body_style`, `in_pos_files`,
`Description` property, `fields_autoplaced`, `embedded_fonts`, justify
у visible Reference/Value) совпадают с тем, что KiCad 10 GUI пишет
после save. Без них GUI при повторном save может уйти в OOM/reset
(T100 incident 2026-05-18; в итоге причина оказалась в AppImage
сборке, но canonical-формат всё равно желателен для стабильности).

T026 (2026-06-03): добавлен staged-режим. Если `LockDetector` сообщает,
что KiCad GUI держит `path` открытым (lock-файл рядом), writer пишет
рядом `<path>.staged` + sidecar `.meta.json` с `parent_hash` (sha256
active content на момент write) вместо overwrite активного. Уведомления
через `WriterNotifier` (default Null). При наличии lock возвращает
staged-путь, не active.
"""

from __future__ import annotations

import hashlib
import re
import uuid as uuid_module
from datetime import UTC, datetime
from importlib import resources
from typing import TYPE_CHECKING

from adapters.outbound.schematic_kicad.lock_detector import KicadLockDetector
from adapters.outbound.schematic_kicad.notifier import (
    NullWriterNotifier,
    WriterNotifier,
)
from adapters.outbound.schematic_kicad.staged_metadata import (
    StagedMetadata,
    write_staged_metadata,
)
from adapters.outbound.schematic_kicad.staged_paths import (
    meta_path,
    staged_path,
)
from ports.outbound.schematic_writer import SchematicWriteError

if TYPE_CHECKING:
    from pathlib import Path

    from domain.schematic import (
        ComponentSpec,
        JunctionSpec,
        LabelSpec,
        NoConnectSpec,
        Position,
        SchematicSpec,
        TextSpec,
        WireSpec,
    )
    from ports.outbound.staged_schematics import LockDetector


_LIB_SYMBOLS_PACKAGE = 'adapters.outbound.schematic_kicad.lib_symbols'
_KICAD_FILE_VERSION = '20260306'
_KICAD_GENERATOR = 'efactory'
_KICAD_GENERATOR_VERSION = '10.0'
_STAGED_BY = 'efactory'
_STAGED_TRIGGER_DEFAULT = 'unknown'


def _fmt(value: float) -> str:
    formatted = f'{value:.6g}'
    return formatted if formatted != '-0' else '0'


def _new_uuid() -> str:
    return str(uuid_module.uuid4())


def _t(depth: int) -> str:
    return '\t' * depth


_EXTENDS_RE = re.compile(r'\(extends "([^"]+)"\)')


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utc_iso() -> str:
    return datetime.now(tz=UTC).isoformat(timespec='seconds').replace('+00:00', 'Z')


def _load_lib_symbol(lib_id: str) -> str:
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


def _collect_lib_symbols(lib_ids: list[str]) -> list[str]:
    """
    Загрузить snippets для всех lib_ids + parent-цепочки через `(extends ...)`.

    Topological-sorted: parents эмитятся перед derived. Дедупликация: каждый
    lib_id загружается ровно один раз даже если несколько компонентов его
    используют или несколько derived ссылаются на одного parent.

    KiCad `(extends "X")` требует, чтобы parent X присутствовал в той же
    `lib_symbols` секции и эмитился ДО derived (иначе symbol не
    разрешается). Для T105: `Valve:ECC83 extends Valve:ECC81` — при
    использовании ECC83 автоматически подгружаем ECC81.
    """
    loaded: dict[str, str] = {}
    queue = list(dict.fromkeys(lib_ids))  # preserve order, dedup
    while queue:
        lid = queue.pop(0)
        if lid in loaded:
            continue
        snippet = _load_lib_symbol(lid)
        loaded[lid] = snippet
        for match in _EXTENDS_RE.finditer(snippet):
            parent = match.group(1)
            if parent not in loaded:
                queue.append(parent)
    # Topo-sort: parents before derived. `sorted(pending)` гарантирует
    # детерминированный output между запусками — Python set iteration
    # рандомизируется через PYTHONHASHSEED, и без sort lib_symbols секция
    # перемешивается на каждом rebuild (snapshot-CI fail).
    ordered: list[str] = []
    pending = set(loaded)
    while pending:
        progressed = False
        for lid in sorted(pending):
            parents = {m.group(1) for m in _EXTENDS_RE.finditer(loaded[lid])}
            if parents.issubset(set(ordered)):
                ordered.append(lid)
                pending.discard(lid)
                progressed = True
        if not progressed:
            ordered.extend(sorted(pending))
            break
    return [loaded[lid] for lid in ordered]


def _is_power_symbol(component: ComponentSpec) -> bool:
    return component.lib_id.startswith('power:')


def _font_effects(depth: int, justify: str | None = None) -> list[str]:
    lines = [
        _t(depth) + '(effects',
        _t(depth + 1) + '(font',
        _t(depth + 2) + '(size 1.27 1.27)',
        _t(depth + 1) + ')',
    ]
    if justify is not None:
        lines.append(_t(depth + 1) + f'(justify {justify})')
    lines.append(_t(depth) + ')')
    return lines


def _property_block(
    depth: int,
    name: str,
    value: str,
    position: Position,
    *,
    rotation: float = 0.0,
    hidden: bool = False,
    justify: str | None = None,
) -> list[str]:
    lines = [
        _t(depth) + f'(property "{name}" "{value}"',
        _t(depth + 1)
        + f'(at {_fmt(position.x_mm)} {_fmt(position.y_mm)} {_fmt(rotation)})',
    ]
    if hidden:
        lines.append(_t(depth + 1) + '(hide yes)')
    lines.append(_t(depth + 1) + '(show_name no)')
    lines.append(_t(depth + 1) + '(do_not_autoplace no)')
    lines.extend(_font_effects(depth + 1, justify))
    lines.append(_t(depth) + ')')
    return lines


def _wire_block(depth: int, wire: WireSpec) -> list[str]:
    return [
        _t(depth) + '(wire',
        _t(depth + 1) + '(pts',
        _t(depth + 2)
        + f'(xy {_fmt(wire.start.x_mm)} {_fmt(wire.start.y_mm)}) '
        + f'(xy {_fmt(wire.end.x_mm)} {_fmt(wire.end.y_mm)})',
        _t(depth + 1) + ')',
        _t(depth + 1) + '(stroke',
        _t(depth + 2) + '(width 0)',
        _t(depth + 2) + '(type default)',
        _t(depth + 1) + ')',
        _t(depth + 1) + f'(uuid "{_new_uuid()}")',
        _t(depth) + ')',
    ]


def _junction_block(depth: int, junction: JunctionSpec) -> list[str]:
    return [
        _t(depth) + '(junction',
        _t(depth + 1) + f'(at {_fmt(junction.at.x_mm)} {_fmt(junction.at.y_mm)})',
        _t(depth + 1) + '(diameter 0)',
        _t(depth + 1) + '(color 0 0 0 0)',
        _t(depth + 1) + f'(uuid "{_new_uuid()}")',
        _t(depth) + ')',
    ]


def _no_connect_block(depth: int, no_connect: NoConnectSpec) -> list[str]:
    return [
        _t(depth) + '(no_connect',
        _t(depth + 1) + f'(at {_fmt(no_connect.at.x_mm)} {_fmt(no_connect.at.y_mm)})',
        _t(depth + 1) + f'(uuid "{_new_uuid()}")',
        _t(depth) + ')',
    ]


def _label_block(depth: int, label: LabelSpec) -> list[str]:
    return [
        _t(depth) + f'(label "{label.text}"',
        _t(depth + 1)
        + f'(at {_fmt(label.position.x_mm)} {_fmt(label.position.y_mm)} 0)',
        *_font_effects(depth + 1, 'left bottom'),
        _t(depth + 1) + f'(uuid "{_new_uuid()}")',
        _t(depth) + ')',
    ]


def _text_block(depth: int, text: TextSpec) -> list[str]:
    """
    Schematic text node (SPICE-директива при leading `.`).

    `exclude_from_sim no` — обязательно, иначе KiCad считает текст
    декоративным и не включает в netlist.
    """
    escaped = text.text.replace('"', '\\"')
    return [
        _t(depth) + f'(text "{escaped}"',
        _t(depth + 1) + '(exclude_from_sim no)',
        _t(depth + 1) + f'(at {_fmt(text.position.x_mm)} {_fmt(text.position.y_mm)} 0)',
        *_font_effects(depth + 1, 'left bottom'),
        _t(depth + 1) + f'(uuid "{_new_uuid()}")',
        _t(depth) + ')',
    ]


def _base_properties(depth: int, component: ComponentSpec) -> list[str]:
    """Reference/Value/Footprint/Datasheet/Description — KiCad 10 obligatory."""
    ref_pos = component.ref_position or component.position
    value_pos = component.value_position or component.position
    pos = component.position
    is_power = _is_power_symbol(component)
    # У не-power Reference/Value visible с (justify left); у power Reference
    # hidden, Value visible без justify (canonical KiCad save).
    visible_justify = None if is_power else 'left'
    lines = []
    lines.extend(
        _property_block(
            depth,
            'Reference',
            component.reference,
            ref_pos,
            rotation=component.ref_rotation,
            hidden=is_power,
            justify=visible_justify,
        ),
    )
    lines.extend(
        _property_block(
            depth,
            'Value',
            component.value,
            value_pos,
            rotation=component.value_rotation,
            justify=visible_justify,
        ),
    )
    # Footprint/Datasheet — hidden у не-power; у power тоже hidden (canonical).
    lines.extend(
        _property_block(depth, 'Footprint', '', pos, hidden=not is_power),
    )
    lines.extend(
        _property_block(depth, 'Datasheet', '', pos, hidden=not is_power),
    )
    # Description ВСЕГДА hidden в instance.
    lines.extend(_property_block(depth, 'Description', '', pos, hidden=True))
    return lines


def _symbol_block(
    depth: int,
    component: ComponentSpec,
    sheet_uuid: str,
    project_name: str,
) -> list[str]:
    pos = component.position
    lines: list[str] = [
        _t(depth) + '(symbol',
        _t(depth + 1) + f'(lib_id "{component.lib_id}")',
        _t(depth + 1)
        + f'(at {_fmt(pos.x_mm)} {_fmt(pos.y_mm)} {_fmt(component.rotation)})',
        _t(depth + 1) + f'(unit {component.unit})',
        _t(depth + 1) + '(body_style 1)',
        _t(depth + 1) + '(exclude_from_sim no)',
        _t(depth + 1) + '(in_bom yes)',
        _t(depth + 1) + '(on_board yes)',
        _t(depth + 1) + '(in_pos_files yes)',
        _t(depth + 1) + '(dnp no)',
        # `(fields_autoplaced yes)` — Reference/Value поставлены пользователем;
        # без него KiCad GUI пересчитывает layout при save (T100 incident).
        _t(depth + 1) + '(fields_autoplaced yes)',
        _t(depth + 1) + f'(uuid "{_new_uuid()}")',
    ]
    lines.extend(_base_properties(depth + 1, component))
    for key, value in component.properties.items():
        lines.extend(
            _property_block(depth + 1, key, value, pos, hidden=True),
        )
    for pin_number in component.pins:
        lines.append(_t(depth + 1) + f'(pin "{pin_number}"')
        lines.append(_t(depth + 2) + f'(uuid "{_new_uuid()}")')
        lines.append(_t(depth + 1) + ')')
    lines.extend(
        [
            _t(depth + 1) + '(instances',
            _t(depth + 2) + f'(project "{project_name}"',
            _t(depth + 3) + f'(path "/{sheet_uuid}"',
            _t(depth + 4) + f'(reference "{component.reference}")',
            _t(depth + 4) + f'(unit {component.unit})',
            _t(depth + 3) + ')',
            _t(depth + 2) + ')',
            _t(depth + 1) + ')',
            _t(depth) + ')',
        ]
    )
    return lines


def _sheet_instances(depth: int) -> list[str]:
    return [
        _t(depth) + '(sheet_instances',
        _t(depth + 1) + '(path "/"',
        _t(depth + 2) + '(page "1")',
        _t(depth + 1) + ')',
        _t(depth) + ')',
    ]


class KicadSchematicWriter:
    """
    Сериализует `SchematicSpec` в `.kicad_sch` файл (атомарная запись).

    При детекте «KiCad GUI держит файл открытым» (lock_detector) —
    пишет рядом `<path>.staged` + sidecar `.meta.json` с `parent_hash`,
    активный файл не трогает. Notifier получает `staged()` /
    `staged_overwrite()` события для CLI-уведомлений.
    """

    def __init__(
        self,
        *,
        notifier: WriterNotifier | None = None,
        lock_detector: LockDetector | None = None,
    ) -> None:
        self._notifier: WriterNotifier = notifier or NullWriterNotifier()
        self._lock_detector: LockDetector = lock_detector or KicadLockDetector()

    def write(self, spec: SchematicSpec, path: Path) -> Path:
        text = self._serialize(spec)
        path.parent.mkdir(parents=True, exist_ok=True)
        if self._lock_detector.is_held_by_kicad(path):
            return self._write_staged(text, path)
        return self._write_direct(text, path)

    def _write_direct(self, text: str, path: Path) -> Path:
        new_bytes = text.encode('utf-8')
        if path.exists() and path.read_bytes() == new_bytes:
            return path
        tmp = path.with_suffix(path.suffix + '.tmp')
        tmp.write_text(text, encoding='utf-8')
        tmp.replace(path)
        return path

    def _write_staged(self, text: str, active_path: Path) -> Path:
        staged = staged_path(active_path)
        new_bytes = text.encode('utf-8')
        # Full no-op: identical staged already exists.
        if staged.exists() and staged.read_bytes() == new_bytes:
            return staged
        # Overwrite warning if staged already present with different bytes.
        if staged.exists():
            prev_hash = _sha256_hex(staged.read_bytes())
            self._notifier.staged_overwrite(prev_hash)
        parent_hash = (
            _sha256_hex(active_path.read_bytes()) if active_path.exists() else None
        )
        tmp = staged.with_suffix(staged.suffix + '.tmp')
        tmp.write_text(text, encoding='utf-8')
        tmp.replace(staged)
        meta = StagedMetadata(
            parent_hash=parent_hash,
            staged_at=_utc_iso(),
            staged_by=_STAGED_BY,
            trigger=_STAGED_TRIGGER_DEFAULT,
        )
        write_staged_metadata(meta_path(staged), meta)
        self._notifier.staged(staged)
        return staged

    def _serialize(self, spec: SchematicSpec) -> str:
        sheet_uuid = _new_uuid()
        lines: list[str] = [
            '(kicad_sch',
            _t(1) + f'(version {_KICAD_FILE_VERSION})',
            _t(1) + f'(generator "{_KICAD_GENERATOR}")',
            _t(1) + f'(generator_version "{_KICAD_GENERATOR_VERSION}")',
            _t(1) + f'(uuid "{sheet_uuid}")',
            _t(1) + '(paper "A4")',
            _t(1) + '(lib_symbols',
        ]
        lib_ids = [c.lib_id for c in spec.components]
        lines.extend(_collect_lib_symbols(lib_ids))
        lines.append(_t(1) + ')')
        for wire in spec.wires:
            lines.extend(_wire_block(1, wire))
        for junction in spec.junctions:
            lines.extend(_junction_block(1, junction))
        for no_connect in spec.no_connects:
            lines.extend(_no_connect_block(1, no_connect))
        for label in spec.labels:
            lines.extend(_label_block(1, label))
        for text in spec.texts:
            lines.extend(_text_block(1, text))
        for component in spec.components:
            lines.extend(_symbol_block(1, component, sheet_uuid, spec.name))
        lines.extend(_sheet_instances(1))
        # `(embedded_fonts no)` — обязательное root-поле KiCad 10.
        lines.append(_t(1) + '(embedded_fonts no)')
        lines.append(')')
        return '\n'.join(lines) + '\n'


__all__ = ['KicadSchematicWriter']
