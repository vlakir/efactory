---
description: Поиск по Knowledge Base (token-AND по topic/description/tags/body).
argument-hint: <query tokens>
allowed-tools: Bash
---

Пользователь хочет найти KB entries через `efactory kb search`.

Args от пользователя: `$ARGUMENTS` — query (один или несколько tokens
через пробел). Token-AND match: все tokens должны встретиться в
entry's topic / description / tags / body (case-insensitive substring).

1. Если `$ARGUMENTS` пуст — напечатай `Usage: /kb-search <query>` и
   остановись.

2. Запусти: `efactory kb search $ARGUMENTS`.

3. Покажи stdout (список matches: `topic [source] description`).

4. Если найдены matches и пользователь хочет глубже — предложи
   `/kb-show <topic>` для полного body, либо `Read /efactory/
   knowledge-base/{built-in,host-mutated}/<topic>.md` напрямую.

5. Если nothing matched — подсказать переформулировать query (token-
   AND строгий, fuzzy не делается).
