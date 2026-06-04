"""Domain layer для T029 ERC quality gate — VO + exceptions."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from domain.erc import (
    ErcErrorsFoundError,
    ErcIgnoredCheck,
    ErcItem,
    ErcParseError,
    ErcReport,
    ErcSeverity,
    ErcTimeoutError,
    ErcViolation,
    KiCadCliUnavailableError,
    SchematicParseError,
)


# === ErcSeverity ===


def test_erc_severity_has_three_levels() -> None:
    assert ErcSeverity.ERROR.value == 'error'
    assert ErcSeverity.WARNING.value == 'warning'
    assert ErcSeverity.EXCLUSION.value == 'exclusion'


def test_erc_severity_lookup_from_kicad_string() -> None:
    assert ErcSeverity('error') is ErcSeverity.ERROR
    assert ErcSeverity('warning') is ErcSeverity.WARNING
    assert ErcSeverity('exclusion') is ErcSeverity.EXCLUSION


def test_erc_severity_rejects_unknown_value() -> None:
    with pytest.raises(ValueError, match='info'):
        ErcSeverity('info')


# === ErcItem ===


def _sample_item(uuid: str = 'abc') -> ErcItem:
    return ErcItem(
        description='Symbol U1 Pin 1 [+, Input, Line]',
        pos=(0.8238, 0.7246),
        uuid=uuid,
    )


def test_erc_item_holds_description_position_uuid() -> None:
    item = _sample_item()
    assert item.description.startswith('Symbol U1')
    assert item.pos == (0.8238, 0.7246)
    assert item.uuid == 'abc'


def test_erc_item_is_frozen() -> None:
    item = _sample_item()
    with pytest.raises(ValidationError):
        item.description = 'mutated'  # type: ignore[misc]


def test_erc_item_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        ErcItem(  # type: ignore[call-arg]
            description='d',
            pos=(0.0, 0.0),
            uuid='u',
            extra='nope',
        )


# === ErcViolation ===


def _sample_violation(
    *,
    severity: ErcSeverity = ErcSeverity.ERROR,
    type_id: str = 'power_pin_not_driven',
    items: list[ErcItem] | None = None,
) -> ErcViolation:
    return ErcViolation(
        severity=severity,
        type=type_id,
        description='Input Power pin not driven by any Output Power pins.',
        items=items if items is not None else [_sample_item()],
    )


def test_erc_violation_holds_severity_and_items() -> None:
    v = _sample_violation()
    assert v.severity is ErcSeverity.ERROR
    assert v.type == 'power_pin_not_driven'
    assert v.items == [_sample_item()]


def test_erc_violation_is_frozen() -> None:
    v = _sample_violation()
    with pytest.raises(ValidationError):
        v.type = 'mutated'  # type: ignore[misc]


def test_erc_violation_allows_empty_items_list() -> None:
    v = _sample_violation(items=[])
    assert v.items == []


# === ErcIgnoredCheck ===


def test_erc_ignored_check_holds_key_and_description() -> None:
    ic = ErcIgnoredCheck(
        key='single_global_label',
        description='Global label only appears once in the schematic.',
    )
    assert ic.key == 'single_global_label'
    assert 'Global' in ic.description


def test_erc_ignored_check_is_frozen() -> None:
    ic = ErcIgnoredCheck(key='k', description='d')
    with pytest.raises(ValidationError):
        ic.key = 'mutated'  # type: ignore[misc]


# === ErcReport ===


def _now() -> datetime:
    return datetime(2026, 6, 5, 0, 0, 0, tzinfo=UTC)


def _sample_report(
    *,
    violations: list[ErcViolation] | None = None,
    ignored_checks: list[ErcIgnoredCheck] | None = None,
) -> ErcReport:
    return ErcReport(
        kicad_version='10.0.3',
        schematic_path=Path('/tmp/lpf.kicad_sch'),
        timestamp=_now(),
        violations=violations if violations is not None else [],
        ignored_checks=ignored_checks if ignored_checks is not None else [],
    )


def test_erc_report_empty_has_zero_counts() -> None:
    r = _sample_report()
    assert r.error_count == 0
    assert r.warning_count == 0
    assert r.exclusion_count == 0


def test_erc_report_counts_total_items_per_severity() -> None:
    items_err = [_sample_item(uuid=f'e-{i}') for i in range(3)]
    items_warn = [_sample_item(uuid=f'w-{i}') for i in range(25)]
    items_excl = [_sample_item(uuid='x-0')]
    r = _sample_report(
        violations=[
            _sample_violation(severity=ErcSeverity.ERROR, items=items_err),
            _sample_violation(
                severity=ErcSeverity.WARNING,
                type_id='endpoint_off_grid',
                items=items_warn,
            ),
            _sample_violation(
                severity=ErcSeverity.EXCLUSION,
                type_id='pin_not_connected',
                items=items_excl,
            ),
        ],
    )
    assert r.error_count == 3
    assert r.warning_count == 25
    assert r.exclusion_count == 1


def test_erc_report_counts_empty_items_violation_as_one() -> None:
    """A violation reported without per-item breakdown counts as a single hit."""
    r = _sample_report(
        violations=[_sample_violation(severity=ErcSeverity.ERROR, items=[])],
    )
    assert r.error_count == 1


def test_erc_report_sums_across_violations_of_same_severity() -> None:
    r = _sample_report(
        violations=[
            _sample_violation(
                severity=ErcSeverity.ERROR,
                items=[_sample_item(uuid='a'), _sample_item(uuid='b')],
            ),
            _sample_violation(
                severity=ErcSeverity.ERROR,
                type_id='pin_not_connected',
                items=[_sample_item(uuid='c')],
            ),
        ],
    )
    assert r.error_count == 3


def test_erc_report_is_frozen() -> None:
    r = _sample_report()
    with pytest.raises(ValidationError):
        r.kicad_version = '11.0.0'  # type: ignore[misc]


# === ErcErrorsFoundError (domain exception) ===


def test_erc_errors_found_error_carries_report_payload() -> None:
    r = _sample_report(
        violations=[_sample_violation(severity=ErcSeverity.ERROR)],
    )
    err = ErcErrorsFoundError(r)

    assert isinstance(err, Exception)
    assert err.report is r
    assert err.report.error_count == 1
    assert str(r.schematic_path) in str(err)


def test_erc_errors_found_error_str_includes_counts() -> None:
    r = _sample_report(
        violations=[
            _sample_violation(
                severity=ErcSeverity.ERROR,
                items=[_sample_item(uuid='a'), _sample_item(uuid='b')],
            ),
        ],
    )
    err = ErcErrorsFoundError(r)
    assert '2' in str(err)


# === Infrastructure exceptions ===


def test_kicad_cli_unavailable_error_is_exception() -> None:
    err = KiCadCliUnavailableError('kicad-cli not found in PATH')
    assert isinstance(err, Exception)
    assert 'kicad-cli' in str(err)


def test_erc_parse_error_is_exception() -> None:
    err = ErcParseError('missing $schema key')
    assert isinstance(err, Exception)
    assert '$schema' in str(err)


def test_erc_timeout_error_carries_seconds() -> None:
    err = ErcTimeoutError(timeout_seconds=30.0)
    assert isinstance(err, Exception)
    assert err.timeout_seconds == 30.0
    assert '30' in str(err)


def test_schematic_parse_error_carries_stderr() -> None:
    err = SchematicParseError(stderr='IO Error: malformed sexpr at line 42')
    assert isinstance(err, Exception)
    assert err.stderr.startswith('IO Error')
    assert 'line 42' in str(err)


def test_erc_parse_error_distinct_from_schematic_parse_error() -> None:
    assert not issubclass(ErcParseError, SchematicParseError)
    assert not issubclass(SchematicParseError, ErcParseError)
