"""Integration: SubprocessGitRepository через реальный `git` CLI (T010)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from adapters.outbound.git_subprocess.git_repository import (
    SubprocessGitRepository,
)
from ports.outbound.git_repository import (
    GitOperationError,
    GitUnavailableError,
)

_GIT_AVAILABLE = shutil.which('git') is not None
needs_git = pytest.mark.skipif(
    not _GIT_AVAILABLE,
    reason='git CLI not installed',
)


@needs_git
async def test_init_creates_git_dir_and_commit(tmp_path: Path) -> None:
    project_path = tmp_path / 'demo'
    project_path.mkdir()
    (project_path / 'project.yaml').write_text('schema_version: 1\n')
    repo = SubprocessGitRepository()

    await repo.init_with_initial_commit(
        project_path, 'efactory: create project demo'
    )

    assert (project_path / '.git').is_dir()
    log = subprocess.run(
        ['git', '-C', str(project_path), 'log', '--oneline'],
        capture_output=True, text=True, check=True,
    )
    assert 'efactory: create project demo' in log.stdout
    files = subprocess.run(
        ['git', '-C', str(project_path), 'ls-files'],
        capture_output=True, text=True, check=True,
    )
    assert 'project.yaml' in files.stdout


@needs_git
async def test_init_works_without_user_git_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C2: initial commit не требует глобально настроенного user.* (env override)."""
    project_path = tmp_path / 'no-identity'
    project_path.mkdir()
    (project_path / 'file.txt').write_text('content')

    # Подменяем HOME, чтобы git не нашёл ~/.gitconfig пользователя.
    fake_home = tmp_path / 'home'
    fake_home.mkdir()
    monkeypatch.setenv('HOME', str(fake_home))
    monkeypatch.delenv('GIT_AUTHOR_NAME', raising=False)
    monkeypatch.delenv('GIT_AUTHOR_EMAIL', raising=False)
    monkeypatch.delenv('GIT_COMMITTER_NAME', raising=False)
    monkeypatch.delenv('GIT_COMMITTER_EMAIL', raising=False)

    repo = SubprocessGitRepository()
    await repo.init_with_initial_commit(
        project_path, 'no-identity init'
    )

    log = subprocess.run(
        ['git', '-C', str(project_path), 'log', '--format=%an <%ae>'],
        capture_output=True, text=True, check=True,
    )
    assert 'efactory' in log.stdout
    assert 'efactory@localhost' in log.stdout


@needs_git
async def test_init_commit_is_not_gpg_signed(tmp_path: Path) -> None:
    """C6: --no-gpg-sign — initial commit independent of user GPG setup."""
    project_path = tmp_path / 'no-sign'
    project_path.mkdir()
    (project_path / 'file.txt').write_text('x')
    repo = SubprocessGitRepository()

    await repo.init_with_initial_commit(project_path, 'unsigned')

    show = subprocess.run(
        ['git', '-C', str(project_path), 'log', '--show-signature'],
        capture_output=True, text=True, check=True,
    )
    assert 'gpg:' not in show.stdout
    assert 'gpgsm:' not in show.stdout


async def test_init_raises_git_unavailable_when_git_not_on_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, 'which', lambda _: None)
    project_path = tmp_path / 'no-git'
    project_path.mkdir()
    repo = SubprocessGitRepository()

    with pytest.raises(GitUnavailableError):
        await repo.init_with_initial_commit(project_path, 'fail')


@needs_git
async def test_init_raises_git_operation_error_on_subprocess_failure(
    tmp_path: Path,
) -> None:
    """Несуществующий путь → git init упадёт → GitOperationError."""
    repo = SubprocessGitRepository()

    with pytest.raises(GitOperationError):
        await repo.init_with_initial_commit(
            tmp_path / 'does-not-exist', 'fail'
        )
