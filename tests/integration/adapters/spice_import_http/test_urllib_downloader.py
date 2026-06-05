"""UrllibSpiceModelDownloader — T030 Phase 2.

Live network избегаем — гоняем через `file://` URLs (urllib stdlib
поддерживает) и через локальный http.server fixture.
"""

from __future__ import annotations

import asyncio
import contextlib
import http.server
import socketserver
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from adapters.outbound.spice_import_http.downloader import (
    UrllibSpiceModelDownloader,
)
from domain.spice_import import (
    ContentRejectedError,
    DownloadError,
    ImportSource,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

_FIXTURES = (
    Path(__file__).resolve().parents[3] / 'data' / 'spice_import' / 'vendor_samples'
)


# === file:// URL (stdlib urllib supports it) ===


def test_download_file_url() -> None:
    src = ImportSource(
        kind='url', location=(_FIXTURES / '2n3904_bjt_npn.lib').as_uri()
    )
    dl = UrllibSpiceModelDownloader()
    raw = asyncio.run(dl.download(src, timeout_seconds=5.0, max_bytes=10_000, verify_tls=True))
    assert '.MODEL Q2N3904 NPN' in raw.bytes_text
    assert len(raw.sha256) == 64
    assert raw.source == src


def test_download_local_file_via_import_file_kind() -> None:
    src = ImportSource(kind='file', location=str(_FIXTURES / '2n3906_bjt_pnp.lib'))
    dl = UrllibSpiceModelDownloader()
    raw = asyncio.run(dl.download(src, timeout_seconds=5.0, max_bytes=10_000, verify_tls=True))
    assert '.MODEL Q2N3906 PNP' in raw.bytes_text


def test_download_file_url_nonexistent_raises_download_error() -> None:
    src = ImportSource(kind='url', location='file:///nonexistent/path.lib')
    dl = UrllibSpiceModelDownloader()
    with pytest.raises(DownloadError):
        asyncio.run(dl.download(src, timeout_seconds=5.0, max_bytes=10_000, verify_tls=True))


def test_download_max_bytes_exceeded_raises_content_rejected() -> None:
    # большой файл — установим max_bytes ниже фактического размера фикстуры
    fixture = _FIXTURES / '2n3904_bjt_npn.lib'
    actual_size = fixture.stat().st_size
    src = ImportSource(kind='url', location=fixture.as_uri())
    dl = UrllibSpiceModelDownloader()
    with pytest.raises(ContentRejectedError, match='exceed'):
        asyncio.run(
            dl.download(
                src,
                timeout_seconds=5.0,
                max_bytes=actual_size - 10,
                verify_tls=True,
            ),
        )


# === HTTP via local http.server ===


@contextlib.contextmanager
def _local_http_server(serve_dir: Path) -> 'Iterator[int]':
    handler_cls = http.server.SimpleHTTPRequestHandler

    class _ScopedHandler(handler_cls):  # type: ignore[misc, valid-type]
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, directory=str(serve_dir), **kwargs)  # type: ignore[arg-type]

        def log_message(self, *_args: object) -> None:  # silence per-test stderr
            return

    with socketserver.TCPServer(('127.0.0.1', 0), _ScopedHandler) as srv:
        port = srv.server_address[1]
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        try:
            yield port
        finally:
            srv.shutdown()


def test_download_http_200_returns_raw_import() -> None:
    with _local_http_server(_FIXTURES) as port:
        src = ImportSource(
            kind='url',
            location=f'http://127.0.0.1:{port}/2n3904_bjt_npn.lib',
        )
        dl = UrllibSpiceModelDownloader()
        raw = asyncio.run(
            dl.download(src, timeout_seconds=5.0, max_bytes=10_000, verify_tls=False),
        )
        assert '.MODEL Q2N3904 NPN' in raw.bytes_text


def test_download_http_404_raises_download_error() -> None:
    with _local_http_server(_FIXTURES) as port:
        src = ImportSource(
            kind='url',
            location=f'http://127.0.0.1:{port}/does-not-exist.lib',
        )
        dl = UrllibSpiceModelDownloader()
        with pytest.raises(DownloadError) as ei:
            asyncio.run(
                dl.download(src, timeout_seconds=5.0, max_bytes=10_000, verify_tls=False),
            )
        assert ei.value.status == 404


def test_download_invalid_url_scheme_raises_download_error() -> None:
    src = ImportSource(kind='url', location='ftp://example.com/m.lib')
    dl = UrllibSpiceModelDownloader()
    with pytest.raises(DownloadError, match='scheme'):
        asyncio.run(dl.download(src, timeout_seconds=5.0, max_bytes=10_000, verify_tls=True))


def test_download_html_content_rejected_at_download_time() -> None:
    # HTML файлы тоже должны проходить проверку download'а
    # (sniff content-type, или просто получить bytes — classifier потом
    # отдаст ContentRejectedError; downloader сам не sniff'ит content-type,
    # это работа classifier'а. Здесь — sanity check что HTML файл всё
    # же download'ится и возвращается как text).
    src = ImportSource(kind='url', location=(_FIXTURES / 'html_login_page.lib').as_uri())
    dl = UrllibSpiceModelDownloader()
    raw = asyncio.run(dl.download(src, timeout_seconds=5.0, max_bytes=10_000, verify_tls=True))
    assert '<html>' in raw.bytes_text  # downloader returned bytes, classifier reject'нёт
