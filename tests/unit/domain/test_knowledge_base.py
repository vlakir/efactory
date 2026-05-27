"""Domain: KbEntry + KbConflictError + KbParseError (T134 Phase A)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.knowledge_base import KbConflictError, KbEntry, KbParseError


def _make_entry(**overrides: object) -> KbEntry:
    defaults: dict[str, object] = {
        'topic': 'spice.saturable',
        'description': 'Saturable магнетика — XSPICE gyrator-cap, не PWL',
        'tags': ('spice', 'magnetics'),
        'source': 'built-in',
        'body': '# Body\n\nMarkdown body content.',
    }
    defaults.update(overrides)
    return KbEntry(**defaults)  # type: ignore[arg-type]


def test_kb_entry_minimum_fields() -> None:
    entry = _make_entry()
    assert entry.topic == 'spice.saturable'
    assert entry.description == 'Saturable магнетика — XSPICE gyrator-cap, не PWL'
    assert entry.tags == ('spice', 'magnetics')
    assert entry.source == 'built-in'
    assert 'Markdown body' in entry.body


def test_kb_entry_default_tags_empty_tuple() -> None:
    entry = _make_entry(tags=())
    assert entry.tags == ()


def test_kb_entry_is_frozen() -> None:
    entry = _make_entry()
    with pytest.raises(ValidationError):
        entry.topic = 'other.slug'  # type: ignore[misc]


def test_kb_entry_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        _make_entry(extra_unknown_field='oops')


def test_kb_entry_topic_must_be_namespaced() -> None:
    """Flat slug без точки запрещён."""
    with pytest.raises(ValidationError, match='topic'):
        _make_entry(topic='flat-slug')


def test_kb_entry_topic_lowercase_kebab() -> None:
    """Topic должен быть lowercase, разрешён дефис, не undercore."""
    with pytest.raises(ValidationError):
        _make_entry(topic='Spice.Saturable')  # uppercase
    with pytest.raises(ValidationError):
        _make_entry(topic='spice.with_underscore')  # underscore
    with pytest.raises(ValidationError):
        _make_entry(topic='spice.')  # empty name part
    with pytest.raises(ValidationError):
        _make_entry(topic='.saturable')  # empty namespace part


def test_kb_entry_topic_supports_multi_namespace() -> None:
    """`namespace.sub.name` валиден."""
    entry = _make_entry(topic='spice.fourier.calibration')
    assert entry.topic == 'spice.fourier.calibration'


def test_kb_entry_topic_with_digits_and_dashes() -> None:
    entry = _make_entry(topic='fem.elmer-3d-mumps-ceiling')
    assert entry.topic == 'fem.elmer-3d-mumps-ceiling'


def test_kb_entry_namespace_property() -> None:
    entry = _make_entry(topic='magnetics.leakage-erickson')
    assert entry.namespace == 'magnetics'


def test_kb_entry_name_property() -> None:
    entry = _make_entry(topic='magnetics.leakage-erickson')
    assert entry.name == 'leakage-erickson'


def test_kb_entry_name_with_nested_namespace() -> None:
    entry = _make_entry(topic='spice.fourier.calibration')
    assert entry.namespace == 'spice'
    assert entry.name == 'fourier.calibration'


def test_kb_entry_description_max_length_200() -> None:
    with pytest.raises(ValidationError):
        _make_entry(description='X' * 201)
    # 200 OK
    entry = _make_entry(description='X' * 200)
    assert len(entry.description) == 200


def test_kb_entry_description_non_empty() -> None:
    with pytest.raises(ValidationError):
        _make_entry(description='')


def test_kb_entry_body_non_empty() -> None:
    with pytest.raises(ValidationError):
        _make_entry(body='')


def test_kb_entry_source_validates() -> None:
    """Только 'built-in' / 'host-mutated'."""
    entry = _make_entry(source='host-mutated')
    assert entry.source == 'host-mutated'
    with pytest.raises(ValidationError):
        _make_entry(source='other')


def test_kb_entry_tags_lowercase_kebab() -> None:
    """Tag format: lowercase, kebab-case."""
    entry = _make_entry(tags=('spice', 'gyrator-cap'))
    assert entry.tags == ('spice', 'gyrator-cap')
    with pytest.raises(ValidationError):
        _make_entry(tags=('Spice',))  # uppercase
    with pytest.raises(ValidationError):
        _make_entry(tags=('with_underscore',))


def test_kb_entry_tags_empty_string_rejected() -> None:
    with pytest.raises(ValidationError):
        _make_entry(tags=('',))


def test_kb_conflict_error_is_exception() -> None:
    assert issubclass(KbConflictError, Exception)
    err = KbConflictError('topic spice.saturable already exists')
    assert 'spice.saturable' in str(err)


def test_kb_parse_error_is_exception() -> None:
    assert issubclass(KbParseError, Exception)
    err = KbParseError('frontmatter not closed')
    assert 'not closed' in str(err)
