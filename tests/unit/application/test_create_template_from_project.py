"""create_template_from_project use case tests (T177)."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.create_template_from_project import (
    CreateTemplateError,
    CreateTemplateRequest,
    create_template_from_project,
)


def _make_project(root: Path, name: str = 'p1') -> Path:
    """Создать stub project с .kicad_sch + .kicad_pro + models/X.lib."""
    proj = root / name
    proj.mkdir(parents=True)
    (proj / f'{name}.kicad_sch').write_text(
        '(kicad_sch (uuid "stub")\n  (lib_symbols))\n', encoding='utf-8'
    )
    (proj / f'{name}.kicad_pro').write_text(
        '{"meta": {"filename": "p1.kicad_pro"}}', encoding='utf-8'
    )
    (proj / 'project.yaml').write_text('id: stub\nname: p1\n', encoding='utf-8')
    (proj / 'models').mkdir()
    (proj / 'models' / 'CUSTOM.lib').write_text(
        '.SUBCKT CUSTOM A B\nR1 A B 1k\n.ENDS\n', encoding='utf-8'
    )
    # Noise that should NOT be copied:
    (proj / 'sim').mkdir()
    (proj / 'sim' / 'cached.cir').write_text('* stale\n', encoding='utf-8')
    (proj / f'{name}.kicad_prl').write_text('{}', encoding='utf-8')
    return proj


# ============================== Happy path ==============================


def test_create_template_promotes_files(tmp_path: Path) -> None:
    proj = _make_project(tmp_path / 'projects', 'mic-preamp-6zh32p')
    target_root = tmp_path / 'overlay' / 'templates'
    target_root.mkdir(parents=True)

    result = create_template_from_project(
        CreateTemplateRequest(
            project_dir=proj,
            template_name='custom-mic',
            target_root=target_root,
            summary='Custom mic preamp',
        )
    )

    assert result.template_dir == target_root / 'custom-mic'
    assert result.template_dir.is_dir()
    # Placeholder-renamed files
    assert (result.template_dir / '{{PROJECT_NAME}}.kicad_sch').is_file()
    assert (result.template_dir / '{{PROJECT_NAME}}.kicad_pro').is_file()
    # Models copied (not renamed)
    assert (result.template_dir / 'models' / 'CUSTOM.lib').is_file()
    # Stubs generated
    assert (result.template_dir / 'template.yaml').is_file()
    assert (result.template_dir / 'README.md').is_file()
    # Excluded files NOT copied
    assert not (result.template_dir / 'project.yaml').exists()
    assert not (result.template_dir / 'sim').exists()
    assert not (result.template_dir / '{{PROJECT_NAME}}.kicad_prl').exists()
    # Summary in yaml
    yaml = (result.template_dir / 'template.yaml').read_text()
    assert 'summary: Custom mic preamp' in yaml


def test_create_template_files_copied_count(tmp_path: Path) -> None:
    proj = _make_project(tmp_path / 'projects')
    target_root = tmp_path / 'overlay'
    target_root.mkdir()

    result = create_template_from_project(
        CreateTemplateRequest(
            project_dir=proj,
            template_name='c1',
            target_root=target_root,
        )
    )
    # Expected: .kicad_sch + .kicad_pro + models/CUSTOM.lib = 3 files
    # (project.yaml + sim/ + .kicad_prl skipped)
    assert result.files_copied == 3


# ============================== Errors ==============================


def test_create_template_missing_project_raises(tmp_path: Path) -> None:
    with pytest.raises(CreateTemplateError, match='not found'):
        create_template_from_project(
            CreateTemplateRequest(
                project_dir=tmp_path / 'absent',
                template_name='t',
                target_root=tmp_path,
            )
        )


def test_create_template_missing_schematic_raises(tmp_path: Path) -> None:
    proj = tmp_path / 'bad-proj'
    proj.mkdir()
    (proj / 'project.yaml').write_text('stub', encoding='utf-8')

    with pytest.raises(CreateTemplateError, match='schematic not found'):
        create_template_from_project(
            CreateTemplateRequest(
                project_dir=proj,
                template_name='t',
                target_root=tmp_path,
            )
        )


def test_create_template_conflict_without_force(tmp_path: Path) -> None:
    proj = _make_project(tmp_path / 'projects')
    target_root = tmp_path / 'overlay'
    target_root.mkdir()
    (target_root / 'existing').mkdir()  # squat the target

    with pytest.raises(CreateTemplateError, match='already exists'):
        create_template_from_project(
            CreateTemplateRequest(
                project_dir=proj,
                template_name='existing',
                target_root=target_root,
            )
        )


def test_create_template_force_overwrites(tmp_path: Path) -> None:
    proj = _make_project(tmp_path / 'projects')
    target_root = tmp_path / 'overlay'
    target_root.mkdir()
    existing = target_root / 'existing'
    existing.mkdir()
    (existing / 'stale.txt').write_text('stale', encoding='utf-8')

    result = create_template_from_project(
        CreateTemplateRequest(
            project_dir=proj,
            template_name='existing',
            target_root=target_root,
            force=True,
        )
    )
    assert not (result.template_dir / 'stale.txt').exists()
    assert (result.template_dir / '{{PROJECT_NAME}}.kicad_sch').is_file()
