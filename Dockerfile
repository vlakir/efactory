# syntax=docker/dockerfile:1.7
#
# efactory:linux — Phase 0.9 Containerization.
#
# Phase 0 (T110): базовый Dockerfile с CLI-стеком (KiCad 10, ngspice,
# uv-managed Python 3.14, editable efactory). Acceptance: `docker build`
# зелёный, `docker run … uv run pytest` прогоняет тест-набор efactory.
#
# Phase 1 (T111): X11/Wayland GUI passthrough. Final stage расширен
# runtime-инструментами (`x11-apps`, `x11-utils`, `libgl1`, `dbus-x11`,
# `xauth`, `mesa-utils`); сам `kicad` apt-пакет уже тянет Qt/GUI .so
# зависимости в Phase 0. Один образ (`efactory:linux`); разделение на
# slim CI-variant — T120/T121.
#
# Phase 2 (T112): FreeCAD 1.1.1 через AppImage (variant C, ADR
# 2026-05-20 в DECISIONS.md). Отдельный stage `freecad-appimage`
# скачивает AppImage + Sheet Metal addon в build-time; final stage
# копирует /opt/freecad/ + симлинки на freecadcmd / freecad. Qt6
# runtime deps добавлены в base stage. +3 GB к образу.
#
# FEM-solver (T113), CI (T115), AppImage cleanup (T120) — отдельные
# фазы внутри Phase 0.9, отдельные PR.


# ============================================================================
# Stage 1: base — Ubuntu 24.04 LTS + apt-toolchain (KiCad 10, ngspice).
# ============================================================================
FROM ubuntu:24.04 AS base

ENV DEBIAN_FRONTEND=noninteractive

# KiCad 10 — из официального PPA `kicad/kicad-10.0-releases`
# (см. spec §3, ADR от 2026-05-19 «Distribution: Linux Docker image»).
# ngspice — из universe Ubuntu 24.04.
# X11 runtime (T111, spec §Phase 1):
#   - `libgl1` + `mesa-utils` — OpenGL для KiCad/pcbnew рендеринга
#     (software fallback при отсутствии `/dev/dri`).
#   - `xauth` — обработка X-cookies через bind-mount `$XAUTHORITY`.
#   - `dbus-x11` — D-Bus session для clipboard и Qt theming.
#   - `x11-apps` + `x11-utils` — `xeyes`/`xdpyinfo` для smoke-теста.
#   - `libcanberra-gtk3-module` — GTK system sounds (без него startup
#     warning «Failed to load module canberra-gtk-module», cosmetic).
# Qt6 runtime для FreeCAD AppImage (T112): FreeCAD 1.1 bundle несёт Qt6,
# но depends-on system shared libs для xcb-plugin / EGL / audio / NSS.
# Если этих deps нет — `freecad --version` падает с `Could not load the
# Qt platform plugin "xcb"`. KiCad apt-пакет покрывает только Qt5 — Qt6
# отдельно.
# Locales (T111): `locales` + locale-gen для `ru_RU.UTF-8` и `en_US.UTF-8`.
# KiCad sample translations (`/usr/share/kicad/internat/<lang>/kicad.mo`)
# уже в `kicad` apt-пакете; недостаёт только сгенерированных locale —
# без них `LANG=ru_RU.UTF-8` в runtime отвалится в `C.UTF-8`.
# `--no-install-recommends` отсекает GUI-документацию и спутниковые тулзы
# (spec §N1, N6).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      gnupg \
      passwd \
      software-properties-common \
 && add-apt-repository -y ppa:kicad/kicad-10.0-releases \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      kicad \
      ngspice \
      dbus-x11 \
      libcanberra-gtk3-module \
      libgl1 \
      locales \
      mesa-utils \
      x11-apps \
      x11-utils \
      xauth \
      libasound2t64 \
      libegl1 \
      libnss3 \
      libopengl0 \
      libxcb-cursor0 \
      libxcb-icccm4 \
      libxcb-image0 \
      libxcb-keysyms1 \
      libxcb-render-util0 \
      libxcb-shape0 \
      libxcb-xkb1 \
      libxcomposite1 \
      libxdamage1 \
      libxkbcommon-x11-0 \
      libxrandr2 \
      libxtst6 \
 && sed -i \
      -e 's/^# *\(en_US.UTF-8 UTF-8\)/\1/' \
      -e 's/^# *\(ru_RU.UTF-8 UTF-8\)/\1/' \
      /etc/locale.gen \
 && locale-gen \
 && apt-get purge -y software-properties-common gnupg \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*


# ============================================================================
# Stage 2: python-deps — uv-managed Python 3.14 venv + frozen зависимости.
# ============================================================================
FROM base AS python-deps

# uv бинарь берём из официального образа Astral (без curl-install скрипта).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Фиксированное место venv, ожидаемое spec'ом (см. C1 acceptance).
# UV_LINK_MODE=copy — обходит warning про hardlinks между stages.
ENV UV_PROJECT_ENVIRONMENT=/opt/efactory/.venv \
    UV_LINK_MODE=copy \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python

WORKDIR /opt/efactory

# Слой зависимостей: меняется только при правке pyproject.toml / uv.lock.
# Без `--no-install-project` поднимет hatchling и попытается build
# efactory без исходников → fail. Поэтому деплоим зависимости отдельно.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project


# ============================================================================
# Stage 3: efactory-code — editable install проекта поверх deps-слоя.
# ============================================================================
FROM python-deps AS efactory-code

