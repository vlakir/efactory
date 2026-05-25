"""Unit-тесты TemplateMaterializer (T014 Phase A)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from adapters.inbound.cli import template_materializer
from adapters.inbound.cli.template_materializer import (
    PROJECT_NAME_PLACEHOLDER,
    TemplateConflictError,
    TemplateNotFoundError,
    _sanitize_filename,
    list_templates,
    materialize_template,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def fake_templates_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Подменить TEMPLATES_ROOT, чтобы тест не зависел от shipping baked content."""
    root = tmp_path / 'templates'
    root.mkdir()
    monkeypatch.setattr(template_materializer, 'TEMPLATES_ROOT', root)
    return root


def _make_template(root: Path, name: str, files: dict[str, str]) -> Path:
    template_dir = root / name
    template_dir.mkdir()
    for rel_path, content in files.items():
        file_path = template_dir / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding='utf-8')
    return template_dir


class TestListTemplates:
    def test_empty_root_returns_empty(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(template_materializer, 'TEMPLATES_ROOT', tmp_path / 'missing')
        assert list_templates() == []

    def test_returns_subdir_names_sorted(self, fake_templates_root: Path) -> None:
        (fake_templates_root / 'zzz').mkdir()
        (fake_templates_root / 'aaa').mkdir()
        assert list_templates() == ['aaa', 'zzz']

    def test_skips_dot_dirs(self, fake_templates_root: Path) -> None:
        (fake_templates_root / 'se-amp').mkdir()
        (fake_templates_root / '.hidden').mkdir()
        assert list_templates() == ['se-amp']

    def test_skips_files(self, fake_templates_root: Path) -> None:
        (fake_templates_root / 'README.md').write_text('top-level readme')
        (fake_templates_root / 'se-amp').mkdir()
        assert list_templates() == ['se-amp']


class TestSanitizeFilename:
    @pytest.mark.parametrize(
        ('raw', 'expected'),
        [
            ('simple', 'simple'),
            ('my-amp-v2', 'my-amp-v2'),
            ('my amp', 'my_amp'),
            ('a/b', 'a_b'),
            ('two words /slash', 'two_words__slash'),
        ],
    )
    def test_replaces_spaces_and_slash(self, raw: str, expected: str) -> None:
        assert _sanitize_filename(raw) == expected


class TestMaterializeTemplate:
    def test_unknown_template_raises_with_available_list(
        self,
        tmp_path: Path,
        fake_templates_root: Path,
    ) -> None:
        _make_template(fake_templates_root, 'se-amp', {'a.txt': 'x'})
        target = tmp_path / 'project'
        target.mkdir()

        with pytest.raises(TemplateNotFoundError) as exc_info:
            materialize_template('nonexistent', target, 'foo')
        assert 'se-amp' in str(exc_info.value)
        assert 'nonexistent' in str(exc_info.value)

    def test_target_dir_missing_raises(
        self,
        tmp_path: Path,
        fake_templates_root: Path,
    ) -> None:
        _make_template(fake_templates_root, 'se-amp', {'a.txt': 'x'})
        target = tmp_path / 'does-not-exist'
        with pytest.raises(ValueError, match='Target dir does not exist'):
            materialize_template('se-amp', target, 'foo')

    def test_copies_files_to_target(
        self,
        tmp_path: Path,
        fake_templates_root: Path,
    ) -> None:
        _make_template(
            fake_templates_root,
            'se-amp',
            {
                'foo.kicad_sch': 'schematic body',
                'models/lib.txt': 'lib body',
            },
        )
        target = tmp_path / 'project'
        target.mkdir()

        materialize_template('se-amp', target, 'demo')

        assert (target / 'foo.kicad_sch').read_text() == 'schematic body'
        assert (target / 'models' / 'lib.txt').read_text() == 'lib body'

    def test_filename_substitution(
        self,
        tmp_path: Path,
        fake_templates_root: Path,
    ) -> None:
        _make_template(
            fake_templates_root,
            'se-amp',
            {
                f'{PROJECT_NAME_PLACEHOLDER}.kicad_sch': 'sch',
                f'{PROJECT_NAME_PLACEHOLDER}.kicad_pro': 'pro',
            },
        )
        target = tmp_path / 'project'
        target.mkdir()

        materialize_template('se-amp', target, 'my-amp-v2')

        assert (target / 'my-amp-v2.kicad_sch').exists()
        assert (target / 'my-amp-v2.kicad_pro').exists()
        assert not (target / f'{PROJECT_NAME_PLACEHOLDER}.kicad_sch').exists()

    def test_content_substitution_in_text_files(
        self,
        tmp_path: Path,
        fake_templates_root: Path,
    ) -> None:
        _make_template(
            fake_templates_root,
            'se-amp',
            {
                'cfg.yaml': f'name: {PROJECT_NAME_PLACEHOLDER}\n',
                f'{PROJECT_NAME_PLACEHOLDER}.kicad_pro': (
                    f'{{"filename": "{PROJECT_NAME_PLACEHOLDER}.kicad_pro"}}'
                ),
            },
        )
        target = tmp_path / 'project'
        target.mkdir()

        materialize_template('se-amp', target, 'foo')

        assert (target / 'cfg.yaml').read_text() == 'name: foo\n'
        assert (
            (target / 'foo.kicad_pro').read_text()
            == '{"filename": "foo.kicad_pro"}'
        )

    def test_non_text_files_get_filename_substitution_but_content_unchanged(
        self,
        tmp_path: Path,
        fake_templates_root: Path,
    ) -> None:
        """Filename substitution применяется ко всем файлам, content — только к text."""
        # Содержимое умышленно включает токен — он не должен подставиться
        # для бинарных расширений (rule: substitute content только в текстовых).
        _make_template(
            fake_templates_root,
            'se-amp',
            {f'models/{PROJECT_NAME_PLACEHOLDER}.bin': f'body {PROJECT_NAME_PLACEHOLDER} body'},
        )
        target = tmp_path / 'project'
        target.mkdir()

        materialize_template('se-amp', target, 'foo')

        renamed = target / 'models' / 'foo.bin'
        assert renamed.exists()
        # .bin не в _TEXT_EXTENSIONS — content substitution не сработал
        assert renamed.read_text() == f'body {PROJECT_NAME_PLACEHOLDER} body'

    def test_template_metadata_files_excluded(
        self,
        tmp_path: Path,
        fake_templates_root: Path,
    ) -> None:
        _make_template(
            fake_templates_root,
            'se-amp',
            {
                'template.yaml': 'description: foo',
                'README.md': 'docs',
                'sch.kicad_sch': 'sch',
            },
        )
        target = tmp_path / 'project'
        target.mkdir()

        materialize_template('se-amp', target, 'foo')

        assert (target / 'sch.kicad_sch').exists()
        assert not (target / 'template.yaml').exists()
        assert not (target / 'README.md').exists()

    def test_conflict_with_existing_file_raises_before_writing(
        self,
        tmp_path: Path,
        fake_templates_root: Path,
    ) -> None:
        _make_template(
            fake_templates_root,
            'se-amp',
            {'foo.kicad_sch': 'new content', 'bar.txt': 'bar'},
        )
        target = tmp_path / 'project'
        target.mkdir()
        (target / 'foo.kicad_sch').write_text('existing')

        with pytest.raises(TemplateConflictError, match='foo.kicad_sch'):
            materialize_template('se-amp', target, 'foo')

        # bar.txt не должен был записаться (pre-scan failed before writing)
        assert not (target / 'bar.txt').exists()
        # existing файл не тронут
        assert (target / 'foo.kicad_sch').read_text() == 'existing'

    def test_name_with_space_sanitized_in_filename(
        self,
        tmp_path: Path,
        fake_templates_root: Path,
    ) -> None:
        _make_template(
            fake_templates_root,
            'se-amp',
            {f'{PROJECT_NAME_PLACEHOLDER}.kicad_sch': PROJECT_NAME_PLACEHOLDER},
        )
        target = tmp_path / 'project'
        target.mkdir()

        materialize_template('se-amp', target, 'my amp')

        assert (target / 'my_amp.kicad_sch').exists()
        assert (target / 'my_amp.kicad_sch').read_text() == 'my_amp'
