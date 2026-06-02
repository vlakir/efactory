"""Integration: SubprocessGitRepository через реальный `git` CLI (T010)."""

from __future__ import annotations

import os
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

# T169: pop GIT_DIR / GIT_WORK_TREE / GIT_INDEX_FILE из env при
# verification subprocess вызовах. Под `git push` из worktree git
# инжектит GIT_DIR=<worktree-gitdir> в pre-push hook subprocess
# (pytest); без sanitization `git -C <tmp_path> log ...` читает
# parent repo вместо tmp_path init'a и assertion-ы фейлят. Соответствует
# поведению `_build_env()` в `SubprocessGitRepository` под test.
_GIT_ENV_LEAKAGE = frozenset({'GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE'})


def _git_capture(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in _GIT_ENV_LEAKAGE}
    return subprocess.run(
        ['git', '-C', str(cwd), *args],
        capture_output=True,
        text=True,
        check=True,
        env=env,
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
    log = _git_capture('log', '--oneline', cwd=project_path)
    assert 'efactory: create project demo' in log.stdout
    files = _git_capture('ls-files', cwd=project_path)
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

    log = _git_capture('log', '--format=%an <%ae>', cwd=project_path)
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

    show = _git_capture('log', '--show-signature', cwd=project_path)
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


@needs_git
async def test_init_works_when_caller_has_git_dir_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T169 regression: init + verification работают под inherited GIT_DIR.

    Симулируется ситуация worktree pre-push hook: git инжектит
    `GIT_DIR=<parent-worktree-gitdir>` в pytest subprocess. Без env-
    sanitization init субпроцессы пишут в parent gitdir / verification
    `git -C <tmp>` читает parent log; assertion-ы фейлят. Production
    `_build_env()` уже pop'ит, helper `_git_capture` тоже — тест ловит
    регрессию если кто-то добавит ещё один raw `subprocess.run(['git',
    ...])` без env arg в этот файл.
    """
    fake_gitdir = tmp_path / 'fake-parent-gitdir'
    fake_worktree = tmp_path / 'fake-parent-worktree'
    fake_gitdir.mkdir()
    fake_worktree.mkdir()
    monkeypatch.setenv('GIT_DIR', str(fake_gitdir))
    monkeypatch.setenv('GIT_WORK_TREE', str(fake_worktree))

    project_path = tmp_path / 'env-leak-demo'
    project_path.mkdir()
    (project_path / 'file.txt').write_text('marker')
    repo = SubprocessGitRepository()

    await repo.init_with_initial_commit(project_path, 'env-isolated init')

    assert (project_path / '.git').is_dir(), (
        'init wrote to parent GIT_DIR instead of project_path/.git'
    )
    log = _git_capture('log', '--oneline', cwd=project_path)
    assert 'env-isolated init' in log.stdout, (
        f'verification subprocess inherited GIT_DIR; log:\n{log.stdout}'
    )
