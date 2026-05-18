r"""
FilesystemSpiceModelLibrary — generic adapter для библиотеки SPICE-моделей.

Scan структуры `<root>/<category>/<source>/*.{lib,inc,cir}`:

- `<category>` ∈ `tubes` / `transformers` / `loads` (`ComponentCategory`).
- `<source>` для tubes — `koren / ayumi / duncan / custom` (T006); для
  transformers / loads — `generic` или vendor-specific (T007).

Для каждого файла парсим первую `.SUBCKT` строку: имя + пины.
Subcategory определяется в порядке приоритета (T007 C2):

1. Header `* subcategory: <value>` — generic header (новый T007).
2. Header `* tube_type: <value>` — legacy T006, backward compat
   для tube моделей.
3. Pin-count fallback — **только** для `category=TUBE`:
   2 → rectifier (half-wave), 3 → triode, 4-5 → pentode, 6+ → dual_triode.
4. Для `transformer` / `load` без header → `SpiceModelInvalidError`.

`id` = uppercase filename stem. Два файла с одним id в разных
source dir внутри одной category — `SpiceModelLibraryDuplicateError`.

**User overlay (T006 fix-up Q3):** `<user_library_root>/` сканируется
после built-in; user-id'ы перезаписывают built-in.

`read_subckt` для source=AYUMI применяет `^ → **` ngspice конверсию.

Known limitations:
- `.SUBCKT NAME P1 P2 ... [PARAMS:...]` на одной строке (uppercase
  или lowercase). Continuation `+` lines не поддерживаются.
- Header `* subcategory:` / `* tube_type:` должен быть **до**
  `.SUBCKT` строки.
"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Final

from adapters.outbound.spice_models.conversion import convert_ayumi_to_ngspice
from domain.spice_model import (
    ComponentCategory,
    ModelSource,
    SpiceModel,
    TubeType,
)
from ports.outbound.spice_model_library import (
    SpiceModelInvalidError,
    SpiceModelLibraryDuplicateError,
    SpiceModelNotFoundError,
)

if TYPE_CHECKING:
    from pathlib import Path


_MODEL_EXTS: Final = ('.lib', '.inc', '.cir')

# Pin-count → tube type fallback (T006). Header override приоритет.
_PINS_RECTIFIER_HALF: Final = 2
_PINS_TRIODE: Final = 3
_PINS_PENTODE_RANGE: Final = (4, 5)
_PINS_DUAL_TRIODE_MIN: Final = 6

_SUBCKT_RE = re.compile(
    r'^\s*\.subckt\s+(\S+)\s+(.+?)(?:\s+params:.*)?$',
    re.IGNORECASE,
)
_SUBCATEGORY_HEADER_RE = re.compile(
    r'^\s*\*\s*subcategory:\s*(\w+)\s*$',
    re.IGNORECASE,
)
# Legacy T006 header — backward compat для tube моделей.
_TUBE_TYPE_HEADER_RE = re.compile(
    r'^\s*\*\s*tube_type:\s*(\w+)\s*$',
    re.IGNORECASE,
)
_SUBCKT_BLOCK_RE = re.compile(
    r'(\.subckt\s.*?\.ends[ \t]*\S*)',
    re.IGNORECASE | re.DOTALL,
)

# Category subdir → ComponentCategory mapping.
_CATEGORY_DIR_NAMES: Final[dict[str, ComponentCategory]] = {
    'tubes': ComponentCategory.TUBE,
    'transformers': ComponentCategory.TRANSFORMER,
    'loads': ComponentCategory.LOAD,
    'diodes': ComponentCategory.DIODE,
}


def _detect_tube_subcategory(
    pins: tuple[str, ...],
    header_hint: str | None,
) -> str:
    """Tube subcategory: header priority + pin-count fallback."""
    if header_hint:
        try:
            return TubeType(header_hint.lower()).value
        except ValueError:
            pass  # неизвестный header — fallback на heuristic
    n = len(pins)
    if n == _PINS_RECTIFIER_HALF:
        return TubeType.RECTIFIER.value
    if n == _PINS_TRIODE:
        return TubeType.TRIODE.value
    if n in _PINS_PENTODE_RANGE:
        return TubeType.PENTODE.value
    if n >= _PINS_DUAL_TRIODE_MIN:
        return TubeType.DUAL_TRIODE.value
    msg = f'Invalid pin count {n} for tube SUBCKT'
    raise ValueError(msg)


def _parse_header(
    text: str,
    file_path: Path,
    category: ComponentCategory,
) -> tuple[str, tuple[str, ...], str]:
    """Извлечь `(subckt_name, pins, subcategory_value)` из текста модели."""
    header_hint: str | None = None
    subckt_match: re.Match[str] | None = None
    for line in text.splitlines():
        if subckt_match is None:
            sub = _SUBCKT_RE.match(line)
            if sub is not None:
                subckt_match = sub
                break
        # `* subcategory:` приоритет над `* tube_type:`.
        sub_hint = _SUBCATEGORY_HEADER_RE.match(line)
        if sub_hint is not None:
            header_hint = sub_hint.group(1)
            continue
        legacy_hint = _TUBE_TYPE_HEADER_RE.match(line)
        if legacy_hint is not None and header_hint is None:
            header_hint = legacy_hint.group(1)
    if subckt_match is None:
        msg = f'No .SUBCKT line found in {file_path}'
        raise SpiceModelInvalidError(msg)

    subckt_name = subckt_match.group(1)
    pins = tuple(subckt_match.group(2).split())

    if category is ComponentCategory.TUBE:
        subcategory = _detect_tube_subcategory(pins, header_hint)
    else:
        # transformer / load: header обязателен (T007 C2).
        if not header_hint:
            msg = (
                f'Missing `* subcategory: <value>` header in '
                f'{file_path} (required for category={category.value})'
            )
            raise SpiceModelInvalidError(msg)
        subcategory = header_hint.lower()

    return subckt_name, pins, subcategory


def _extract_subckt_block(text: str) -> str:
    """Вернуть содержимое от `.SUBCKT` до `.ENDS [NAME]` включительно."""
    match = _SUBCKT_BLOCK_RE.search(text)
    if match is None:
        msg = 'No .SUBCKT ... .ENDS block found'
        raise SpiceModelInvalidError(msg)
    return match.group(1)


def _parse_file(
    file_path: Path,
    category: ComponentCategory,
    source: ModelSource,
    *,
    is_user: bool = False,
) -> SpiceModel:
    text = file_path.read_text(encoding='utf-8')
    subckt_name, pins, subcategory = _parse_header(text, file_path, category)
    return SpiceModel(
        id=file_path.stem.upper(),
        name=subckt_name,
        category=category,
        subcategory=subcategory,
        source=source,
        file_path=file_path,
        subckt_pins=pins,
        is_user=is_user,
    )


def _resolve_source(source_dir_name: str) -> ModelSource | None:
    """Map source-subdir name → ModelSource enum; None если неизвестный."""
    try:
        return ModelSource(source_dir_name.lower())
    except ValueError:
        return None


def _scan_root(
    root: Path,
    *,
    is_user: bool,
) -> dict[str, SpiceModel]:
    """
    Scan `<root>/<category>/<source>/*` → {id: SpiceModel}.

    Fail-fast на duplicate id в пределах одного root.
    Неизвестные category subdirs игнорируются.
    """
    by_id: dict[str, SpiceModel] = {}
    if not root.is_dir():
        return by_id
    for category_dir_name, category in _CATEGORY_DIR_NAMES.items():
        category_dir = root / category_dir_name
        if not category_dir.is_dir():
            continue
        for source_dir in sorted(category_dir.iterdir()):
            if not source_dir.is_dir():
                continue
            source = _resolve_source(source_dir.name)
            if source is None:
                continue
            for entry in sorted(source_dir.iterdir()):
                if entry.suffix.lower() not in _MODEL_EXTS:
                    continue
                if not entry.is_file():
                    continue
                model = _parse_file(entry, category, source, is_user=is_user)
                if model.id in by_id:
                    existing = by_id[model.id]
                    msg = (
                        f"Duplicate SPICE model id '{model.id}' in "
                        f'{"user" if is_user else "built-in"} library: '
                        f'{existing.file_path} vs {entry}'
                    )
                    raise SpiceModelLibraryDuplicateError(msg)
                by_id[model.id] = model
    return by_id


class FilesystemSpiceModelLibrary:
    def __init__(
        self,
        library_root: Path,
        user_library_root: Path | None = None,
    ) -> None:
        self._library_root = library_root
        self._user_library_root = user_library_root

    async def list_all(self) -> list[SpiceModel]:
        def _scan() -> list[SpiceModel]:
            built_in = _scan_root(self._library_root, is_user=False)
            user = (
                _scan_root(self._user_library_root, is_user=True)
                if self._user_library_root is not None
                else {}
            )
            merged = {**built_in, **user}
            return sorted(merged.values(), key=lambda m: m.id)

        return await asyncio.to_thread(_scan)

    async def get_by_id(self, model_id: str) -> SpiceModel:
        models = await self.list_all()
        for m in models:
            if m.id == model_id:
                return m
        msg = f"SPICE model '{model_id}' not found in {self._library_root}"
        raise SpiceModelNotFoundError(msg)

    async def read_subckt(self, model_id: str) -> str:
        model = await self.get_by_id(model_id)

        def _read() -> str:
            raw = model.file_path.read_text(encoding='utf-8')
            block = _extract_subckt_block(raw)
            if model.source is ModelSource.AYUMI:
                return convert_ayumi_to_ngspice(block)
            return block

        return await asyncio.to_thread(_read)


__all__ = ['FilesystemSpiceModelLibrary']
