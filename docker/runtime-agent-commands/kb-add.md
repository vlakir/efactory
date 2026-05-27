---
description: Добавить entry в host-mutated KB (agent learns in production).
argument-hint: <topic> --description "..." --body "..." [--tags csv]
allowed-tools: Bash
---

Пользователь (или ты сам, если нашёл новый pitfall в работе) хочет
добавить entry в Knowledge Base.

Args: `$ARGUMENTS` должен содержать:
- Позиционный `<topic>` — namespaced slug (например
  `spice.new-pitfall`, `agent.workflow-trick`).
- `--description "..."` — one-liner для TOC (≤200 chars).
- Body — одним из трёх способов (priority `--body` > `--body-file` >
  stdin):
  - `--body "markdown text"` — **рекомендованный** для коротких
    entries и для тебя как агента (одна Bash-команда без heredoc /
    stdin gymnastics).
  - `--body-file <path>` — для длинных, заранее подготовленных в файле.
  - stdin — fallback если ни `--body`, ни `--body-file` не переданы.
- Опционально `--tags spice,magnetics` (CSV).

Алгоритм:

1. Если `$ARGUMENTS` пуст или отсутствуют `<topic>` / `--description`
   — напечатай Usage и остановись.

2. Подготовь body (markdown) с:
   - Правилом (что именно делать / не делать).
   - Источником/обоснованием (DECISIONS.md ADR, spec, инцидент).
   - Anti-pattern (что часто делается неверно).
   - Anchor (если есть): `См. DECISIONS.md 2026-XX-XX «...»` или
     `См. specs/TNNN-*/spec.md §X`.

3. Запусти (compact form, рекомендованная):
   ```bash
   efactory kb add <topic> --description "..." --body "<markdown>" --tags <csv>
   ```
   Или для длинного multi-line body:
   ```bash
   efactory kb add <topic> --description "..." --tags <csv> --body-file <path>
   ```

4. Если успех — entry в `/efactory/knowledge-base/host-mutated/
   <topic>.md`; следующая сессия увидит через SessionStart hook TOC.

5. Если conflict (existing topic) — выбери другой slug, или (если
   умышленный overwrite) добавь `--force`.

6. Built-in seed (`/efactory/knowledge-base/built-in/`) — read-only
   runtime. Promotion host-mutated → built-in делается отдельно
   через PR в репо `docker/runtime-agent-knowledge-base/` (Vladimir
   + Гвидо curation).

Naming convention: lowercase-kebab, namespaced. Существующие
namespaces: `spice.*`, `magnetics.*`, `fem.*`, `agent.*`,
`project.*`. Новый namespace ок — придерживайся осмысленного
семантического деления.
