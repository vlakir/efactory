"""FileSystemKbStore integration с реальным tmp_path (T134 Phase B)."""

from __future__ import annotations

from pathlib import Path

import pytest

from adapters.outbound.knowledge_base_filesystem.store import FileSystemKbStore
from domain.knowledge_base import KbConflictError, KbEntry, KbParseError


def _store(tmp_path: Path) -> FileSystemKbStore:
    return FileSystemKbStore(
        built_in_dir=tmp_path / 'built-in',
        host_mutated_dir=tmp_path / 'host-mutated',
    )


def _write_md(directory: Path, slug: str, *, body: str = 'Body.', tags: str = '') -> None:
    directory.mkdir(parents=True, exist_ok=True)
    tags_yaml = f'tags: [{tags}]\n' if tags else ''
    content = (
        f'---\n'
        f'topic: {slug}\n'
        f'description: {slug} desc\n'
        f'{tags_yaml}'
        f'---\n'
        f'{body}\n'
    )
    (directory / f'{slug}.md').write_text(content, encoding='utf-8')


def test_list_empty_when_no_dirs(tmp_path: Path) -> None:
    assert _store(tmp_path).list_all() == ()


def test_list_built_in_only(tmp_path: Path) -> None:
    _write_md(tmp_path / 'built-in', 'spice.saturable')
    _write_md(tmp_path / 'built-in', 'magnetics.leakage')

    entries = _store(tmp_path).list_all()

    assert len(entries) == 2
    assert {e.topic for e in entries} == {'spice.saturable', 'magnetics.leakage'}
    assert all(e.source == 'built-in' for e in entries)
    # Sorted by topic alphabetically.
    assert [e.topic for e in entries] == ['magnetics.leakage', 'spice.saturable']


def test_list_host_mutated_only(tmp_path: Path) -> None:
    _write_md(tmp_path / 'host-mutated', 'spice.user-discovery')

    entries = _store(tmp_path).list_all()

    assert len(entries) == 1
    assert entries[0].topic == 'spice.user-discovery'
    assert entries[0].source == 'host-mutated'


def test_list_host_wins_at_conflict(tmp_path: Path) -> None:
    """Host-mutated overrides built-in для совпадающего topic'а (Q-E → a)."""
    _write_md(tmp_path / 'built-in', 'spice.saturable', body='Built-in body.')
    _write_md(tmp_path / 'host-mutated', 'spice.saturable', body='Host body.')

    entries = _store(tmp_path).list_all()

    assert len(entries) == 1
    assert entries[0].source == 'host-mutated'
    assert 'Host body' in entries[0].body


def test_list_built_in_kept_for_non_conflicting(tmp_path: Path) -> None:
    _write_md(tmp_path / 'built-in', 'spice.saturable')
    _write_md(tmp_path / 'built-in', 'magnetics.leakage')
    _write_md(tmp_path / 'host-mutated', 'spice.user-extra')

    entries = _store(tmp_path).list_all()

    assert {e.topic for e in entries} == {
        'spice.saturable', 'magnetics.leakage', 'spice.user-extra',
    }


def test_list_raises_when_filename_mismatch_frontmatter_topic(
    tmp_path: Path,
) -> None:
    """Filename slug должен совпадать с frontmatter topic."""
    (tmp_path / 'built-in').mkdir()
    (tmp_path / 'built-in' / 'spice.saturable.md').write_text(
        '---\ntopic: spice.different\ndescription: x\n---\nbody\n',
        encoding='utf-8',
    )

    with pytest.raises(KbParseError, match='does not match filename'):
        _store(tmp_path).list_all()


def test_list_raises_on_bad_frontmatter(tmp_path: Path) -> None:
    (tmp_path / 'built-in').mkdir()
    (tmp_path / 'built-in' / 'spice.saturable.md').write_text(
        'no frontmatter at all\n',
        encoding='utf-8',
    )

    with pytest.raises(KbParseError):
        _store(tmp_path).list_all()


def test_get_returns_entry(tmp_path: Path) -> None:
    _write_md(tmp_path / 'built-in', 'spice.saturable')

    entry = _store(tmp_path).get('spice.saturable')

    assert entry is not None
    assert entry.topic == 'spice.saturable'


