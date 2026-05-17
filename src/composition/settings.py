"""Settings — pydantic-settings конфигурация efactory."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Конфигурация приложения. Источник — env vars с префиксом EFACTORY_.

    Локальные секреты (API-ключи и т.п.) можно вынести в `.secrets`
    в корне проекта (загружается автоматически, в репо не попадает).
    """

    model_config = SettingsConfigDict(
        env_prefix='EFACTORY_',
        env_file='.secrets',
        env_file_encoding='utf-8',
        extra='ignore',
    )

    projects_root: Path
    database_url: str
