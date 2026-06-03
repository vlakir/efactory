"""
Filesystem implementation of `TubeIVRepository` (T031 Phase 2, spec §5).

JSON schema mirrors `domain.tube_fitting.IVDataset`:

```json
{
  "tube_name": "6Ж38П",
  "tube_type": "pentode",
  "source": "datasheet: ...",
  "date_extracted": "2026-06-03",
  "screen_voltage_v": 150,
  "curves": [
    {"vg": -1.0, "points": [[50, 5.2], [100, 7.1]]},
    {"vg": -2.0, "points": [[50, 2.4], [100, 4.3]]}
  ],
  "screen_curves": [
    {"vg": -1.0, "points": [[100, 3.0]]}
  ]
}
```

`screen_voltage_v` обязательно для pentode, запрещено для triode.
`screen_curves` опционально (даёт KG2 identifiability — см. T031
Phase 1+).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic import ValidationError

from domain.tube_fitting import AyumiPentodeParams, IVDataset, KorenTriodeParams

if TYPE_CHECKING:
    from pathlib import Path


class IVDatasetLoadError(RuntimeError):
    """JSON-файл не парсится или не валидируется."""


class FilesystemTubeIVRepository:
    """`TubeIVRepository` implementation: читает JSON с локального диска."""

    def load_iv_dataset(self, path: Path) -> IVDataset:
        raw_text = _read_text(path)
        data = _parse_json(raw_text, path)
        try:
            return IVDataset.model_validate(data)
        except ValidationError as exc:
            msg = f'IVDataset validation failed for {path}:\n{exc}'
            raise IVDatasetLoadError(msg) from exc

    def load_seed_from_params(
        self, path: Path, tube_type: str
    ) -> KorenTriodeParams | AyumiPentodeParams:
        raw_text = _read_text(path)
        data = _parse_json(raw_text, path)
        try:
            if tube_type == 'triode':
                return KorenTriodeParams.model_validate(data)
            return AyumiPentodeParams.model_validate(data)
        except ValidationError as exc:
            msg = f'seed_from params validation failed for {path}:\n{exc}'
            raise IVDatasetLoadError(msg) from exc


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8')
    except OSError as exc:
        msg = f'cannot read tube IV JSON {path}: {exc}'
        raise IVDatasetLoadError(msg) from exc


def _parse_json(raw_text: str, path: Path) -> object:
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        msg = f'invalid JSON in {path}: {exc.msg} (line {exc.lineno})'
        raise IVDatasetLoadError(msg) from exc
