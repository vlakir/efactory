---
description: Показать project-context для указанного проекта (display-only, cwd не меняется).
argument-hint: <PROJECT_NAME>
allowed-tools: Bash
---

Пользователь хочет посмотреть свежий контекст проекта `$ARGUMENTS`
(имя, файлы, последние sim-результаты).

**Важно:** это **display-only** команда. Bash cwd между tool calls в
Claude Code нестабилен, поэтому НЕ делаем `cd` — иначе следующие
shell-команды могли бы тихо вернуться к старому cwd. Вместо этого
запускаем SessionStart hook с явным `CLAUDE_PROJECT_DIR=/workspace/
$ARGUMENTS` и парсим его JSON-ответ.

1. Если `$ARGUMENTS` пуст — напечатай `Usage: /project-use <NAME>` и
   остановись.
2. Pre-flight: проверь существование `/workspace/$ARGUMENTS/` через
   `test -d /workspace/$ARGUMENTS && echo OK || echo MISSING`. Если
   MISSING — выведи `ls /workspace/` и напомни пользователю про
   `/project-create $ARGUMENTS`.
3. Запусти:
   ```bash
   CLAUDE_PROJECT_DIR=/workspace/$ARGUMENTS \
       python3 /opt/efactory/scripts/session_start_hook.py < /dev/null \
       | python3 -c "import json, sys; print(json.load(sys.stdin)['hookSpecificOutput']['additionalContext'])"
   ```
   Покажи полученный context-блок пользователю как есть (это
   markdown).
4. После блока добавь explanatory note: «Контекст показан, но cwd
   сессии не изменён. Для последующих shell-команд используй абсолютные
   пути под `/workspace/$ARGUMENTS/`. Полный refresh системного prompt:
   `/clear` (если ты уже работал из этого cwd изначально) или выход +
   `./efactory-up --agent $ARGUMENTS` на хосте.»
