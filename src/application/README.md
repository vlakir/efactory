# `application/` — use cases

Тонкие use cases: оркестрация портов под конкретный сценарий
использования.

## Сюда

- Классы / функции вида `CreateProject`, `RunSpiceSimulation`,
  `ImportComponentLibrary` — по одному use case на сценарий.
- Координация вызовов outbound-портов (репозиториев, AI, file store,
  MCP-клиента) в нужном порядке.
- Транзакционные границы (где они проходят на уровне сценария).

## НЕ сюда

- Бизнес-инварианты — они в `domain/`.
- Импорты `adapters/` (только `ports/` и `domain/`).
- Детали технологий (SQL, HTTP, файловые форматы) — за портами.

## Зависимости

- `domain/` — модели и сервисы предметной области.
- `ports/` — Protocol-интерфейсы того, что use case требует от мира.
- stdlib.

Никаких `sqlalchemy`, `kuzu`, `anthropic`, `mcp` импортов в этом слое.

## Async

Все методы use cases — `async`. Вызов sync-API внешних библиотек —
ответственность адаптера (`asyncio.to_thread`).

## TDD

Use cases пишутся outside-in: сначала acceptance/e2e тест на
сценарий, потом unit-тест use case с **fake-портами** (in-memory
реализации `Protocol`), потом конкретные адаптеры.
**Никаких `unittest.mock`** для портов.

См. спеку `T085` §5 (Test structure) и ADR блок «TDD-first» в
`DECISIONS.md`.