# Сорсы и данные. Тесты копируются — Phase 0 acceptance гоняет pytest
# внутри образа. `scripts/` копируется потому что gen-bracket-demo.py
# (T112) запускается через `freecadcmd` внутри контейнера (FreeCAD API
# доступен только в образе; host у пользователя FreeCAD не имеет).
# `.dockerignore` исключает `.git/`, кэши, output-фикстуры.
COPY src/ ./src/
COPY data/ ./data/
COPY tests/ ./tests/
COPY scripts/ ./scripts/
COPY hatch_build.py README.md alembic.ini ./

# Editable install: T114 `efactory-up --dev` сможет bind-mount'ить
# host src/ поверх `/opt/efactory/src/` без пересборки образа.
# hatch_build хук (T095) silently skips при отсутствии `.git/`
# (см. hatch_build.py).
RUN uv sync --frozen


# ============================================================================
# Stage 3.5: freecad-appimage — extract FreeCAD AppImage + Sheet Metal addon.
# ============================================================================
# T112 (variant C, ADR 2026-05-20). FreeCAD 1.1+ нет в apt — берём AppImage
# с GitHub releases, распаковываем `--appimage-extract` в /opt/freecad/ (без
# FUSE на runtime). Sheet Metal addon — git clone pinned SHA в Mod/.
# SHA256 проверяется против upstream `.AppImage-SHA256.txt` (поставляется
# на том же releases-странице).
# Используется минимальный base (ubuntu:24.04 без apt-stack из stage 1) —
# stage идёт через `COPY --from=...` в final, никакие apt-зависимости не
# тащутся.
FROM ubuntu:24.04 AS freecad-appimage

ARG FREECAD_VERSION=1.1.1
ARG FREECAD_SHA256=e2006138400b2fa85fa2e160e872d00767eb32964e85075830f7e198a3a876e1
ARG SHEETMETAL_SHA=8076898be2d888c3c634dee343af2349c974a1d0

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      git \
 && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

WORKDIR /tmp/freecad
RUN curl -fsSL -o fc.AppImage \
      "https://github.com/FreeCAD/FreeCAD/releases/download/${FREECAD_VERSION}/FreeCAD_${FREECAD_VERSION}-Linux-x86_64-py311.AppImage" \
 && echo "${FREECAD_SHA256}  fc.AppImage" | sha256sum -c - \
 && chmod +x fc.AppImage \
 && ./fc.AppImage --appimage-extract >/dev/null \
 && mv squashfs-root /opt/freecad \
 && rm fc.AppImage \
 && git clone --no-checkout https://github.com/shaise/FreeCAD_SheetMetal.git \
      /opt/freecad/usr/Mod/SheetMetal \
 && git -C /opt/freecad/usr/Mod/SheetMetal checkout "${SHEETMETAL_SHA}" \
 && rm -rf /opt/freecad/usr/Mod/SheetMetal/.git


# ============================================================================
# Stage 4: final — efactory:linux.
# ============================================================================
FROM efactory-code AS final

# Runtime среда: venv в PATH, чистый buffering.
ENV PATH=/opt/efactory/.venv/bin:/usr/local/bin:/usr/bin:/bin \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/efactory/.venv \
    UV_LINK_MODE=copy

# C1 fix: venv и WORKDIR во владении uid 1000. Ubuntu 24.04 base image
# идёт с pre-created пользователем `ubuntu` (uid=1000, gid=1000) — его
# и используем, переназначаем HOME на /opt/efactory. В T114 wrapper
# подменит на `--user $(id -u):$(id -g)` хоста; пока uid 1000 на dev-
# машине совпадает с vlakir.
RUN chown -R 1000:1000 /opt/efactory

# T112 — FreeCAD: копируем extracted AppImage + Sheet Metal addon из
# stage 3.5; root-owned read-only достаточно (пользователь только читает).
# Симлинки в /usr/local/bin/ — добавляем `freecadcmd` и `freecad` в PATH.
# `freecad` указывает на AppRun (выставляет LD_LIBRARY_PATH / PYTHONPATH
# bundled Qt/Python из AppImage перед exec'ом FreeCAD).
COPY --from=freecad-appimage /opt/freecad /opt/freecad
RUN ln -s /opt/freecad/usr/bin/freecadcmd /usr/local/bin/freecadcmd \
 && ln -s /opt/freecad/AppRun /usr/local/bin/freecad

# C3 mount targets: user-agnostic пути (spec §5 «Volume mounts»).
# `/efactory/.claude` — credentials для Claude Code (T114), `/workspace`
# — проекты пользователя, `/libs` — custom libraries.
# `/efactory/.Xauthority` (T111) создаёт сам docker при `-v
# $XAUTHORITY:/efactory/.Xauthority:ro`, parent `/efactory` уже есть.
RUN mkdir -p /efactory/.claude /workspace /libs \
 && chmod 0755 /efactory /efactory/.claude /workspace /libs

ENV EFACTORY_VERSION=linux-dev \
    CLAUDE_CONFIG_DIR=/efactory/.claude \
    EFACTORY_PROJECTS_ROOT=/workspace \
    EFACTORY_LIBS_ROOT=/libs \
    XAUTHORITY=/efactory/.Xauthority \
    HOME=/opt/efactory \
    LANG=C.UTF-8 \
    NO_AT_BRIDGE=1

WORKDIR /opt/efactory
USER 1000:1000

# Default CMD — лёгкая self-check. Acceptance Phase 0 переопределяет
# CMD на `uv run pytest` (см. README / spec). ENTRYPOINT не задаём,
# чтобы `docker run … <любая команда>` работал без обёртки.
CMD ["bash", "-lc", "echo 'efactory:linux ('$EFACTORY_VERSION') ready. Try: docker run --rm efactory:linux uv run pytest'"]
