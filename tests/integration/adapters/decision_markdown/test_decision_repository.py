"""Integration: FilesystemDecisionRepository через реальный tmp_path (T099)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from adapters.outbound.decision_markdown.decision_repository import (
    FilesystemDecisionRepository,
    _slugify,
)
from domain.decision import Decision, DecisionStatus
from ports.outbound.decision_repository import (
    DecisionInvalidError,
    DecisionNotFoundError,
)


def _decision(
    decision_id: str = 'D001',
    title: str = 'Test Decision',
    **kwargs: object,
) -> Decision:
    defaults: dict[str, object] = {
        'id': decision_id,
        'title': title,
        'date': date(2026, 5, 17),
        'status': DecisionStatus.ACCEPTED,
        'summary': 'Short summary',
        'rationale': 'Detailed rationale',
    }
    defaults.update(kwargs)
    return Decision.model_validate(defaults)


async def test_save_creates_decisions_dir_and_file(tmp_path: Path) -> None:
    repo = FilesystemDecisionRepository()

    written = await repo.save(tmp_path, _decision())

    assert (tmp_path / 'decisions').is_dir()
    assert written.name == 'D001_test-decision.md'
    assert written.is_file()


async def test_save_writes_template_with_required_sections(tmp_path: Path) -> None:
    repo = FilesystemDecisionRepository()
    decision = _decision()

    written = await repo.save(tmp_path, decision)

    content = written.read_text(encoding='utf-8')
    assert content.startswith('# D001: Test Decision\n')
    assert '**Дата:** 2026-05-17' in content
    assert '**Статус:** accepted' in content
    assert '## Summary\nShort summary' in content
    assert '## Rationale\nDetailed rationale' in content
    # Без evidence/session — секции не появляются.
    assert '## Evidence' not in content
    assert '**Сессия:**' not in content


async def test_save_includes_optional_evidence_and_session(tmp_path: Path) -> None:
    repo = FilesystemDecisionRepository()
    decision = _decision(
        evidence=Path('sim/ac.json'),
        session=Path('sessions/session_001.json'),
    )

    written = await repo.save(tmp_path, decision)

    content = written.read_text(encoding='utf-8')
    assert '**Сессия:** sessions/session_001.json' in content
    assert '## Evidence\nsim/ac.json' in content


async def test_save_and_load_round_trip_preserves_all_fields(tmp_path: Path) -> None:
    repo = FilesystemDecisionRepository()
    original = _decision(
        evidence=Path('sim/ac.json'),
        session=Path('sessions/session_001.json'),
    )

    await repo.save(tmp_path, original)
    loaded = await repo.load(tmp_path, 'D001')

    assert loaded == original


async def test_save_atomic_does_not_leave_tmp_files(tmp_path: Path) -> None:
    repo = FilesystemDecisionRepository()

    await repo.save(tmp_path, _decision())

    decisions_dir = tmp_path / 'decisions'
    leftovers = [p for p in decisions_dir.iterdir() if p.name.endswith('.tmp')]
    assert leftovers == []


async def test_load_missing_file_raises_decision_not_found(tmp_path: Path) -> None:
    repo = FilesystemDecisionRepository()
    (tmp_path / 'decisions').mkdir()

    with pytest.raises(DecisionNotFoundError):
        await repo.load(tmp_path, 'D999')


async def test_load_missing_decisions_dir_raises_decision_not_found(
    tmp_path: Path,
) -> None:
    repo = FilesystemDecisionRepository()

    with pytest.raises(DecisionNotFoundError):
        await repo.load(tmp_path, 'D001')


async def test_load_corrupt_markdown_raises_decision_invalid(tmp_path: Path) -> None:
    repo = FilesystemDecisionRepository()
    decisions_dir = tmp_path / 'decisions'
    decisions_dir.mkdir()
    (decisions_dir / 'D001_x.md').write_text(
        'не markdown без заголовка', encoding='utf-8',
    )

    with pytest.raises(DecisionInvalidError):
        await repo.load(tmp_path, 'D001')


async def test_load_ignores_unknown_sections_keeps_required(tmp_path: Path) -> None:
    """C1: пользователь добавил `## Контекст` руками — load всё равно работает."""
    repo = FilesystemDecisionRepository()
    decisions_dir = tmp_path / 'decisions'
    decisions_dir.mkdir()
    (decisions_dir / 'D001_x.md').write_text(
        '# D001: Manual\n\n'
        '**Дата:** 2026-05-17\n'
        '**Статус:** accepted\n\n'
        '## Context\nкакой-то контекст\n\n'
        '## Summary\ns\n\n'
        '## Rationale\nr\n\n'
        '## Notes\nкакие-то заметки\n',
        encoding='utf-8',
    )

    decision = await repo.load(tmp_path, 'D001')

    assert decision.title == 'Manual'
    assert decision.summary == 's'
    assert decision.rationale == 'r'


async def test_list_all_empty_when_no_decisions_dir(tmp_path: Path) -> None:
    repo = FilesystemDecisionRepository()

    assert await repo.list_all(tmp_path) == []


async def test_list_all_returns_sorted_by_numeric_id(tmp_path: Path) -> None:
    repo = FilesystemDecisionRepository()
    await repo.save(tmp_path, _decision('D010', title='ten'))
    await repo.save(tmp_path, _decision('D002', title='two'))
    await repo.save(tmp_path, _decision('D100', title='hundred'))
    await repo.save(tmp_path, _decision('D009', title='nine'))

    result = await repo.list_all(tmp_path)

    assert [d.id for d in result] == ['D002', 'D009', 'D010', 'D100']


async def test_list_all_skips_non_decision_files(tmp_path: Path) -> None:
    repo = FilesystemDecisionRepository()
    await repo.save(tmp_path, _decision())
    (tmp_path / 'decisions' / 'README.md').write_text('not a decision')
    (tmp_path / 'decisions' / 'foo_bar.txt').write_text('not markdown')

    result = await repo.list_all(tmp_path)

    assert [d.id for d in result] == ['D001']


async def test_next_id_returns_d001_for_empty_dir(tmp_path: Path) -> None:
    repo = FilesystemDecisionRepository()

    assert await repo.next_id(tmp_path) == 'D001'


async def test_next_id_increments_from_max(tmp_path: Path) -> None:
    repo = FilesystemDecisionRepository()
    await repo.save(tmp_path, _decision('D001'))
    await repo.save(tmp_path, _decision('D003'))

    assert await repo.next_id(tmp_path) == 'D004'


async def test_next_id_handles_four_digit_max(tmp_path: Path) -> None:
    repo = FilesystemDecisionRepository()
    await repo.save(tmp_path, _decision('D999'))

    assert await repo.next_id(tmp_path) == 'D1000'


@pytest.mark.parametrize(
    ('title', 'expected_slug'),
    [
        ('Hello World', 'hello-world'),
        ('  Trim  Me  ', 'trim-me'),
        ('Punctuation!?+', 'punctuation'),
        ('Choose SE topology', 'choose-se-topology'),
        ('SUPER_long_name_with_underscores', 'super-long-name-with-underscores'),
    ],
)
def test_slugify_ascii(title: str, expected_slug: str) -> None:
    assert _slugify(title) == expected_slug


def test_slugify_cyrillic_falls_back_to_untitled() -> None:
    """W2: кириллица без транслита → fallback untitled."""
    assert _slugify('Выбор SE-топологии') == 'se'  # ascii часть выживает


def test_slugify_pure_cyrillic_is_untitled() -> None:
    assert _slugify('Только кириллица') == 'untitled'


def test_slugify_caps_length_at_fifty() -> None:
    long = 'a' * 100
    assert len(_slugify(long)) == 50
