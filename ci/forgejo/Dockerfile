# Образ задания гейтов в Forgejo Actions на srv (создан из шаблона репозитория CI srv).
#
# Что внутри и почему:
# - Python 3.13 — сборка python-build-standalone через `uv python install`,
#   та же, что у разработчика (версию задаёт `.python-version` проекта).
# - `uv` из официального образа Astral.
# - `git` и `nodejs` — на них работает `actions/checkout` внутри контейнера.
# - `util-linux` (`flock`) и `procps` — их зовёт `scripts/pytest-guard.sh`.
# Нужны тестам ещё системные пакеты — дописать их в `apt-get install` ниже.
#
# Базовые образы закреплены по digest (поэтому сборка без `--pull`). Собирает образ сам
# workflow (`.forgejo/workflows/gates.yml`, задание `image`): тег — хэш этого файла,
# поэтому правка Dockerfile даёт новый образ, а неизменный берётся из Docker раннера.
FROM ghcr.io/astral-sh/uv:0.12.17@sha256:10787c682e4184e4f290de1171fd4703dc63de99221f10fe1c99002ce7fa9acc AS uv

FROM docker.io/library/debian:trixie-slim@sha256:a29215f6a35e51e22adffa17f89e9d2ef06214e64a2bad10d765c46aea49f11f

# Пакеты apt — в кэше BuildKit: канал srv медленный, повторная сборка не качает заново.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean \
    && echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' \
        > /etc/apt/apt.conf.d/keep-cache \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        git ca-certificates nodejs procps util-linux

COPY --from=uv /uv /uvx /usr/local/bin/

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python \
    UV_LINK_MODE=copy

# Интерпретатор ставится в образ один раз; дальше `uv` его не качает.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv python install 3.13 \
    && ln -s "$(uv python find 3.13)" /usr/bin/python3

ENV UV_PYTHON=3.13 \
    UV_PYTHON_DOWNLOADS=never
