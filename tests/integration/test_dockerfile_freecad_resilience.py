"""Regression test: T155 curl retry / HTTP/1.1 для FreeCAD AppImage.

В past sessions замечено, что BuildKit HTTP/2 connection к github.com
releases для FreeCAD AppImage download — flaky. Симптом: cold build
падает на `curl -fsSL ... fc.AppImage` с TLS / connection-reset.

Lockdown: добавить `--http1.1` (избежать HTTP/2 race) + `--retry 3
--retry-delay 5` (defensive против transient network errors).

Тест проверяет что Dockerfile содержит правильные curl флаги для
FreeCAD AppImage download (regression защита).
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOCKERFILE = _REPO_ROOT / 'Dockerfile'


def test_dockerfile_freecad_curl_uses_http_1_1() -> None:
    """FreeCAD AppImage download должен использовать `--http1.1` для
    защиты от BuildKit HTTP/2 flakiness на github.com releases."""
    text = _DOCKERFILE.read_text(encoding='utf-8')
    # Найдём строку с FreeCAD AppImage download.
    assert 'fc.AppImage' in text, 'FreeCAD AppImage download step missing'
    # Find the line(s) с `curl ... fc.AppImage`.
    lines_with_curl = [
        line for line in text.splitlines()
        if 'curl' in line and ('fc.AppImage' in line or '${FREECAD_VERSION}' in line)
    ]
    # Также может быть multi-line — собрать контекст вокруг fc.AppImage.
    idx = text.find('fc.AppImage')
    context_start = text.rfind('RUN ', 0, idx)
    context_end = text.find('\n\n', idx)
    if context_end == -1:
        context_end = len(text)
    context = text[context_start:context_end]

    assert '--http1.1' in context, (
        'FreeCAD AppImage curl должен использовать `--http1.1` '
        '(T155 — BuildKit HTTP/2 flaky на github.com releases)'
    )


def test_dockerfile_freecad_curl_has_retry() -> None:
    """FreeCAD AppImage download должен использовать `--retry` для
    защиты от transient network errors."""
    text = _DOCKERFILE.read_text(encoding='utf-8')
    idx = text.find('fc.AppImage')
    context_start = text.rfind('RUN ', 0, idx)
    context_end = text.find('\n\n', idx)
    if context_end == -1:
        context_end = len(text)
    context = text[context_start:context_end]

    assert '--retry' in context, (
        'FreeCAD AppImage curl должен использовать `--retry N` '
        '(T155 — defensive против transient network errors)'
    )


def test_dockerfile_freecad_curl_has_retry_all_errors() -> None:
    """`--retry-all-errors` обязателен: без него exit 18 (partial
    transfer — самый частый mode failure на github.com releases) НЕ
    triggers retry. Обнаружено 2026-05-30 в warm rebuild T141."""
    text = _DOCKERFILE.read_text(encoding='utf-8')
    idx = text.find('fc.AppImage')
    context_start = text.rfind('RUN ', 0, idx)
    context_end = text.find('\n\n', idx)
    if context_end == -1:
        context_end = len(text)
    context = text[context_start:context_end]

    assert '--retry-all-errors' in context, (
        'FreeCAD AppImage curl должен использовать `--retry-all-errors` '
        '(T155 follow-up — без него exit 18 partial-transfer не '
        'триггерит retry)'
    )


def test_dockerfile_freecad_curl_has_max_time() -> None:
    """`--max-time` защищает от hung connections (curl default = infinity).

    Без cap warm rebuild T141 застрял на 84 мин на single attempt вместо
    retry'я после короткого timeout.
    """
    text = _DOCKERFILE.read_text(encoding='utf-8')
    idx = text.find('fc.AppImage')
    context_start = text.rfind('RUN ', 0, idx)
    context_end = text.find('\n\n', idx)
    if context_end == -1:
        context_end = len(text)
    context = text[context_start:context_end]

    assert '--max-time' in context, (
        'FreeCAD AppImage curl должен использовать `--max-time SEC` '
        '(T155 follow-up — без cap hung connections не fail-fast в retry)'
    )


def test_dockerfile_freecad_curl_has_resume() -> None:
    """`-C -` (`--continue-at -`) — resume from partial download.

    Без него каждая retry начинает с нуля. На slow link (~7 MB/min) +
    820 MB AppImage даже 60-минутный `--max-time` cap не успевает в
    одну попытку. С `-C -` retries продолжают с offset → faster overall.
    Обнаружено в warm rebuild T141 #2 (2026-05-30, 33 min, 227/820 MB).
    """
    text = _DOCKERFILE.read_text(encoding='utf-8')
    idx = text.find('fc.AppImage')
    context_start = text.rfind('RUN ', 0, idx)
    context_end = text.find('\n\n', idx)
    if context_end == -1:
        context_end = len(text)
    context = text[context_start:context_end]

    # `-C -` (short form) или `--continue-at -` (long form).
    has_short = '-C -' in context or '-C-' in context
    has_long = '--continue-at' in context
    assert has_short or has_long, (
        'FreeCAD AppImage curl должен использовать `-C -` или '
        '`--continue-at -` для resume partial transfer'
    )
