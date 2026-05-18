"""
SubprocessGitRepository — `git init` + initial commit через subprocess (T010).

Минимальная реализация без GitPython-dep'а: три вызова `git`
(`init --quiet`, `add -A`, `commit -m <msg> --quiet --no-gpg-sign`).

C2: `GIT_AUTHOR_NAME=efactory` / `GIT_AUTHOR_EMAIL=efactory@localhost`
(+ committer) — initial commit не требует глобально настроенного
`user.name` / `user.email`. Пользовательские коммиты после initial —
от его `git config`.

C6: `--no-gpg-sign` — initial commit independent от `commit.gpgsign`
в user config. Если пользователь хочет подписывать всё — initial
unsigned, дальше его коммиты как обычно.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from typing import TYPE_CHECKING, Final

from ports.outbound.git_repository import (
    GitOperationError,
    GitUnavailableError,
)

if TYPE_CHECKING:
    from pathlib import Path


_AUTHOR_ENV: Final[dict[str, str]] = {
    'GIT_AUTHOR_NAME': 'efactory',
    'GIT_AUTHOR_EMAIL': 'efactory@localhost',
    'GIT_COMMITTER_NAME': 'efactory',
    'GIT_COMMITTER_EMAIL': 'efactory@localhost',
}


def _build_env() -> dict[str, str]:
    """
    Наследуем env (для PATH/LANG/HOME), но чистим GIT_DIR/WORK_TREE и
    подменяем AUTHOR/COMMITTER (C2: independent от user.name/email).
    """
    env = os.environ.copy()
    env.pop('GIT_DIR', None)
    env.pop('GIT_WORK_TREE', None)
    env.update(_AUTHOR_ENV)
    return env


def _run(git_path: str, args: list[str], cwd: Path) -> None:
    try:
        subprocess.run(
            [git_path, *args],
            cwd=cwd,
            env=_build_env(),
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        msg = (
            f'git {" ".join(args)} failed (exit {exc.returncode}) '
            f'at {cwd}: {exc.stderr.strip() or exc.stdout.strip()}'
        )
        raise GitOperationError(msg) from exc
    except FileNotFoundError as exc:
        # cwd не существует или git исполняемый исчез.
        msg = f'git {" ".join(args)} failed at {cwd}: {exc}'
        raise GitOperationError(msg) from exc


class SubprocessGitRepository:
    async def init_with_initial_commit(
        self,
        project_path: Path,
        message: str,
    ) -> None:
        git_path = shutil.which('git')
        if git_path is None:
            msg = 'git not found on PATH'
            raise GitUnavailableError(msg)

        def _do_init() -> None:
            _run(git_path, ['init', '--quiet'], project_path)
            _run(git_path, ['add', '-A'], project_path)
            _run(
                git_path,
                ['commit', '-m', message, '--quiet', '--no-gpg-sign'],
                project_path,
            )

        await asyncio.to_thread(_do_init)


__all__ = ['SubprocessGitRepository']
