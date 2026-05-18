"""Unit-тесты Settings: default'ы и приоритет env над ними.

Walking Skeleton CLI должен работать из чистого окружения без
обязательного `.secrets` и env (T087). Раньше `Settings()` падал
с ValidationError, если EFACTORY_PROJECTS_ROOT / EFACTORY_DATABASE_URL
не заданы.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from composition.settings import Settings

if TYPE_CHECKING:
    from pathlib import Path

_EFACTORY_ENV_VARS = (
    'EFACTORY_PROJECTS_ROOT',
    'EFACTORY_DATABASE_URL',
    'EFACTORY_SESSION_ROOT',
)


@pytest.fixture(autouse=True)
def _isolate_settings_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: 'Path',
) -> None:
    """Очистить EFACTORY_* и XDG_DATA_HOME, изолировать $HOME и cwd.

    Так Settings() в тестах ведёт себя предсказуемо: единственный
    источник дефолтов — изолированный $HOME / $XDG_DATA_HOME в tmp_path.
    `.secrets` в репо/cwd не подхватывается, потому что cwd → tmp_path.
    """
    for var in (*_EFACTORY_ENV_VARS, 'XDG_DATA_HOME'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.chdir(tmp_path)


def test_defaults_use_home_local_share_when_no_xdg(tmp_path: 'Path') -> None:
    settings = Settings()

    expected_root = tmp_path / '.local' / 'share' / 'efactory'
    assert settings.projects_root == expected_root / 'projects'
    assert (
        settings.database_url
        == f'sqlite+aiosqlite:///{expected_root / "efactory.db"}'
    )
    assert settings.session_root == expected_root / 'sessions'


def test_env_overrides_session_root(
    tmp_path: 'Path',
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    custom_sessions = tmp_path / 'custom_sessions'
    monkeypatch.setenv('EFACTORY_SESSION_ROOT', str(custom_sessions))

    settings = Settings()

    assert settings.session_root == custom_sessions


def test_defaults_use_xdg_data_home_when_set(
    tmp_path: 'Path',
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    xdg = tmp_path / 'xdg'
    monkeypatch.setenv('XDG_DATA_HOME', str(xdg))

    settings = Settings()

    expected_root = xdg / 'efactory'
    assert settings.projects_root == expected_root / 'projects'
    assert (
        settings.database_url
        == f'sqlite+aiosqlite:///{expected_root / "efactory.db"}'
    )


def test_env_overrides_defaults(
    tmp_path: 'Path',
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    custom_root = tmp_path / 'custom_projects'
    custom_db = f'sqlite+aiosqlite:///{tmp_path / "custom.db"}'
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(custom_root))
    monkeypatch.setenv('EFACTORY_DATABASE_URL', custom_db)

    settings = Settings()

    assert settings.projects_root == custom_root
    assert settings.database_url == custom_db
