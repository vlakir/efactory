"""
ErcJsonParser — `kicad-cli sch erc --format json` → ErcReport (T029).

Pure transformation, no I/O. Validates `$schema` prefix per spec N1
(`erc.v1.json` family is supported; `erc.v2.json` is rejected).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from domain.erc import (
    ErcIgnoredCheck,
    ErcItem,
    ErcParseError,
    ErcReport,
    ErcSeverity,
    ErcViolation,
)

if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path

_SCHEMA_FAMILY_PREFIX = 'https://schemas.kicad.org/erc.v1'


class ErcJsonParser:
    def parse(
        self,
        payload: dict[str, Any],
        *,
        schematic_path: Path,
        timestamp: datetime,
    ) -> ErcReport:
        schema = payload.get('$schema')
        if not isinstance(schema, str):
            msg = "ERC JSON missing '$schema' key"
            raise ErcParseError(msg)
        if not schema.startswith(_SCHEMA_FAMILY_PREFIX):
            msg = f"Unsupported ERC schema {schema!r}; expected family 'erc.v1.json'"
            raise ErcParseError(msg)

        kicad_version = str(payload.get('kicad_version', ''))
        violations = self._parse_violations(payload.get('sheets', []))
        ignored_checks = self._parse_ignored_checks(
            payload.get('ignored_checks', []),
        )

        try:
            return ErcReport(
                kicad_version=kicad_version,
                schematic_path=schematic_path,
                timestamp=timestamp,
                violations=violations,
                ignored_checks=ignored_checks,
            )
        except Exception as exc:
            msg = f'ERC JSON does not satisfy ErcReport schema: {exc}'
            raise ErcParseError(msg) from exc

    def _parse_violations(
        self,
        sheets: list[dict[str, Any]],
    ) -> list[ErcViolation]:
        return [
            self._parse_violation(raw)
            for sheet in sheets
            for raw in sheet.get('violations', [])
        ]

    def _parse_violation(self, raw: dict[str, Any]) -> ErcViolation:
        try:
            severity = ErcSeverity(raw['severity'])
            return ErcViolation(
                severity=severity,
                type=raw['type'],
                description=raw.get('description', ''),
                items=[self._parse_item(it) for it in raw.get('items', [])],
            )
        except (KeyError, ValueError) as exc:
            msg = f'Malformed ERC violation: {raw!r} ({exc})'
            raise ErcParseError(msg) from exc

    def _parse_item(self, raw: dict[str, Any]) -> ErcItem:
        try:
            pos = raw['pos']
            return ErcItem(
                description=raw.get('description', ''),
                pos=(float(pos['x']), float(pos['y'])),
                uuid=raw['uuid'],
            )
        except (KeyError, TypeError, ValueError) as exc:
            msg = f'Malformed ERC item: {raw!r} ({exc})'
            raise ErcParseError(msg) from exc

    def _parse_ignored_checks(
        self,
        raw: list[dict[str, Any]],
    ) -> list[ErcIgnoredCheck]:
        try:
            return [
                ErcIgnoredCheck(
                    key=item['key'],
                    description=item.get('description', ''),
                )
                for item in raw
            ]
        except KeyError as exc:
            msg = f'Malformed ERC ignored_check entry: missing {exc}'
            raise ErcParseError(msg) from exc


__all__ = ['ErcJsonParser']
