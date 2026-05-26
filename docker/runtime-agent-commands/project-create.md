---
description: Создать новый efactory-проект из шаблона se-amp.
argument-hint: <PROJECT_NAME>
allowed-tools: Bash
---

Пользователь хочет создать новый efactory-проект `$ARGUMENTS` из шаблона
`se-amp` (single-ended 6П14П amp с OPT 5kΩ:8Ω).

1. Если `$ARGUMENTS` пуст — напечатай `Usage: /project-create <NAME>` и
   остановись.
2. Запусти: `efactory project create --name $ARGUMENTS --template se-amp`.
3. Покажи stdout/stderr пользователю.
4. Если команда успешна — короткое follow-up: «Проект создан в
   `/workspace/$ARGUMENTS/`. Используй `/project-use $ARGUMENTS` для
   просмотра контекста или просто работай с `/workspace/$ARGUMENTS/*`
   через абсолютные пути.»
5. Если упало (non-zero rc) — покажи сообщение об ошибке и не предлагай
   workaround'ов, пока пользователь не уточнит.
