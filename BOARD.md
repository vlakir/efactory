# Board

Лёгкая Kanban-альтернатива на одном markdown-файле: три колонки
(To Do / Doing / Done) под git, без внешних сервисов и инструментов.

## Соотношение с другими файлами

- `BACKLOG.md` — длинная очередь идей и побочных находок. Сюда падает
  «потом подумаем», «не сейчас». Парковка scope.
- `BOARD.md` (этот файл) — активный рабочий поток. Задачи, которые мы
  уже взяли или собираемся брать в ближайшее время.
- `specs/T<NNN>-*/spec.md` — куда вырастает крупная задача из BOARD, если
  она оказывается фичей >1 дня работы.

Жизненный цикл задачи: идея в `BACKLOG.md` → созрела → переезжает в
`To Do` здесь → берётся в работу (`Doing`) → закрывается (`Done`) →
после релиза переходит в `CHANGELOG.md` (запись обязательно содержит
T-ID), отсюда удаляется. **`CHANGELOG.md` — единственное persistent-
хранилище T-ID завершённых задач**, без него правило «ID не
переиспользуется» сломается.

## Формат задачи

Каждая задача — `- **T<NNN>** — <короткое описание>`. ID присваивается
при создании: новый = `max(существующих T-ID в BOARD.md, BACKLOG.md и
CHANGELOG.md) + 1`. ID никогда не переиспользуется. ID общий для
`BOARD.md` и `BACKLOG.md` — при перетекании задачи между ними
сохраняется; после релиза задача попадает в `CHANGELOG.md` с тем же
T-ID, что гарантирует уникальность номеров между релизами.

Имя ветки: `T<NNN>-<slug>` (без namespace типа `fixes/` / `feature/` —
ID уже даёт идентификацию). Имя PR: `T<NNN>: <title>`. Спецификация
крупной фичи: `specs/T<NNN>-<slug>/spec.md`.

По вкусу можно добавлять:

- метку даты взятия,
- ссылку на спеку,
- имя ветки.

Пример:

```
- **T<NNN>** — Превью постов в Telegram
  (`specs/T<NNN>-telegram-preview/`, ветка `T<NNN>-telegram-preview`).
```

---

## To Do

<!-- Готово к взятию. Очередь FIFO по умолчанию, можно поднимать
     приоритетное наверх. -->

<!-- Записи задач в формате `- **T<NNN>** — описание`. См. раздел
     «Формат задачи» выше. -->

## Doing

<!-- В работе прямо сейчас. Держим короткой: максимум 1-2 задачи на
     разработчика, иначе теряется фокус (классическое WIP-limit
     правило из Kanban). -->

- **T111** — [2026-05-19, ветка `T111-kicad-gui-passthrough`] Phase
  0.9 Containerization, Phase 1 — KiCad GUI passthrough из контейнера
  на хост через X11 (Wayland fallback). Расширение final stage:
  apt-runtime `x11-apps`, `x11-utils`, `libgl1`, `dbus-x11`, `xauth`,
  `mesa-utils` (KiCad GUI пакетные зависимости уже стянуты Phase 0).
  Один образ `efactory:linux` (без `-headless` split — разделение в
  T120/T121). Wrapper-скрипты для ритуала ручной проверки:
  `scripts/run-kicad.sh` (запуск GUI из контейнера с `xhost
  +SI:localuser:#$(id -u)` и опциональным `--demo` mount'ом),
  `scripts/gen-se-amp-demo.py` (материализует SE-amp 6П14П
  acceptance-фикстуру в `$HOME/efactory-projects/se-amp-demo/` с
  относительными `Sim.Library`-путями и минимальным `.kicad_pro` для
  Simulator). Smoke-script `scripts/smoke-gui.sh`: X11 connectivity
  (`xdpyinfo`) + `kicad-cli version` + `xeyes` end-to-end. Spec —
  `specs/T110-containerization/spec.md` Phase 1.
  Acceptance: smoke зелёный + 50× open/save/close SE-amp у
  Vladimir'а без падений, шрифты и clipboard работают, Simulator
  прогоняет `.tran` с AC-амплификацией 5–7× на /plate.

## Done

<!-- Закрытые задачи, ждущие переноса в CHANGELOG.md при следующем
     релизе или значимой точке. После переноса — очищаем. -->

- **T110 Phase 0** — [closed 2026-05-19, PR #52] Phase 0.9
  Containerization, Phase 0 — базовый Dockerfile `efactory:linux-
  headless`. Multi-stage build: Ubuntu 24.04 LTS base + KiCad 10 (PPA
  `kicad/kicad-10.0-releases`) + ngspice → python-deps (uv + venv 3.14
  в `/opt/efactory/.venv`) → efactory-code (editable install) → final.
  Size: 2.43 GB (≤ 6 GB потолок). `docker run pytest` — 587 passed,
  8 skipped, coverage 87.29% (host: 593/2 — разница на AppImage-
  skipif'ах, очистка в T120). Закрыты C1 (venv permissions) и C3
  (user-agnostic mount paths: `/efactory/.claude/`, `/workspace`,
  `/libs`, `HOME=/opt/efactory`). Pre-push hook (ruff/format/mypy/
  lint-imports/pytest) — все зелёные. Spec —
  `specs/T110-containerization/spec.md` Phase 0. Следующие фазы (T111
  GUI passthrough, T112 FreeCAD, T113 FEM, T114 wrapper, T115 CI,
  T120 cleanup, T121 externalize libs) — отдельные PR.
- **T107 Phase 0** — [closed 2026-05-19, PR #46] Custom Soviet tube
  snippets: `Tubes_Soviet:GU50/6P45S/6N6P` через copy-rename базовых
  EL84/ECC81 форм. 3 demo фикстуры (`test_soviet_tubes_facade.py`)
  — common-cathode amp для каждой лампы, ngspice gain 20×/14×/227×.
  Phase 1 deferred — datasheet-accurate vector drawing (top-cap GU50,
  beam tetrode 6П45С, octal 6Н6П) с возможной LLM-vision delegation.
  Bug-fix mini-discovery: KiCad требует sub-unit names = parent name
  (initial "N6P_X_Y" не работал, fixed "6N6P_X_Y").
  593 passed (+3), coverage 87.99%.

<!-- Записи T103, T101, T105 Phase 0, T004b, T005 Phase 0, T104
     перенесены в CHANGELOG.md → [0.5.0] release-PR (2026-05-19). -->

<!-- Записи T010, T009, T006, T007, T004, T008, T100, T102 перенесены
     в CHANGELOG.md → [0.4.0] release-PR. -->

<!-- Записи T093, T095, T096, T097, T098, T099 перенесены в
     CHANGELOG.md → [0.3.0] release-PR. -->
