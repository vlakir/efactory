#!/usr/bin/env python3
"""
Полный прогон гейтов на srv: push ветки в песочницу Forgejo и ожидание `gates`.

Правило методики (решение Разработчика 2026-10-11): перед push локально идут только
лёгкие проверки (`scripts/gates.sh --light`), а pytest с покрытием и прочее тяжёлое —
на srv, в workflow `gates` Forgejo. Слияние в `main` — только после зелёного прогона
для итогового коммита ветки; `gitflic_merge.py` проверяет это через `--check`.

Песочница — репозиторий `<организация>/<проект>-dev` (remote `srv-dev`): в неё
можно пушить сразу, не дожидаясь GitFlic и часовой синхронизации зеркала. Ветка в
песочнице перезаписывается (`--force`): это рабочая копия, а не история.

Использование::

    uv run python scripts/srv_gates.py              # push HEAD, ждать итог
    uv run python scripts/srv_gates.py --no-wait    # только push
    uv run python scripts/srv_gates.py --check      # есть ли зелёный прогон HEAD
    uv run python scripts/srv_gates.py --check --remote origin --branch T123-x

Код выхода: 0 — зелёный прогон есть, 1 — красный или прогона нет, 2 — ошибка
(нет VPN, токена, таймаут).

Настройка — переменными окружения (умолчания в константах ниже):
``SRV_FORGEJO_URL``, ``SRV_FORGEJO_ORG``, ``SRV_FORGEJO_CA``,
``SRV_FORGEJO_TOKEN_FILE`` (строка ``FORGEJO_TOKEN=`` — токен пользователя с
правом ``write:repository``), ``SRV_FORGEJO_REPO`` (имя проекта, если его не
вывести из remote GitFlic или GitHub).

Скрипт одинаков во всех проектах экосистемы; правка — во всех копиях сразу
(образец — `templates/python-project` репозитория CI srv).
"""

from __future__ import annotations

import argparse
import http
import http.client
import json
import os
import pathlib
import re
import shutil
import ssl
import subprocess
import sys
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any

#: Forgejo на srv (WireGuard).
URL = os.environ.get('SRV_FORGEJO_URL', 'https://10.66.66.10:3443')
#: Организация с зеркалами и песочницами. Переименование — правкой этой строки
#: (или переменной окружения), а не поиском по скриптам.
ORG = os.environ.get('SRV_FORGEJO_ORG', 'dev')
#: Корневой сертификат локального УЦ srv.
CA = pathlib.Path(os.environ.get('SRV_FORGEJO_CA', '~/srv-forgejo-ca.crt')).expanduser()
#: Файл с токеном (не в репозитории).
TOKEN_FILE = pathlib.Path(
    os.environ.get('SRV_FORGEJO_TOKEN_FILE', '~/.config/srv-forgejo/push.env')
).expanduser()
ENV_PREFIX = 'FORGEJO_TOKEN='
#: Имя workflow гейтов в `.forgejo/workflows/`.
WORKFLOW = 'gates.yml'
#: Суффикс песочницы и имя её remote.
SANDBOX_SUFFIX = '-dev'
SANDBOX_REMOTE = 'srv-dev'
#: Состояния прогона Forgejo: зелёное и окончательно красные; прочие — «ещё идёт».
GREEN = 'success'
RED = frozenset({'failure', 'cancelled', 'skipped'})
#: Сколько ждать появления прогона после push и опрашивать его ход.
APPEAR_S = 300.0
POLL_S = 15.0
#: Проект по remote GitFlic (`.../project/vlakir/<имя>(.git)`) или GitHub
#: (`https://github.com/vlakir/<имя>(.git)`, `git@github.com:vlakir/<имя>.git`).
REMOTE_RES = (
    re.compile(r'gitflic\.ru/project/[^/]+/([^/]+?)(?:\.git)?/?$'),
    re.compile(r'github\.com[:/][^/]+/([^/]+?)(?:\.git)?/?$'),
)


class SrvGatesError(RuntimeError):
    """srv недоступен, нет токена или ответ Forgejo не разобрать."""


@dataclass(frozen=True)
class Run:
    """Прогон workflow `gates` на коммите."""

    repo: str
    number: int
    status: str
    url: str

    @property
    def green(self) -> bool:
        return self.status == GREEN

    @property
    def finished(self) -> bool:
        return self.status == GREEN or self.status in RED


def _say(text: str) -> None:
    sys.stdout.write(text + '\n')
    sys.stdout.flush()


