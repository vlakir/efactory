"""Settings — pydantic-settings конфигурация efactory."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_APP_DIR_NAME = 'efactory'


def _default_data_dir() -> Path:
    """
    Базовый каталог данных приложения (XDG-стиль).

    `$XDG_DATA_HOME/efactory`, либо `$HOME/.local/share/efactory` если
    переменная не задана. Создаётся при первом запуске composition root.
    """
    xdg = os.environ.get('XDG_DATA_HOME')
    base = Path(xdg) if xdg else Path.home() / '.local' / 'share'
    return base / _APP_DIR_NAME


def _default_projects_root() -> Path:
    return _default_data_dir() / 'projects'


def _default_database_url() -> str:
    return f'sqlite+aiosqlite:///{_default_data_dir() / "efactory.db"}'


def _default_session_root() -> Path:
    return _default_data_dir() / 'sessions'


def _default_library_root() -> Path:
    """
    `<repo>/data/models/` — корень built-in SPICE-моделей (T006 + T007).

    Структура: `<root>/<category>/<source>/*.{lib,inc,cir}`. Категории:
    tubes / transformers / loads. Resolution path: settings.py →
    composition/ → src/ → <repo>. На production install переопределяется
    через `EFACTORY_LIBRARY_ROOT` env.
    """
    return Path(__file__).resolve().parents[2] / 'data' / 'models'


def _default_user_library_root() -> Path:
    """
    `<storage_root>/models/` для user-added SPICE-моделей (T006 fix-up Q3).

    User-id с тем же именем, что built-in, перезаписывает built-in
    (overlay). Структура та же: `<root>/<category>/<source>/...`.
    Каталог не создаётся автоматически — если отсутствует, adapter
    работает только с built-in.
    """
    return _default_data_dir() / 'models'


class Settings(BaseSettings):
    """
    Конфигурация приложения.

    Источники (по приоритету сверху вниз):
    1. Аргументы конструктора.
    2. Env-переменные с префиксом `EFACTORY_`.
    3. Файл `.secrets` в текущей директории (автозагрузка, в репо не
       попадает — см. `.gitignore`).
    4. Default'ы XDG-стиля (см. `_default_data_dir`).
    """

    model_config = SettingsConfigDict(
        env_prefix='EFACTORY_',
        env_file='.secrets',
        env_file_encoding='utf-8',
        extra='ignore',
    )

    projects_root: Path = Field(default_factory=_default_projects_root)
    database_url: str = Field(default_factory=_default_database_url)
    session_root: Path = Field(default_factory=_default_session_root)
    library_root: Path = Field(default_factory=_default_library_root)
    user_library_root: Path = Field(default_factory=_default_user_library_root)
