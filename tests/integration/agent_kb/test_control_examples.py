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
    # T153 Phase C.1.8 Level 2 — KB sync regression для break point
    # convention (op-amp output side для Middlebrook V).
    (
        'op-amp inverting phase margin break node middlebrook',
        'spice.feedback-break-point',
        'low-Z driver',
    ),
    # T153 Phase C.3 Level 2 — KB sync regression для tube NFB
    # canonical break (OPT secondary → feedback chain) + per-topology
    # applicability matrix (tube only-V).
    (
        'tube NFB SE amp phase margin break OPT secondary feedback',
        'spice.feedback-break-point',
        'sec_a',
    ),
    # T164 Level 2 — KB sync regression для auto-detect refinement
    # (multi-active boost + stimulus-distance ranking — tube NFB
    # auto-detect at threshold 0.7, op-amp invariance к KiCad ordering).
    (
        'auto-detect phase margin tube NFB threshold confidence',
        'spice.feedback-break-point',
        'threshold 0.7',
    ),
    # T163 Level 2 — KB sync regression для BJT CE shunt-shunt NFB
    # canonical break (collector → DC-block, analog к tube) + per-method
    # matrix row (V+Tian strict, I+Rosenstark degenerate).
    (
        'BJT common emitter shunt feedback phase margin break',
        'spice.feedback-break-point',
        'C_F',
    ),
    # T027 Phase A Level 2 — KB sync regression для tube push-pull amp
    # template (LTP splitter vs concertina ADR-T027a) + agent routing
    # mapping для «ламповый PP / двухтактный».
    (
        'tube push pull amp LTP splitter',
        'spice.tube-push-pull',
        'LTP',
    ),
    (
        'создай ламповый push-pull проект',
        'agent.command-routing',
        'tube-pp-amp',
    ),
    # T027 Phase B Level 2 — KB sync regression для tube-line-preamp
    # template (CC+CF cascade) + agent routing mapping для «ламповый
    # preamp / buffer».
    (
        'tube line preamp cathode follower CF cascade',
        'spice.tube-line-preamp',
        'CF',
    ),
    (
        'создай ламповый preamp проект',
        'agent.command-routing',
        'tube-line-preamp',
    ),
    # T027 Phase C Level 2 — KB sync regression для tube-phono-riaa
    # (12AX7 + passive RIAA inter-stage Lipshitz design) + agent routing
    # mapping для phono / винил preamp / MM cartridge.
    (
        'phono preamp RIAA passive inter-stage Lipshitz',
        'spice.tube-phono-riaa',
        'Lipshitz',
    ),
    (
        'создай винил phono RIAA проект',
        'agent.command-routing',
        'tube-phono-riaa',
    ),
    # T027 Phase C addendum (Vladimir request 2026-06-02) — KB sync
    # для convert_pwrs_to_ngspice converter и Koren/Ayumi HSPICE-syntax
    # compatibility issues.
    (
        'ngspice PWRS error tube model HSPICE syntax',
        'spice.ngspice-syntax-compat',
        'convert_pwrs_to_ngspice',
    ),
    # T027 Phase D Level 2 — KB sync для Sallen-Key active filter
    # template + agent routing mapping для «LPF / active filter».
    (
        'Sallen-Key Butterworth active filter LPF design',
        'spice.active-filter-sallen-key',
        'Butterworth',
    ),
    (
        'создай active filter LPF проект',
        'agent.command-routing',
        'active-lpf-sallen-key',
    ),
    # T025 Phase C — L2 regression для schematic visualization routing.
    (
        'покажи схему отрисуй проект как выглядит render schematic',
        'agent.command-routing',
        'schematic-render',
    ),
    # T025 Q1 v2 — L2 regression для plot graphical output routing.
    (
        'покажи график в окне графически show plot',
        'agent.command-routing',
        'plot-render',
    ),
    # T025 Q1 v2 — L2 anti-pattern: ad-hoc matplotlib запрещён.
    (
        'matplotlib python script ad-hoc plot waveform',
        'agent.command-routing',
        'ad-hoc',
    ),
    # T026 Phase 2 — L2 regression: routing «apply staged» → /schematic-apply.
    (
        'применить отложенные изменения apply staged schematic',
        'agent.command-routing',
        '/schematic-apply',
    ),
    # T026 Phase 2 — L2 regression: KB topic schematic.staged-modifications
    # содержит ключевые директивы про --force vs --accept-overwrite разделение.
    (
        'staged kicad sch parent hash lock force accept overwrite',
        'schematic.staged-modifications',
        '--accept-overwrite',
    ),
    # T026 L3 follow-up — L2 regression: routing «покажи состояние проекта» →
    # CLI project show (а не ad-hoc ls обзор), чтобы T026 warnings не терялись.
    (
        'покажи состояние проекта статус summary',
        'agent.command-routing',
        'efactory project show',
    ),
    (
        'список проектов какие проекты есть list projects',
        'agent.command-routing',
        'efactory project list',
    ),
    # T031 Phase 3 — L2 regression: routing «добавь модель лампы из datasheet»
    # → /tube-add-from-datasheet (vision-extract pipeline).
    (
        'добавь модель лампы из datasheet PDF 6Ж38П extract',
        'agent.command-routing',
        '/tube-add-from-datasheet',
    ),
    # T031 Phase 3 — L2 regression: KB topic tubes.curve-fitting
    # содержит ключевые директивы про KG2 fallback (Ia-only path) и
    # canonical 2× множитель в Koren formula.
    (
        'KG2 typical ratio Ia-only pentode screen current fitting',
        'tubes.curve-fitting',
        'typical ratio',
    ),
    # T031 Phase 5 — L2 regression: routing «RF preamp 6Ж38П / IF amp
    # sharp-cutoff» → /project-create + template 6zh38p-if-amp.
    (
        'RF preamp 6Ж38П IF amplifier sharp-cutoff pentode 6BH6',
        'agent.command-routing',
        '6zh38p-if-amp',
    ),
    # T031 Phase 5 — L2 regression: routing «SE amp 6П13С без OPT» →
    # /project-create + template 6p13s-se-resistive.
    (
        'SE amp 6П13С output без OPT резистивная нагрузка beam tetrode',
        'agent.command-routing',
        '6p13s-se-resistive',
    ),
    # T031 Phase 5 — L2 regression: KB topic spice.tube-rf-amp-6zh38p
    # содержит ключевые директивы про default op-point + topology.
    (
        '6zh38p class A resistance-coupled preamp Vbb plate cathode bias',
        'spice.tube-rf-amp-6zh38p',
        'resistance-coupled',
    ),
    # T031 Phase 5 — L2 regression: KB topic spice.tube-se-resistive-6p13s
    # содержит ключевые директивы про A-W3 pattern + T173 refined bias.
    (
        '6p13s SE resistive load A-W3 Rk 470 cathode bias screen dissipation',
        'spice.tube-se-resistive-6p13s',
        'a-w3',
    ),
    # T031 Phase 6 — L2 regression: routing «микрофонный преамп 6Ж32П» →
    # /project-create + template 6zh32p-mic-preamp (agent-built).
    (
        'микрофонный преамп 6Ж32П EF86 low-noise pentode mic',
        'agent.command-routing',
        '6zh32p-mic-preamp',
    ),
    # T031 Phase 6 — L2 regression: KB topic spice.tube-mic-preamp-6zh32p
    # содержит default op-point + bandwidth measurements + agent provenance.
    (
        '6zh32p mic preamp 40 dB common-cathode pentode self-bias bandwidth',
        'spice.tube-mic-preamp-6zh32p',
        '40.76 db',
    ),
    # T177 Phase 7 — L2 regression: routing «сохрани проект как шаблон»
    # → /template create-from-project (persistent overlay CLI).
    (
        'сохрани проект как шаблон template promote reusable save',
        'agent.command-routing',
        'template create-from-project',
    ),
    # T177 Phase 7 — L2 regression: KB topic tubes.curve-fitting
    # содержит секцию о persistent overlay (избегает повторения
    # pre-T177 bug agent'ом).
    (
        'persistent agent overlay bind-mount transient pre-T177 user_library_root',
        'tubes.curve-fitting',
        'persistent',
    ),
    # T182/T184/T186 cleanup — L2 regression: KB topic
    # tubes.formula-variant-choice содержит decision tree для агента
    # (когда modified-knee/modified-cutoff/canonical).
    (
        'koren modified knee pentode formula variant choice 300B power triode '
        'cutoff edge',
        'tubes.formula-variant-choice',
        'modified-cutoff',
    ),
    # T182 cleanup — L2 regression: routing «300B model strong cutoff fit triode»
    # → efactory tube fit-from-points + --formula-variant koren-modified-cutoff.
    (
        '300B model strong cutoff routing slash command',
        'agent.command-routing',
        'koren-modified-cutoff',
    ),
    # T029 Phase 5: ERC quality gate topic + routing.
    (
        'erc quality gate kicad schematic check exit codes',
        'design.erc-quality-gate',
        'power_pin_not_driven',
    ),
    (
        'check schematic for errors design check ERC',
        'agent.command-routing',
        '/design-check',
    ),
    # T187 Phase 3: off-grid endpoint diagnostic topic + routing.
    (
        'off-grid endpoint diagnostic kicad connection grid 1.27 mm',
        'design.grid-check',
        'endpoint_off_grid',
    ),
    (
        'check schematic grid alignment components off grid',
        'agent.command-routing',
        '/grid-check',
    ),
    # T030 Phase 5: SPICE import pipeline topic + routing.
    (
        'spice model import URL vendor BJT MOSFET diode op-amp pipeline',
        'spice.import-pipeline',
        '/spice-import-url',
    ),
    (
        'импортируй модель из URL vendor',
        'agent.command-routing',
        '/spice-import-url',
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
    """Namespace coverage: spice/magnetics/fem/agent/schematic/tubes (6 ns после T031)."""
    namespaces = {entry.namespace for entry in store.list_all()}
    expected_namespaces = {
        'spice',
        'magnetics',
        'fem',
        'agent',
        'schematic',
        'tubes',
    }
    assert expected_namespaces.issubset(namespaces)