def test_get_returns_none_when_missing(tmp_path: Path) -> None:
    assert _store(tmp_path).get('missing.topic') is None


def test_add_writes_to_host_mutated_dir(tmp_path: Path) -> None:
    store = _store(tmp_path)
    entry = KbEntry(
        topic='agent.command-routing',
        description='Map user-request → slash-command',
        source='host-mutated',
        body='# Body\n\nContent.',
    )

    store.add(entry)

    written = tmp_path / 'host-mutated' / 'agent.command-routing.md'
    assert written.is_file()
    text = written.read_text(encoding='utf-8')
    assert 'topic: agent.command-routing' in text
    assert 'source:' not in text  # Analyze A7


def test_add_overrides_entry_source_field_in_file(tmp_path: Path) -> None:
    """Caller передаёт source='built-in', но add() пишет в host-mutated.

    `entry.source` в KbEntry поле — для in-memory, на disk не пишется.
    """
    store = _store(tmp_path)
    entry = KbEntry(
        topic='foo.bar',
        description='desc',
        source='built-in',  # callsite says built-in
        body='body',
    )

    store.add(entry)

    assert (tmp_path / 'host-mutated' / 'foo.bar.md').is_file()
    # built-in directory не trogata.
    assert not (tmp_path / 'built-in').is_dir()


def test_add_creates_host_dir_if_missing(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert not (tmp_path / 'host-mutated').exists()

    store.add(KbEntry(
        topic='foo.bar', description='d', source='host-mutated', body='b',
    ))

    assert (tmp_path / 'host-mutated').is_dir()


def test_add_conflict_raises_without_force(tmp_path: Path) -> None:
    _write_md(tmp_path / 'built-in', 'spice.saturable')
    store = _store(tmp_path)
    new = KbEntry(
        topic='spice.saturable', description='new desc',
        source='host-mutated', body='new body',
    )

    with pytest.raises(KbConflictError, match='spice.saturable'):
        store.add(new)


def test_add_conflict_with_force_overwrites(tmp_path: Path) -> None:
    _write_md(tmp_path / 'host-mutated', 'spice.saturable', body='Old body.')
    store = _store(tmp_path)
    new = KbEntry(
        topic='spice.saturable', description='new desc',
        source='host-mutated', body='New body.',
    )

    store.add(new, force=True)

    reloaded = store.get('spice.saturable')
    assert reloaded is not None
    assert 'New body' in reloaded.body


def test_search_returns_matching_entries(tmp_path: Path) -> None:
    _write_md(
        tmp_path / 'built-in', 'spice.saturable',
        body='XSPICE gyrator-capacitor для magnetics.', tags='spice',
    )
    _write_md(
        tmp_path / 'built-in', 'magnetics.leakage',
        body='Erickson sandwich formula.', tags='magnetics',
    )

    results = _store(tmp_path).search('gyrator')

    assert len(results) == 1
    assert results[0].topic == 'spice.saturable'


def test_search_token_and_match(tmp_path: Path) -> None:
    """Все tokens должны встретиться (Q-D → b)."""
    _write_md(
        tmp_path / 'built-in', 'spice.saturable',
        body='XSPICE gyrator-capacitor для magnetics.',
    )

    # Оба токена в body → match.
    assert len(_store(tmp_path).search('gyrator magnetics')) == 1
    # Один token отсутствует → no match.
    assert _store(tmp_path).search('gyrator nonexistent') == ()


def test_search_case_insensitive(tmp_path: Path) -> None:
    _write_md(
        tmp_path / 'built-in', 'spice.saturable',
        body='XSPICE Gyrator-Capacitor.',
    )

    assert len(_store(tmp_path).search('GYRATOR')) == 1
    assert len(_store(tmp_path).search('gyrator')) == 1


def test_search_matches_topic_description_tags(tmp_path: Path) -> None:
    """Haystack включает topic + description + tags + body."""
    _write_md(
        tmp_path / 'built-in', 'spice.saturable',
        body='Body without keyword.', tags='gyrator',
    )

    assert len(_store(tmp_path).search('gyrator')) == 1


def test_search_empty_query_returns_empty(tmp_path: Path) -> None:
    _write_md(tmp_path / 'built-in', 'spice.saturable')

    assert _store(tmp_path).search('') == ()
    assert _store(tmp_path).search('   ') == ()
