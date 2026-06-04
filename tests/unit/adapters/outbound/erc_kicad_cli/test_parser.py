"""ErcJsonParser unit tests against fixture JSON."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from adapters.outbound.erc_kicad_cli.parser import ErcJsonParser
from domain.erc import ErcParseError, ErcSeverity

_FIXTURES = Path(__file__).resolve().parents[4] / 'fixtures' / 'erc'


def _load(name: str) -> dict[str, object]:
    return json.loads((_FIXTURES / name).read_text(encoding='utf-8'))


def _now() -> datetime:
    return datetime(2026, 6, 5, tzinfo=UTC)


def test_parses_clean_schematic() -> None:
    payload = _load('sample_clean.json')

    report = ErcJsonParser().parse(
        payload,
        schematic_path=Path('/tmp/clean.kicad_sch'),
        timestamp=_now(),
    )

    assert report.kicad_version == '10.0.3'
    assert report.violations == []
    assert report.ignored_checks == []
    assert report.error_count == 0
    assert report.warning_count == 0
    assert report.exclusion_count == 0


def test_parses_single_error_violation() -> None:
    payload = _load('sample_one_error.json')

    report = ErcJsonParser().parse(
        payload,
        schematic_path=Path('/tmp/lpf.kicad_sch'),
        timestamp=_now(),
    )

    assert report.error_count == 1
    error_violations = [
        v for v in report.violations if v.severity is ErcSeverity.ERROR
    ]
    assert len(error_violations) == 1
    error = error_violations[0]
    assert error.type == 'power_pin_not_driven'
    assert len(error.items) == 1
    assert error.items[0].uuid.startswith('d7cd0635')
    assert error.items[0].pos == (0.8238, 0.7246)


def test_parses_warnings_and_ignored_checks() -> None:
    payload = _load('sample_warnings_only.json')

    report = ErcJsonParser().parse(
        payload,
        schematic_path=Path('/tmp/warn.kicad_sch'),
        timestamp=_now(),
    )

    assert report.error_count == 0
    assert report.warning_count == 2
    assert len(report.ignored_checks) == 1
    assert report.ignored_checks[0].key == 'single_global_label'


def test_rejects_missing_schema_key() -> None:
    parser = ErcJsonParser()
    with pytest.raises(ErcParseError, match=r'\$schema'):
        parser.parse(
            {'sheets': [], 'ignored_checks': []},
            schematic_path=Path('/tmp/x.kicad_sch'),
            timestamp=_now(),
        )


def test_rejects_unsupported_schema_version() -> None:
    payload = _load('sample_unsupported_schema.json')

    with pytest.raises(ErcParseError, match='erc.v1.json'):
        ErcJsonParser().parse(
            payload,
            schematic_path=Path('/tmp/x.kicad_sch'),
            timestamp=_now(),
        )


def test_rejects_violation_with_missing_required_field() -> None:
    payload = {
        '$schema': 'https://schemas.kicad.org/erc.v1.json',
        'kicad_version': '10.0.3',
        'sheets': [
            {
                'violations': [
                    {'type': 'oops'},
                ],
            },
        ],
        'ignored_checks': [],
    }
    with pytest.raises(ErcParseError):
        ErcJsonParser().parse(
            payload,
            schematic_path=Path('/tmp/x.kicad_sch'),
            timestamp=_now(),
        )


def test_aggregates_violations_across_multiple_sheets() -> None:
    payload = {
        '$schema': 'https://schemas.kicad.org/erc.v1.json',
        'kicad_version': '10.0.3',
        'sheets': [
            {
                'path': '/',
                'violations': [
                    {
                        'severity': 'error',
                        'type': 'pin_not_connected',
                        'description': 'd',
                        'items': [
                            {
                                'description': 'i1',
                                'pos': {'x': 0.0, 'y': 0.0},
                                'uuid': 'u1',
                            },
                        ],
                    },
                ],
            },
            {
                'path': '/sub',
                'violations': [
                    {
                        'severity': 'warning',
                        'type': 'endpoint_off_grid',
                        'description': 'd',
                        'items': [
                            {
                                'description': 'i2',
                                'pos': {'x': 1.0, 'y': 1.0},
                                'uuid': 'u2',
                            },
                        ],
                    },
                ],
            },
        ],
        'ignored_checks': [],
    }

    report = ErcJsonParser().parse(
        payload,
        schematic_path=Path('/tmp/multi.kicad_sch'),
        timestamp=_now(),
    )

    assert report.error_count == 1
    assert report.warning_count == 1
    assert len(report.violations) == 2


def test_supports_v1_minor_schema_drift() -> None:
    """`erc.v1.X.json` is treated as compatible (per spec N1)."""
    payload = {
        '$schema': 'https://schemas.kicad.org/erc.v1.2.json',
        'kicad_version': '10.1.0',
        'sheets': [{'violations': []}],
        'ignored_checks': [],
    }
    report = ErcJsonParser().parse(
        payload,
        schematic_path=Path('/tmp/x.kicad_sch'),
        timestamp=_now(),
    )
    assert report.kicad_version == '10.1.0'
