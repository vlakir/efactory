"""
UrllibSpiceModelDownloader — T030 adapter.

stdlib `urllib.request` без external deps. Поддерживает schemes
`http`, `https`, `file`. `kind=file` (ImportSource) обрабатывается
прямой read-from-disk (без urllib overhead, без URL escaping).
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import ssl
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final
from urllib.parse import urlparse

from domain.spice_import import (
    ContentRejectedError,
    DownloadError,
    RawImport,
)

if TYPE_CHECKING:
    from domain.spice_import import ImportSource


_ALLOWED_SCHEMES: Final = frozenset({'http', 'https', 'file'})
_DEFAULT_USER_AGENT: Final = (
    'efactory-spice-import/1.0 (+https://github.com/vlakir/efactory)'
)

# Effective TLD+1 для anti-cross-host detection (W3 в spec):
# хост `www.vishay.com` → effective `vishay.com`.
_EFFECTIVE_DOMAIN_RE = re.compile(r'(?:^|\.)([^.]+\.[^.]+)$')


class UrllibSpiceModelDownloader:
    async def download(
        self,
        source: ImportSource,
        *,
        timeout_seconds: float,
        max_bytes: int,
        verify_tls: bool,
    ) -> RawImport:
        if source.kind == 'file':
            return await asyncio.to_thread(
                _read_local_file,
                source=source,
                max_bytes=max_bytes,
            )
        return await asyncio.to_thread(
            _http_download,
            source=source,
            timeout_seconds=timeout_seconds,
            max_bytes=max_bytes,
            verify_tls=verify_tls,
        )


def _read_local_file(*, source: ImportSource, max_bytes: int) -> RawImport:
    path = Path(source.location)
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise DownloadError(
            url=source.location,
            status=None,
            message=f'file not found: {path}',
        ) from exc
    except OSError as exc:
        raise DownloadError(
            url=source.location,
            status=None,
            message=f'IO error: {exc}',
        ) from exc
    if len(data) > max_bytes:
        raise ContentRejectedError(
            reason=f'body size {len(data)} bytes exceeds max_bytes={max_bytes}',
        )
    text = data.decode('utf-8', errors='replace')
    return RawImport(
        source=source,
        bytes_text=text,
        sha256=hashlib.sha256(data).hexdigest(),
        downloaded_at=datetime.now(UTC),
    )


def _http_download(
    *,
    source: ImportSource,
    timeout_seconds: float,
    max_bytes: int,
    verify_tls: bool,
) -> RawImport:
    parsed = urlparse(source.location)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise DownloadError(
            url=source.location,
            status=None,
            message=f'unsupported URL scheme {parsed.scheme!r} '
            f'(allowed: {sorted(_ALLOWED_SCHEMES)})',
        )

    if parsed.scheme == 'file':
        # Деликатно: file:// URL → читаем как локальный путь.
        local_path = parsed.path
        try:
            data = Path(local_path).read_bytes()
        except FileNotFoundError as exc:
            raise DownloadError(
                url=source.location,
                status=None,
                message=f'file not found: {local_path}',
            ) from exc
        if len(data) > max_bytes:
            raise ContentRejectedError(
                reason=f'body size {len(data)} bytes exceeds max_bytes={max_bytes}',
            )
        text = data.decode('utf-8', errors='replace')
        return RawImport(
            source=source,
            bytes_text=text,
            sha256=hashlib.sha256(data).hexdigest(),
            downloaded_at=datetime.now(UTC),
        )

    origin_domain = _effective_domain(parsed.netloc)
    req = urllib.request.Request(  # noqa: S310 — scheme guarded above
        source.location,
        headers={'User-Agent': _DEFAULT_USER_AGENT},
    )
    ctx = ssl.create_default_context() if verify_tls else _insecure_context()
    try:
        with urllib.request.urlopen(  # noqa: S310 — scheme guarded
            req, timeout=timeout_seconds, context=ctx
        ) as resp:
            final_url = resp.geturl()
            final_parsed = urlparse(final_url)
            final_domain = _effective_domain(final_parsed.netloc)
            if final_domain != origin_domain:
                msg = (
                    f'cross-host redirect blocked: '
                    f'{parsed.netloc} → {final_parsed.netloc}'
                )
                raise DownloadError(
                    url=source.location,
                    status=None,
                    message=msg,
                )
            data = resp.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise ContentRejectedError(
                    reason=f'body size > max_bytes={max_bytes}',
                )
    except urllib.error.HTTPError as exc:
        raise DownloadError(
            url=source.location,
            status=exc.code,
            message=exc.reason or 'HTTP error',
        ) from exc
    except urllib.error.URLError as exc:
        raise DownloadError(
            url=source.location,
            status=None,
            message=str(exc.reason),
        ) from exc
    except TimeoutError as exc:
        raise DownloadError(
            url=source.location,
            status=None,
            message=f'timeout after {timeout_seconds}s',
        ) from exc

    text = data.decode('utf-8', errors='replace')
    return RawImport(
        source=source,
        bytes_text=text,
        sha256=hashlib.sha256(data).hexdigest(),
        downloaded_at=datetime.now(UTC),
    )


def _effective_domain(netloc: str) -> str:
    # Удалить порт + creds, оставить host.
    host = netloc.rsplit('@', 1)[-1].split(':', 1)[0].lower()
    m = _EFFECTIVE_DOMAIN_RE.search(host)
    return m.group(1) if m else host


def _insecure_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx
