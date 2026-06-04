"""
KicadCliErcRunner — async `kicad-cli sch erc` wrapper (T029).

`run()` builds a tmp-file output, invokes `kicad-cli sch erc --format
json --severity-all --output <tmp.json> <schematic>` with locale forced
to C, and hands the parsed JSON to `ErcJsonParser` (spec R15: only the
JSON file is parsed; stdout/stderr are ignored beyond the exit code).

Failure differentiation (spec R17):
- binary missing in PATH → `KiCadCliUnavailableError`
- subprocess exceeds timeout → `ErcTimeoutError`
- subprocess crashed / no JSON output → `SchematicParseError`
- JSON malformed or schema mismatch → `ErcParseError` (from parser)
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from adapters.outbound.erc_kicad_cli.parser import ErcJsonParser
from domain.erc import (
    ErcReport,
    ErcTimeoutError,
    KiCadCliUnavailableError,
    SchematicParseError,
)


class KicadCliErcRunner:
    def __init__(
        self,
        *,
        binary: str = 'kicad-cli',
        parser: ErcJsonParser | None = None,
    ) -> None:
        self._binary = binary
        self._parser = parser or ErcJsonParser()

    async def run(
        self,
        schematic: Path,
        *,
        timeout_seconds: float,
    ) -> ErcReport:
        return await asyncio.to_thread(
            self._run_sync,
            schematic,
            timeout_seconds,
        )

    def _run_sync(
        self,
        schematic: Path,
        timeout_seconds: float,
    ) -> ErcReport:
        resolved = shutil.which(self._binary)
        if resolved is None:
            msg = f'{self._binary!r} not found in PATH'
            raise KiCadCliUnavailableError(msg)

        with tempfile.TemporaryDirectory(prefix='erc-') as tmpdir:
            out_path = Path(tmpdir) / 'erc.json'
            argv = [
                resolved,
                'sch',
                'erc',
                '--format',
                'json',
                '--severity-all',
                '--output',
                str(out_path),
                str(schematic),
            ]
            env = {**os.environ, 'LANG': 'C', 'LC_ALL': 'C'}
            try:
                result = subprocess.run(
                    argv,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    env=env,
                )
            except subprocess.TimeoutExpired as exc:
                raise ErcTimeoutError(timeout_seconds=timeout_seconds) from exc

            if not out_path.exists() or out_path.stat().st_size == 0:
                stderr = (result.stderr or result.stdout or '').strip()
                raise SchematicParseError(stderr=stderr)

            try:
                payload = json.loads(out_path.read_text(encoding='utf-8'))
            except json.JSONDecodeError as exc:
                stderr = (result.stderr or '').strip()
                raise SchematicParseError(stderr=stderr or str(exc)) from exc

        return self._parser.parse(
            payload,
            schematic_path=schematic,
            timestamp=datetime.now(UTC),
        )


__all__ = ['KicadCliErcRunner']
