#!/usr/bin/env bash
# smoke-gui.sh — автоматический smoke-тест GUI passthrough из контейнера
# efactory:linux (T111, Phase 0.9 / Phase 1).
#
# Проверяет:
#   1. Образ efactory:linux существует локально (или собирается).
#   2. Внутри контейнера видна X11-сессия хоста: `xdpyinfo` отрабатывает.
#   3. Внутри контейнера `kicad-cli version` отвечает (KiCad GUI стек в PATH).
#   4. Внутри контейнера `xeyes` стартует и завершается без падения
#      (рендеринг через X11 → реальное GUI-окно, проверка end-to-end).
#
# Ручная серия (50× open/save/close SE-amp фикстуры) — отдельно,
# Vladimir делает руками перед merge (memory feedback_kicad_fixtures.md).
#
# Wayland fallback не покрываем автоматически — у Vladimir'а X11 (GNOME
# on Xorg / KDE Plasma). При появлении Wayland-сценария дополним.
#
# Exit codes:
#   0 — все проверки прошли;
#   1 — какая-то из проверок упала (см. stderr);
#   2 — окружение не подходит (нет DISPLAY, docker недоступен и т.п.).

set -euo pipefail

IMAGE="${EFACTORY_IMAGE:-efactory:linux}"
XEYES_TIMEOUT="${XEYES_TIMEOUT:-3}"

log() { printf '[smoke-gui] %s\n' "$*" >&2; }
fail() { log "FAIL: $*"; exit 1; }
skip() { log "SKIP: $*"; exit 2; }

# ── 0. Окружение ────────────────────────────────────────────────────────────
command -v docker >/dev/null || skip "docker не найден в PATH"
command -v xhost >/dev/null || skip "xhost не найден в PATH (поставь x11-xserver-utils)"
[[ -n "${DISPLAY:-}" ]] || skip "переменная DISPLAY пустая — нет X11 сессии"
[[ -S /tmp/.X11-unix/X"${DISPLAY#:}" ]] || skip "X11 socket /tmp/.X11-unix/X${DISPLAY#:} не найден"

XAUTH_HOST="${XAUTHORITY:-$HOME/.Xauthority}"
[[ -r "$XAUTH_HOST" ]] || fail "XAUTHORITY=$XAUTH_HOST не читается"

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    log "образ $IMAGE не найден локально — собираю"
    docker build -t "$IMAGE" .
fi

# ── 1. xhost: разрешить контейнерному uid доступ к X server ─────────────────
# `+SI:localuser:#<uid>` — узкое правило (только для конкретного uid),
# безопаснее, чем `+local:docker` (любой локальный docker-клиент).
# uid=1000 совпадает с внутренним юзером образа (см. Dockerfile USER 1000:1000).
HOST_UID="$(id -u)"
xhost "+SI:localuser:#${HOST_UID}" >/dev/null
trap 'xhost "-SI:localuser:#${HOST_UID}" >/dev/null || true' EXIT

# ── 2. docker run шаблон ────────────────────────────────────────────────────
# `--rm` — не оставляем мусора. `--user` явно не задаём — образ уже под 1000:1000.
# `--device /dev/dri` подключаем оппортунистически (для GPU-ускорения), при
# отсутствии устройства флаг опускаем — иначе docker откажется стартовать.
DRI_FLAG=()
if [[ -e /dev/dri ]]; then
    DRI_FLAG=(--device /dev/dri:/dev/dri)
fi

run_in_container() {
    docker run --rm \
        -e DISPLAY \
        -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
        -v "$XAUTH_HOST:/efactory/.Xauthority:ro" \
        "${DRI_FLAG[@]}" \
        "$IMAGE" \
        bash -lc "$1"
}

# ── 3. Проверки ─────────────────────────────────────────────────────────────
log "1/3 xdpyinfo (X11 connectivity)"
run_in_container 'xdpyinfo | head -3' || fail "xdpyinfo не отработал внутри контейнера"

log "2/3 kicad-cli version"
run_in_container 'kicad-cli version' || fail "kicad-cli не отвечает внутри контейнера"

log "3/3 xeyes (end-to-end GUI render)"
# xeyes — графическое окно; запускаем в фоне внутри контейнера и через
# timeout убиваем. Цель: убедиться, что окно создаётся без X11 errors.
# `XDG_RUNTIME_DIR` ставим в `/tmp` чтобы dbus-launch не ругался при первом
# запуске (нет пользовательской runtime-директории внутри контейнера).
run_in_container "\
    export XDG_RUNTIME_DIR=/tmp/runtime-\$(id -u); \
    mkdir -p \$XDG_RUNTIME_DIR; chmod 0700 \$XDG_RUNTIME_DIR; \
    timeout ${XEYES_TIMEOUT}s xeyes 2>&1; \
    rc=\$?; \
    # exit 124 = timeout сработал штатно (xeyes жил все ${XEYES_TIMEOUT}s)
    [[ \$rc == 124 || \$rc == 0 ]] || exit \$rc" \
    || fail "xeyes упал с X11-ошибкой (rc≠0, rc≠124)"

log "OK — X11 passthrough работает (image: $IMAGE)"