def _git(*args: str, env: dict[str, str] | None = None) -> str:
    """Выполнить git и вернуть stdout; ненулевой код — `SrvGatesError`."""
    git = shutil.which('git') or 'git'
    done = subprocess.run(  # noqa: S603 — аргументы собирает скрипт, не ввод
        [git, *args], capture_output=True, text=True, check=False, env=env
    )
    if done.returncode != 0:
        command = ' '.join(args[:2])
        msg = f'git {command} вернул {done.returncode}: {done.stderr.strip()}'
        raise SrvGatesError(msg)
    return done.stdout.strip()


def token() -> str:
    """Токен Forgejo из файла (в репозиторий он не попадает)."""
    if not TOKEN_FILE.is_file():
        msg = (
            f'Нет файла с токеном Forgejo: {TOKEN_FILE} (строка {ENV_PREFIX}…, '
            'токен пользователя с правом write:repository).'
        )
        raise SrvGatesError(msg)
    for line in TOKEN_FILE.read_text(encoding='utf-8').splitlines():
        if line.startswith(ENV_PREFIX):
            return line.removeprefix(ENV_PREFIX).strip()
    msg = f'В {TOKEN_FILE} нет строки {ENV_PREFIX}'
    raise SrvGatesError(msg)


def project_name() -> str:
    """Имя проекта: из `SRV_FORGEJO_REPO` или из адреса remote GitFlic/GitHub."""
    if name := os.environ.get('SRV_FORGEJO_REPO'):
        return name
    for line in _git('remote', '-v').splitlines():
        for url in line.split()[1:2]:
            for pattern in REMOTE_RES:
                if match := pattern.search(url):
                    return match.group(1)
    msg = 'Не вывел имя проекта из remote GitFlic/GitHub — задайте SRV_FORGEJO_REPO.'
    raise SrvGatesError(msg)


def api(path: str, query: dict[str, str] | None = None) -> dict[str, Any]:
    """GET к API Forgejo; разобранный JSON."""
    parsed = urllib.parse.urlsplit(URL)
    if parsed.scheme != 'https' or not parsed.hostname:
        msg = f'SRV_FORGEJO_URL должен быть https-адресом, а не {URL!r}.'
        raise SrvGatesError(msg)
    if not CA.is_file():
        msg = f'Нет сертификата УЦ srv: {CA} (SRV_FORGEJO_CA).'
        raise SrvGatesError(msg)
    target = f'/api/v1/{path}'
    if query:
        target += '?' + urllib.parse.urlencode(query)
    context = ssl.create_default_context(cafile=str(CA))
    connection = http.client.HTTPSConnection(
        parsed.hostname, parsed.port, timeout=30, context=context
    )
    try:
        connection.request('GET', target, headers={'Authorization': f'token {token()}'})
        response = connection.getresponse()
        body = response.read()
    except OSError as exc:
        msg = f'Forgejo {URL} недоступен ({exc}). Нужен VPN к srv (WireGuard).'
        raise SrvGatesError(msg) from exc
    finally:
        connection.close()
    if response.status != http.HTTPStatus.OK:
        detail = body.decode('utf-8', 'replace')[:300]
        msg = f'Forgejo ответил {response.status} на {target}: {detail}'
        raise SrvGatesError(msg)
    parsed_body: dict[str, Any] = json.loads(body)
    return parsed_body


def runs(repo: str, sha: str) -> list[Run]:
    """Прогоны `gates` на коммите в репозитории `ORG/repo`, новые первыми."""
    data = api(
        f'repos/{ORG}/{repo}/actions/runs',
        {'head_sha': sha, 'workflow_id': WORKFLOW, 'limit': '50'},
    )
    found = [
        Run(repo, int(item['index_in_repo']), str(item['status']), item['html_url'])
        for item in data.get('workflow_runs') or []
        if item.get('commit_sha') == sha and item.get('workflow_id') == WORKFLOW
    ]
    return sorted(found, key=lambda run: run.number, reverse=True)


def green_run(project: str, sha: str) -> Run | None:
    """Зелёный прогон коммита в песочнице или в зеркале; `None` — его нет."""
    for repo in (project + SANDBOX_SUFFIX, project):
        try:
            found = runs(repo, sha)
        except SrvGatesError as exc:
            if ' 404 ' not in str(exc):
                raise
            continue
        for run in found:
            if run.green:
                return run
    return None


