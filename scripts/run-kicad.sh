#!/usr/bin/env bash
# run-kicad.sh — запуск KiCad GUI из efactory:linux с X11 passthrough.
#
# Тонкая обёртка вокруг `docker run`, нужна на время до T114 (полноценный
# efactory-up). Цель — упростить ритуал ручной проверки T111 (50× open/
# save/close SE-amp фикстуры).
#
# Что делает:
#   1. Разрешает контейнерному uid 1000 доступ к X server (узко).
#   2. Стартует efactory:linux с DISPLAY/X11 socket/XAUTHORITY/GPU.
#   3. После выхода KiCad — откатывает xhost-правило (даже при падении).
#
# Аргументы передаются в kicad как есть, поэтому можно открыть проект:
#   ./scripts/run-kicad.sh /workspace/myprj/myprj.kicad_pro
# (предполагается, что путь живёт внутри одного из bind-mount'ов).
#
# --demo / -d  : смонтировать $HOME/efactory-projects/ в /workspace и сразу
#                открыть SE-amp demo (положенный туда через
#                scripts/gen-se-amp-demo.py). Используется для ритуала
#                ручной проверки T111 (50× open/save/close).
#
# Env:
#   EFACTORY_IMAGE — image tag (default efactory:linux).
#   EFACTORY_KICAD_BIN — какой бинарь стартовать (default kicad; можно
#       eeschema / pcbnew / kicad-cli ...).
#   EFACTORY_PROJECTS_DIR — host directory с проектами (default
#       $HOME/efactory-projects); монтируется при --demo или если
#       существует.

set -euo pipefail

IMAGE="${EFACTORY_IMAGE:-efactory:linux}"
KICAD_BIN="${EFACTORY_KICAD_BIN:-kicad}"
XAUTH_HOST="${XAUTHORITY:-$HOME/.Xauthority}"
HOST_UID="$(id -u)"
PROJECTS_DIR="${EFACTORY_PROJECTS_DIR:-$HOME/efactory-projects}"

DEMO_MODE=0
PASS_ARGS=()
for arg in "$@"; do
    case "$arg" in
        --demo|-d) DEMO_MODE=1 ;;
        *) PASS_ARGS+=("$arg") ;;
    esac
done

[[ -n "${DISPLAY:-}" ]] || { echo "DISPLAY пустой — нет X11 сессии" >&2; exit 2; }
[[ -r "$XAUTH_HOST" ]] || { echo "XAUTHORITY=$XAUTH_HOST не читается" >&2; exit 2; }
docker image inspect "$IMAGE" >/dev/null 2>&1 || { echo "Образ $IMAGE не найден; собери: docker build -t $IMAGE ." >&2; exit 2; }

DRI_ARGS=()
if [[ -e /dev/dri ]]; then
    DRI_ARGS=(--device /dev/dri:/dev/dri)
fi

PROJECTS_ARGS=()
if [[ -d "$PROJECTS_DIR" ]]; then
    PROJECTS_ARGS=(-v "$PROJECTS_DIR:/workspace:rw")
fi

if (( DEMO_MODE )); then
    DEMO_SCH="$PROJECTS_DIR/se-amp-demo/se_amp.kicad_pro"
    if [[ ! -f "$DEMO_SCH" ]]; then
        echo "Demo не найден: $DEMO_SCH" >&2
        echo "Сгенерируй: uv run python scripts/gen-se-amp-demo.py" >&2
        exit 2
    fi
    PASS_ARGS=(/workspace/se-amp-demo/se_amp.kicad_pro "${PASS_ARGS[@]}")
fi

xhost "+SI:localuser:#${HOST_UID}" >/dev/null
trap 'xhost "-SI:localuser:#${HOST_UID}" >/dev/null || true' EXIT

docker run --rm \
    -e DISPLAY \
    -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
    -v "$XAUTH_HOST:/efactory/.Xauthority:ro" \
    "${DRI_ARGS[@]}" \
    "${PROJECTS_ARGS[@]}" \
    "$IMAGE" \
    "$KICAD_BIN" "${PASS_ARGS[@]}"
