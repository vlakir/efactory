# `composition/` — composition root

Сборка графа зависимостей в одном месте. Без DI-контейнера —
ручная композиция (фабричные функции).

## Сюда

- `main.py` — entrypoint приложения (`efactory ...`); собирает
  CLI-адаптер с use cases и outbound-адаптерами.
- `settings.py` — `pydantic-settings` класс `Settings`: пути к
  SQLite/Kùzu/projects-root, API-ключи через env vars
  (`SettingsConfigDict(env_file='.secrets')` для local-only).
- Фабричные функции, собирающие use case + его outbound-зависимости.
- Минимальный `logging.basicConfig(level=INFO)` — структурное
  логирование появится в T010.

## НЕ сюда

- Бизнес-логика (она в `domain/` и `application/`).
- Реализации портов (они в `adapters/`).

## Зависимости

Composition root — **верхний слой**. Импортирует **все остальные**
(`domain/`, `application/`, `ports/`, `adapters/`). Это допустимо
и явно описано как исключение в `[tool.importlinter]` контракте.

Никто (кроме `__main__`) не импортирует `composition/`.

## DI

Ручная композиция: фабрики вида

```python
def build_cli() -> CLI:
    settings = Settings()
    engine = create_async_engine(settings.sqlite_url)
    metadata_repo = SqlMetadataRepository(engine)
    create_project = CreateProject(metadata_repo, file_store)
    return TyperCLI(create_project, ...)
```

Переход на DI-контейнер (`dependency-injector`, `punq`) — отдельной
задачей, если граф зависимостей станет неуправляемым.
