"""KB control-example regression tests (T134 Phase E).

10 lessons, которые должны быть представлены в built-in seed:
- 3 из T131 (XSPICE gyrator-cap, R_dc_leak, saturation contribution).
- 3 из T132 (PyOM leakage broken, interleaving N², PyOM bobbin patch).
- 3 из T133 (2D-planar gap, MUMPS ceiling, Stranded Coil loop).
- 1 новый: agent.command-routing (typical scenarios mapping).

Каждый case: free-text query + expected_topic + expected_directive
(key term который должен быть в body). Test deterministic через
`FileSystemKbStore.search()` / `.get()`, без LLM-judge.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from adapters.outbound.knowledge_base_filesystem.store import FileSystemKbStore

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BUILT_IN_DIR = _REPO_ROOT / 'docker' / 'runtime-agent-knowledge-base'


@pytest.fixture
def store(tmp_path: Path) -> FileSystemKbStore:
    """Store на real built-in seed + tmp host-mutated."""
    return FileSystemKbStore(
        built_in_dir=_BUILT_IN_DIR,
        host_mutated_dir=tmp_path / 'host-mutated',
    )


# Каждый case — (free-text query, expected topic, key term in body).
_CONTROL_EXAMPLES: list[tuple[str, str, str]] = [
    # T131: 3 lessons.
    (
        'saturable XSPICE gyrator',
        'spice.saturable-gyrator-cap',
        'gyrator',
    ),
    (
        'floating secondary fourier dc reference',
        'spice.floating-secondary-leak',
        'r_dc_leak',
    ),
    (
        'saturation contribution metric thd diagnostic',
        'spice.saturation-contribution-metric',
        'thd@f_low',
    ),
    # T132: 3 lessons.
    (
        'pyom calculate_leakage_inductance mesh',
        'magnetics.pyom-leakage-broken',
        'erickson',
    ),
    (
        'interleaving HF rolloff leakage reduction',
        'magnetics.interleaving-n-squared',
        '1/n²',
    ),
    (
        'pyom bobbin columnwidth uninitialized',
        'magnetics.pyom-bobbin-patch',
        'patch',
    ),
    # T133: 3 lessons.
    (
        '2d planar fem zhang e-core gap',
        'fem.2d-planar-zhang-gap',
        '3d mesh',
    ),
    (
        'elmer 3d mumps mesh memory ceiling',
        'fem.elmer-3d-mumps-ceiling',
        'mumps',
    ),
    (
        'elmer stranded coil opt primary disjoint',
        'fem.elmer-stranded-coil-loop',
        'bridge',
    ),
    # +1 новый: agent.command-routing (Q-I → b).
    (
        'построй график ачх typical mapping',
        'agent.command-routing',
        '/plot-ac',
    ),
    # T022 Phase D Level 2 — KB sync regression для /sweep.
    (
        'параметрический sweep варьировать Rk таблица gain',
        'agent.command-routing',
        '/sweep',
    ),
    # T021 Phase C Level 2 — KB sync regression для /edit-and-resim.
    (
        'what-if delta gain bandwidth',
        'agent.command-routing',
        '/edit-and-resim',
    ),
    # T153 Phase B.6 Level 2 — KB sync regression для /measure-phase-margin.
    (
        'запас по фазе стабильность петли phase margin',
        'agent.command-routing',
        '/measure-phase-margin',
    ),
    # T153 Phase B.7 Level 2 — KB sync regression для /edit-and-resim
    # с phase-margin метрикой (delta после правки feedback резистора).
    (
        'как изменится запас по фазе если поменять R_fb',
        'agent.command-routing',
        '--measure phase-margin',
    ),
]


@pytest.mark.parametrize(
    ('query', 'expected_topic', 'expected_directive'),
    _CONTROL_EXAMPLES,
    ids=[t for _, t, _ in _CONTROL_EXAMPLES],
)
def test_control_example_finds_expected_topic(
    store: FileSystemKbStore,
    query: str,
    expected_topic: str,
    expected_directive: str,
) -> None:
    """Search возвращает entry → entry.body содержит key directive."""
    results = store.search(query)
    topics = {entry.topic for entry in results}
    assert expected_topic in topics, (
        f'query {query!r}: expected topic {expected_topic!r}, '
        f'got {sorted(topics)}'
    )

    entry = store.get(expected_topic)
    assert entry is not None
    assert expected_directive.lower() in entry.body.lower(), (
        f'entry {expected_topic!r}: expected directive '
        f'{expected_directive!r} in body, not found'
    )


def test_all_ten_seed_entries_exist(store: FileSystemKbStore) -> None:
    """10 built-in seed entries присутствуют в built_in_dir."""
    entries = store.list_all()
    topics = {entry.topic for entry in entries}
    expected = {topic for _, topic, _ in _CONTROL_EXAMPLES}
    assert expected.issubset(topics), (
        f'missing entries: {expected - topics}'
    )
    # Все должны быть built-in source.
    for entry in entries:
        if entry.topic in expected:
            assert entry.source == 'built-in', (
                f'{entry.topic} expected source=built-in, '
                f'got {entry.source}'
            )


def test_seed_entries_have_expected_namespaces(store: FileSystemKbStore) -> None:
    """Namespace coverage: spice/magnetics/fem/agent (4 ns)."""
    namespaces = {entry.namespace for entry in store.list_all()}
    expected_namespaces = {'spice', 'magnetics', 'fem', 'agent'}
    assert expected_namespaces.issubset(namespaces)
