"""E2E: portability acceptance — manifest = truth (T098 § 4).

Сценарий из spec:
1. create demo + update phase schematic → in_progress.
2. tar czf storage_root/demo → tgz.
3. rm -rf storage_root/demo + rm index.db.
4. tar xzf tgz → storage_root/demo.
5. efactory project reindex → indexed=1.
6. efactory project show demo → отражает phase in_progress.

Главное обещание efactory: проект самодостаточен и портативен;
SQL — частная деталь машины, не источник истины.
"""

from __future__ import annotations

import shutil
import tarfile
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from composition.main import build_cli_app

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_project_survives_tar_rm_index_restore_reindex_cycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_root = tmp_path / 'storage'
    db_file = tmp_path / 'efactory.sqlite'
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(storage_root))
    monkeypatch.setenv(
        'EFACTORY_DATABASE_URL',
        f'sqlite+aiosqlite:///{db_file}',
    )
    runner = CliRunner()

    create_result = runner.invoke(
        build_cli_app(), ['project', 'create', '--name', 'demo'],
    )
    assert create_result.exit_code == 0, create_result.output

    update_result = runner.invoke(
        build_cli_app(),
        [
            'project', 'update', 'demo',
            '--phase', 'schematic',
            '--status', 'in_progress',
        ],
    )
    assert update_result.exit_code == 0, update_result.output

    project_dir = storage_root / 'demo'
    manifest_text_before = (project_dir / 'project.yaml').read_text(
        encoding='utf-8',
    )
    assert 'in_progress' in manifest_text_before

    tgz_path = tmp_path / 'demo.tgz'
    with tarfile.open(tgz_path, 'w:gz') as tgz:
        tgz.add(project_dir, arcname='demo')

    shutil.rmtree(project_dir)
    db_file.unlink()
    assert not project_dir.exists()
    assert not db_file.exists()

    with tarfile.open(tgz_path, 'r:gz') as tgz:
        tgz.extractall(storage_root, filter='data')
    assert (project_dir / 'project.yaml').is_file()

    reindex_result = runner.invoke(build_cli_app(), ['project', 'reindex'])
    assert reindex_result.exit_code == 0, reindex_result.output
    assert 'Reindexed 1 projects.' in reindex_result.output

    show_result = runner.invoke(
        build_cli_app(), ['project', 'show', '--name', 'demo'],
    )
    assert show_result.exit_code == 0, show_result.output
    assert 'schematic' in show_result.output
    assert 'in_progress' in show_result.output
