# `adapters/` — реализации портов

Технологические реализации `ports/`. Изолированы по технологии в
подпапках.

## Структура

- `inbound/cli/` — Typer-CLI: парсинг команд, вызов use cases.
- `inbound/mcp_server/` — наш MCP-сервер (обёртка use cases как
  MCP-tools) — каркас в T085, реализация в T013.
- `outbound/persistence_sql/` — SQLAlchemy 2.0 async + aiosqlite,
  declarative models, явный маппинг `domain ↔ persistence`,
  Alembic-миграции.
- `outbound/graph_store/` — Kùzu (sync API, обёрнут в
  `asyncio.to_thread`).
- `outbound/file_store/` — filesystem.
- `outbound/ai_anthropic/` — Claude через `anthropic` SDK (фаза
  дорожной карты, не T085).
- `outbound/mcp_client/` — клиент внешних MCP через `mcp` Python
  SDK (фаза дорожной карты, не T085).

## Правила

- Каждый адаптер реализует один или несколько `Protocol`-портов
  и **импортируется только из `composition/`**, нигде больше.
- **Адаптеры не импортируют друг друга.** Если возникает потребность
  — общая логика поднимается в `domain/` или `application/`.
- Persistence-модели (SQLAlchemy declarative) **не утекают** в
  `domain/`. Между ними — явные функции маппинга в том же адаптере.
- Все методы — `async`. Sync-API внешних библиотек (Kùzu, FEMM)
  заворачиваются в `asyncio.to_thread` внутри адаптера.
- DTO (входящие/исходящие сериализованные представления) — отдельные
  классы от domain-моделей, маппинг явный.

## Зависимости

- `domain/`, `ports/` — что реализуем и какими типами оперируем.
- Внешние библиотеки своей технологии.
- stdlib.

Никаких импортов `application/`, `composition/` или соседних
адаптеров.

## TDD

Адаптеры — **integration**-тесты с реальными зависимостями
(`tmp_path`-SQLite, `tmp_path`-Kùzu, реальная FS). Без `unittest.mock`
для портов: fake-порты для тестов use cases живут в `tests/unit/application/`,
а здесь — настоящая технология.
