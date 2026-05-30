"""Regression test: T159 BuildKit cache mounts (apt + uv + FreeCAD AppImage).

Радикальное решение для долгих cold builds: BuildKit `--mount=type=cache`
persistent layers вне image. Файлы скачиваются один раз ever (для данной
version), последующие builds используют cached копию.

Покрывает:
- **apt cache** в base stage + freecad-appimage stage. После первого
  download — повторные builds skip apt download → minutes vs hours.
- **uv cache** в python-deps stage. Повторный `uv sync` skip wheel
  download → секунды vs минуты.
- **FreeCAD AppImage cache** в freecad-appimage stage. 820 MB
  download — happens **один раз ever** (per FREECAD_VERSION). При
  flaky link это огромная экономия.

Dockerfile остаётся portable: первый build на чистом host (или в CI без
cache) — нормальный full download. Subsequent builds — cache hits.

Тесты проверяют **presence** cache mounts в Dockerfile (lockdown
against silent removal при future cleanups).
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOCKERFILE = _REPO_ROOT / 'Dockerfile'


@pytest.fixture
def dockerfile_text() -> str:
    return _DOCKERFILE.read_text(encoding='utf-8')


def test_dockerfile_uses_buildkit_syntax(dockerfile_text: str) -> None:
    """`# syntax=docker/dockerfile:1.X` обязательна для cache mounts."""
    assert dockerfile_text.startswith('# syntax=docker/dockerfile:1.'), (
        'Dockerfile должен начинаться с `# syntax=docker/dockerfile:1.X` '
        'для поддержки `--mount=type=cache` (T159)'
    )


def test_apt_uses_cache_mount_in_base_stage(dockerfile_text: str) -> None:
    """Base stage apt-install использует cache mount для /var/cache/apt."""
    # Find base stage apt RUN block.
    base_idx = dockerfile_text.find('FROM ubuntu:24.04 AS base')
    next_stage_idx = dockerfile_text.find('FROM ', base_idx + 1)
    base_block = dockerfile_text[base_idx:next_stage_idx]

    # apt-get install line should have cache mount.
    assert '--mount=type=cache' in base_block, (
        'Base stage должен использовать `--mount=type=cache` для apt '
        '(T159 — persistent debs cache между builds)'
    )
    assert '/var/cache/apt' in base_block, (
        'Cache mount target должен быть /var/cache/apt'
    )


def test_uv_sync_uses_cache_mount(dockerfile_text: str) -> None:
    """python-deps stage `uv sync` использует cache mount для UV cache."""
    # Find python-deps stage.
    deps_idx = dockerfile_text.find('FROM base AS python-deps')
    if deps_idx == -1:
        pytest.fail('python-deps stage not found')
    next_stage_idx = dockerfile_text.find('FROM ', deps_idx + 1)
    deps_block = dockerfile_text[deps_idx:next_stage_idx]

    assert '--mount=type=cache' in deps_block, (
        'python-deps stage должен использовать `--mount=type=cache` '
        'для uv (T159 — persistent wheel cache)'
    )
    # uv default cache — ~/.cache/uv.
    assert '/root/.cache/uv' in deps_block or '.cache/uv' in deps_block, (
        'Cache mount target должен включать .cache/uv'
    )


def test_freecad_appimage_uses_persistent_cache(dockerfile_text: str) -> None:
    """FreeCAD AppImage download использует persistent cache mount.

    820 MB AppImage — скачивается **один раз ever** (для данной
    FREECAD_VERSION). Critical для slow/flaky links.
    """
    fc_idx = dockerfile_text.find('FROM ubuntu:24.04 AS freecad-appimage')
    if fc_idx == -1:
        pytest.fail('freecad-appimage stage not found')
    next_stage_idx = dockerfile_text.find('\nFROM ', fc_idx + 1)
    if next_stage_idx == -1:
        next_stage_idx = len(dockerfile_text)
    fc_block = dockerfile_text[fc_idx:next_stage_idx]

    assert '--mount=type=cache' in fc_block, (
        'freecad-appimage stage должен использовать `--mount=type=cache` '
        'для AppImage download (T159 — самый важный cache для slow link)'
    )


def test_freecad_appimage_curl_skips_if_cached(dockerfile_text: str) -> None:
    """Cache logic в freecad-appimage: skip curl если cached copy valid.

    Pattern: проверить наличие cached file + sha256 → пропустить curl,
    иначе download.
    """
    fc_idx = dockerfile_text.find('FROM ubuntu:24.04 AS freecad-appimage')
    next_stage_idx = dockerfile_text.find('\nFROM ', fc_idx + 1)
    if next_stage_idx == -1:
        next_stage_idx = len(dockerfile_text)
    fc_block = dockerfile_text[fc_idx:next_stage_idx]

    # Должна быть conditional logic (`if`/`[ -f`/`test`) — иначе curl
    # каждый раз бьёт сеть даже при наличии cached file.
    has_conditional = (
        'if [ -f' in fc_block
        or 'if [ ! -f' in fc_block
        or 'test -f' in fc_block
        or '||' in fc_block  # short-circuit pattern
    )
    assert has_conditional, (
        'freecad-appimage cache mount должен иметь conditional skip '
        'для cached copy — иначе cache не работает (T159 acceptance)'
    )