def push(project: str, branch: str, sha: str) -> None:
    """Отправить коммит веткой в песочницу; remote `srv-dev` — на её адрес."""
    url = f'{URL.rstrip("/")}/{ORG}/{project}{SANDBOX_SUFFIX}.git'
    remotes = _git('remote').split()
    if SANDBOX_REMOTE in remotes:
        _git('remote', 'set-url', SANDBOX_REMOTE, url)
    else:
        _git('remote', 'add', SANDBOX_REMOTE, url)
    # Токен — заголовком через переменные окружения git, а не в адресе или argv:
    # так он не оседает ни в `.git/config`, ни в списке процессов.
    env = {
        **os.environ,
        'GIT_CONFIG_COUNT': '2',
        'GIT_CONFIG_KEY_0': 'http.extraHeader',
        'GIT_CONFIG_VALUE_0': f'Authorization: token {token()}',
        'GIT_CONFIG_KEY_1': 'http.sslCAInfo',
        'GIT_CONFIG_VALUE_1': str(CA),
    }
    _say(f'push {sha[:12]} → {ORG}/{project}{SANDBOX_SUFFIX}, ветка {branch}')
    refspec = f'{sha}:refs/heads/{branch}'
    _git('push', '--force', '--no-verify', SANDBOX_REMOTE, refspec, env=env)


def wait(project: str, sha: str, timeout_s: float) -> Run:
    """Дождаться окончания последнего прогона `gates` коммита в песочнице."""
    repo = project + SANDBOX_SUFFIX
    started = time.monotonic()
    last = ''
    while True:
        found = runs(repo, sha)
        elapsed = time.monotonic() - started
        if found:
            newest = found[0]
            if newest.finished:
                return newest
            if newest.status != last:
                minutes = elapsed / 60
                _say(f'[{minutes:4.1f} мин] прогон #{newest.number}: {newest.status}')
                _say(f'  {newest.url}')
                last = newest.status
        elif elapsed > APPEAR_S:
            msg = (
                f'За {APPEAR_S / 60:.0f} мин прогон {WORKFLOW} коммита {sha[:12]} в '
                f'{ORG}/{repo} не появился (Actions выключены? нет workflow?).'
            )
            raise SrvGatesError(msg)
        if elapsed > timeout_s:
            msg = f'Прогон не кончился за {timeout_s / 60:.0f} мин — см. в Forgejo.'
            raise SrvGatesError(msg)
        time.sleep(POLL_S)


def remote_sha(remote: str, branch: str) -> str:
    """Голова ветки на remote (ls-remote, без fetch)."""
    line = _git('ls-remote', remote, f'refs/heads/{branch}')
    if not line:
        msg = f'На {remote} нет ветки {branch}.'
        raise SrvGatesError(msg)
    return line.split()[0]


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Полный прогон гейтов на srv (Forgejo) и проверка его итога.'
    )
    parser.add_argument(
        '--check',
        nargs='?',
        const='HEAD',
        metavar='REV',
        help='не пушить: проверить, есть ли зелёный прогон коммита (умолч. HEAD)',
    )
    parser.add_argument(
        '--remote', help='с --check: взять голову --branch на этом remote'
    )
    parser.add_argument('--branch', help='имя ветки (умолч. текущая)')
    parser.add_argument('--no-wait', action='store_true', help='только push, не ждать')
    parser.add_argument(
        '--timeout', type=float, default=120.0, help='сколько ждать прогон, мин (120)'
    )
    return parser.parse_args(argv)


def _check(args: argparse.Namespace, project: str) -> int:
    if args.remote:
        if not args.branch:
            _say('--remote требует --branch.')
            return 2
        sha = remote_sha(args.remote, args.branch)
    else:
        sha = _git('rev-parse', f'{args.check}^{{commit}}')
    run = green_run(project, sha)
    if run is None:
        _say(
            f'✖ Для коммита {sha[:12]} нет зелёного прогона {WORKFLOW} на srv '
            f'({ORG}/{project}{SANDBOX_SUFFIX} и {ORG}/{project}). '
            'Запустите scripts/srv_gates.py на итоговом коммите ветки.'
        )
        return 1
    _say(f'✔ {sha[:12]}: зелёный прогон {WORKFLOW} — {run.url}')
    return 0


def _full(args: argparse.Namespace, project: str) -> int:
    sha = _git('rev-parse', 'HEAD^{commit}')
    branch = args.branch or _git('branch', '--show-current')
    if not branch:
        _say('HEAD отсоединён — укажите --branch.')
        return 2
    if _git('status', '--porcelain', '--untracked-files=no'):
        _say('⚠ В рабочей копии незакоммиченные правки — на srv уйдёт только коммит.')
    push(project, branch, sha)
    if args.no_wait:
        _say(f'Прогон: {URL.rstrip("/")}/{ORG}/{project}{SANDBOX_SUFFIX}/actions')
        return 0
    run = wait(project, sha, args.timeout * 60)
    mark = '✔' if run.green else '✖'
    _say(f'{mark} gates на srv для {sha[:12]}: {run.status}')
    _say(f'  {run.url}')
    return 0 if run.green else 1


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        project = project_name()
        return _check(args, project) if args.check else _full(args, project)
    except SrvGatesError as exc:
        _say(f'✖ {exc}')
        return 2


if __name__ == '__main__':
    sys.exit(main())
