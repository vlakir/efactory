r"""
FilesystemTubeModelLibrary — scan `data/models/tubes/{source}/` (T006).

На каждый файл (`*.lib`, `*.inc`, `*.cir`) парсим первую `.SUBCKT`
строку: имя + список пинов. Тип лампы определяем (Resolved #2 (C)):
- header `* tube_type: pentode` приоритет,
- fallback — pin count (3 → triode, 4-5 → pentode, 6+ → dual_triode).

`id` = uppercase filename stem (C3). Это позволяет двум источникам
иметь одну лампу с разными параметрами (`EL34_KOREN.lib` +
`EL34_AYUMI.inc`) без конфликта.

`read_subckt` для Ayumi-моделей применяет `^ → **` конвертацию.

Known limitation (C2): поддерживаются только `.SUBCKT NAME P1 P2 ...
[PARAMS:...]` на одной строке (uppercase или lowercase). Continuation
lines (`.SUBCKT NAME\\n+ P1 P2`) не поддерживаются — добавим если
встретится в реальной upstream-модели (T002 audit).
"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Final

from adapters.outbound.tube_models.conversion import convert_ayumi_to_ngspice
from domain.spice_model import ModelSource, SpiceModel, TubeType
from ports.outbound.tube_model_library import (
    TubeModelLibraryDuplicateError,
    TubeModelNotFoundError,
)

if TYPE_CHECKING:
    from pathlib import Path


_MODEL_EXTS: Final = ('.lib', '.inc', '.cir')

# Pin-count → tube type fallback (N8). Header override приоритет.
_PINS_TRIODE: Final = 3
_PINS_PENTODE_RANGE: Final = (4, 5)
_PINS_DUAL_TRIODE_MIN: Final = 6
_SUBCKT_RE = re.compile(
    r'^\s*\.subckt\s+(\S+)\s+(.+?)(?:\s+params:.*)?$',
    re.IGNORECASE,
)
_TUBE_TYPE_HEADER_RE = re.compile(
    r'^\s*\*\s*tube_type:\s*(\w+)\s*$',
    re.IGNORECASE,
)
_SUBCKT_BLOCK_RE = re.compile(
    r'(\.subckt\s.*?\.ends)',
    re.IGNORECASE | re.DOTALL,
)


def _detect_tube_type(
    pins: tuple[str, ...],
    header_hint: str | None,
) -> TubeType:
    """Header override (N3) + pin-count fallback (N8)."""
    if header_hint:
        try:
            return TubeType(header_hint.lower())
        except ValueError:
            pass  # неизвестный header — fallback на heuristic
    n = len(pins)
    if n == _PINS_TRIODE:
        return TubeType.TRIODE
    if n in _PINS_PENTODE_RANGE:
        return TubeType.PENTODE
    if n >= _PINS_DUAL_TRIODE_MIN:
        return TubeType.DUAL_TRIODE
    msg = f'Invalid pin count {n} for tube SUBCKT'
    raise ValueError(msg)


def _parse_header(text: str, file_path: Path) -> tuple[str, tuple[str, ...], TubeType]:
    """Извлечь (subckt_name, pins, tube_type) из текста модели."""
    header_hint: str | None = None
    subckt_match: re.Match[str] | None = None
    for line in text.splitlines():
        if subckt_match is None:
            sub = _SUBCKT_RE.match(line)
            if sub is not None:
                subckt_match = sub
                break
        hint = _TUBE_TYPE_HEADER_RE.match(line)
        if hint is not None:
            header_hint = hint.group(1)
    if subckt_match is None:
        msg = f'No .SUBCKT line found in {file_path}'
        raise ValueError(msg)
    subckt_name = subckt_match.group(1)
    pins = tuple(subckt_match.group(2).split())
    tube_type = _detect_tube_type(pins, header_hint)
    return subckt_name, pins, tube_type


def _extract_subckt_block(text: str) -> str:
    """Вернуть содержимое от `.SUBCKT` до `.ENDS` (inclusive)."""
    match = _SUBCKT_BLOCK_RE.search(text)
    if match is None:
        msg = 'No .SUBCKT ... .ENDS block found'
        raise ValueError(msg)
    return match.group(1)


class FilesystemTubeModelLibrary:
    def __init__(self, library_root: Path) -> None:
        self._library_root = library_root

    async def list_all(self) -> list[SpiceModel]:
        def _scan() -> list[SpiceModel]:
            if not self._library_root.is_dir():
                return []
            by_id: dict[str, SpiceModel] = {}
            for source in ModelSource:
                source_dir = self._library_root / source.value
                if not source_dir.is_dir():
                    continue
                for entry in sorted(source_dir.iterdir()):
                    if entry.suffix.lower() not in _MODEL_EXTS:
                        continue
                    if not entry.is_file():
                        continue
                    model = _parse_file(entry, source)
                    if model.id in by_id:
                        existing = by_id[model.id]
                        msg = (
                            f"Duplicate tube model id '{model.id}': "
                            f'{existing.file_path} vs {entry}'
                        )
                        raise TubeModelLibraryDuplicateError(msg)
                    by_id[model.id] = model
            return sorted(by_id.values(), key=lambda m: m.id)

        return await asyncio.to_thread(_scan)

    async def get_by_id(self, model_id: str) -> SpiceModel:
        models = await self.list_all()
        for m in models:
            if m.id == model_id:
                return m
        msg = f"Tube model '{model_id}' not found in {self._library_root}"
        raise TubeModelNotFoundError(msg)

    async def read_subckt(self, model_id: str) -> str:
        model = await self.get_by_id(model_id)

        def _read() -> str:
            raw = model.file_path.read_text(encoding='utf-8')
            block = _extract_subckt_block(raw)
            if model.source is ModelSource.AYUMI:
                return convert_ayumi_to_ngspice(block)
            return block

        return await asyncio.to_thread(_read)


def _parse_file(file_path: Path, source: ModelSource) -> SpiceModel:
    text = file_path.read_text(encoding='utf-8')
    subckt_name, pins, tube_type = _parse_header(text, file_path)
    return SpiceModel(
        id=file_path.stem.upper(),
        name=subckt_name,
        tube_type=tube_type,
        source=source,
        file_path=file_path,
        subckt_pins=pins,
    )


__all__ = ['FilesystemTubeModelLibrary']
