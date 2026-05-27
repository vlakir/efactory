"""Frontmatter parser/renderer для KB entries (T134 Phase A)."""

from __future__ import annotations

import pytest

from adapters.outbound.knowledge_base_filesystem.parser import (
    parse_kb_entry,
    render_kb_entry,
)
from domain.knowledge_base import KbEntry, KbParseError


_VALID_CONTENT = """\
---
topic: spice.saturable
description: Saturable магнетика — XSPICE gyrator-cap, не PWL
tags:
  - spice
  - magnetics
---
# Saturable магнетика — XSPICE gyrator-cap

Body markdown content.
"""

_MINIMAL_CONTENT = """\
---
topic: agent.command-routing
description: Mapping user-request → slash-command
---
# Body

Минимальный entry без tags.
"""


def test_parse_valid_entry_built_in_source() -> None:
    entry = parse_kb_entry(_VALID_CONTENT, source='built-in')
    assert entry.topic == 'spice.saturable'
    assert entry.description == 'Saturable магнетика — XSPICE gyrator-cap, не PWL'
    assert entry.tags == ('spice', 'magnetics')
    assert entry.source == 'built-in'
    assert '# Saturable магнетика' in entry.body


def test_parse_valid_entry_host_mutated_source() -> None:
    entry = parse_kb_entry(_VALID_CONTENT, source='host-mutated')
    assert entry.source == 'host-mutated'


def test_parse_minimal_entry_without_tags() -> None:
    entry = parse_kb_entry(_MINIMAL_CONTENT, source='built-in')
    assert entry.tags == ()
    assert entry.topic == 'agent.command-routing'


def test_parse_no_frontmatter_raises() -> None:
    with pytest.raises(KbParseError, match='must start with'):
        parse_kb_entry('# No frontmatter\n\nBody only.', source='built-in')


def test_parse_unclosed_frontmatter_raises() -> None:
    content = '---\ntopic: foo.bar\ndescription: x\n# Forgot closing\n'
    with pytest.raises(KbParseError, match='not closed'):
        parse_kb_entry(content, source='built-in')


def test_parse_invalid_yaml_raises() -> None:
    content = '---\ntopic: [unclosed\n---\nbody\n'
    with pytest.raises(KbParseError, match='valid YAML'):
        parse_kb_entry(content, source='built-in')


def test_parse_frontmatter_not_mapping_raises() -> None:
    """YAML root — list, не mapping."""
    content = '---\n- one\n- two\n---\nbody\n'
    with pytest.raises(KbParseError, match='mapping'):
        parse_kb_entry(content, source='built-in')


def test_parse_validation_error_wraps_in_kb_parse_error() -> None:
    """Pydantic ValidationError wrapped в KbParseError для caller consistency."""
    content = '---\ntopic: invalid_underscore_slug\ndescription: x\n---\nbody\n'
    with pytest.raises(KbParseError, match='validation'):
        parse_kb_entry(content, source='built-in')


def test_parse_missing_required_field_raises() -> None:
    content = '---\ntopic: foo.bar\n---\nbody\n'  # no description
    with pytest.raises(KbParseError):
        parse_kb_entry(content, source='built-in')


def test_parse_unknown_field_raises_strict() -> None:
    """extra='forbid' — unknown frontmatter field → fail."""
    content = (
        '---\n'
        'topic: foo.bar\n'
        'description: x\n'
        'unknown_field: oops\n'
        '---\n'
        'body\n'
    )
    with pytest.raises(KbParseError):
        parse_kb_entry(content, source='built-in')


def test_parse_source_in_frontmatter_overrides_caller_disallowed() -> None:
    """`source` в frontmatter — extra field (auto-set caller'ом, не trustable)."""
    content = (
        '---\n'
        'topic: foo.bar\n'
        'description: x\n'
        'source: host-mutated\n'
        '---\n'
        'body\n'
    )
    # parser передаёт source explicit; frontmatter source — это extra field.
    with pytest.raises(KbParseError):
        parse_kb_entry(content, source='built-in')


def test_parse_body_stripped_of_leading_newlines() -> None:
    content = '---\ntopic: foo.bar\ndescription: x\n---\n\n\n\nActual body.\n'
    entry = parse_kb_entry(content, source='built-in')
    assert entry.body.startswith('Actual body.')


def test_render_kb_entry_roundtrips() -> None:
    """parse → render → parse → equal."""
    original = parse_kb_entry(_VALID_CONTENT, source='built-in')
    rendered = render_kb_entry(original)
    reparsed = parse_kb_entry(rendered, source='built-in')
    assert reparsed == original


def test_render_kb_entry_without_tags_omits_tags_key() -> None:
    entry = KbEntry(
        topic='agent.command-routing',
        description='Mapping user-request → slash-command',
        tags=(),
        source='built-in',
        body='# Body\nContent.',
    )
    rendered = render_kb_entry(entry)
    assert 'tags:' not in rendered


def test_render_kb_entry_does_not_serialize_source() -> None:
    """`source` НЕ записывается в файл (Analyze A7)."""
    entry = KbEntry(
        topic='foo.bar',
        description='x',
        source='host-mutated',
        body='body',
    )
    rendered = render_kb_entry(entry)
    assert 'source:' not in rendered


def test_render_kb_entry_preserves_unicode() -> None:
    entry = KbEntry(
        topic='magnetics.zhang-formula',
        description='ZHANG reluctance — μ_eff на operating point',
        source='built-in',
        body='# Body\nμ_r ≠ μ_eff при насыщении.',
    )
    rendered = render_kb_entry(entry)
    assert 'μ_eff' in rendered
    reparsed = parse_kb_entry(rendered, source='built-in')
    assert 'μ_r' in reparsed.body
