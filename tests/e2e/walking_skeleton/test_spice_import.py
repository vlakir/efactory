"""E2E: efactory spice import-url / import-file + slash bridge (T030)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from composition.main import build_cli_app

_NGSPICE_AVAILABLE = shutil.which('ngspice') is not None

needs_ngspice = pytest.mark.skipif(
    not _NGSPICE_AVAILABLE,
    reason='ngspice not installed',
)

_FIXTURES = (
    Path(__file__).resolve().parents[2]
    / 'data'
    / 'spice_import'
    / 'vendor_samples'
)


def _setup_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    user_lib = tmp_path / 'user_lib'
    kb_dir = tmp_path / 'kb_host_mutated'
    user_lib.mkdir()
    kb_dir.mkdir()
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(tmp_path / 'projects'))
    monkeypatch.setenv('EFACTORY_SESSION_ROOT', str(tmp_path / 'sessions'))
    monkeypatch.setenv('EFACTORY_USER_LIBRARY_ROOT', str(user_lib))
    monkeypatch.setenv('EFACTORY_KB_HOST_MUTATED_DIR', str(kb_dir))
    monkeypatch.setenv('EFACTORY_KB_BUILT_IN_DIR', str(tmp_path / 'kb_built_in'))
    (tmp_path / 'kb_built_in').mkdir()
    return user_lib, kb_dir


@needs_ngspice
def test_spice_import_file_bjt_npn_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_lib, kb_dir = _setup_env(tmp_path, monkeypatch)
    fixture = _FIXTURES / '2n3904_bjt_npn.lib'

    runner = CliRunner()
    result = runner.invoke(
        build_cli_app(),
        ['spice', 'import-file', str(fixture)],
    )

    assert result.exit_code == 0, result.output
    installed = user_lib / 'bjt' / 'unknown' / 'Q2N3904.lib'
    assert installed.is_file()
    body = installed.read_text()
    assert '* vendor: unknown' in body
    assert '* subcategory: npn' in body
    assert (kb_dir / 'spice.unknown.q2n3904.md').is_file()


@needs_ngspice
def test_spice_import_url_via_file_uri(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_lib, kb_dir = _setup_env(tmp_path, monkeypatch)
    fixture = _FIXTURES / '2n3906_bjt_pnp.lib'
    url = fixture.as_uri()

    runner = CliRunner()
    result = runner.invoke(
        build_cli_app(),
        ['spice', 'import-url', url, '--vendor', 'onsemi'],
    )

    assert result.exit_code == 0, result.output
    installed = user_lib / 'bjt' / 'onsemi' / 'Q2N3906.lib'
    assert installed.is_file()
    assert '* vendor: onsemi' in installed.read_text()
    assert (kb_dir / 'spice.onsemi.q2n3906.md').is_file()


def test_spice_import_dry_run_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_lib, kb_dir = _setup_env(tmp_path, monkeypatch)
    fixture = _FIXTURES / '2n3904_bjt_npn.lib'

    runner = CliRunner()
    result = runner.invoke(
        build_cli_app(),
        ['spice', 'import-file', str(fixture), '--dry-run'],
    )

    assert result.exit_code == 0, result.output
    assert 'DRY-RUN' in result.output.upper()
    assert '2N3904' in result.output or 'Q2N3904' in result.output
    # Filesystem untouched
    assert not (user_lib / 'bjt').exists()
    assert list(kb_dir.iterdir()) == []


def test_spice_import_duplicate_without_force_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_lib, _ = _setup_env(tmp_path, monkeypatch)
    fixture = _FIXTURES / '2n3904_bjt_npn.lib'
    existing = user_lib / 'bjt' / 'unknown' / 'Q2N3904.lib'
    existing.parent.mkdir(parents=True)
    existing.write_text('pre-existing\n')

    runner = CliRunner()
    result = runner.invoke(
        build_cli_app(),
        ['spice', 'import-file', str(fixture), '--skip-smoke'],
    )

    assert result.exit_code == 1, result.output
    assert 'already installed' in result.output or 'duplicate' in result.output.lower()
    assert existing.read_text() == 'pre-existing\n'


def test_spice_import_html_content_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _ = _setup_env(tmp_path, monkeypatch)
    fixture = _FIXTURES / 'html_login_page.lib'

    runner = CliRunner()
    result = runner.invoke(
        build_cli_app(),
        ['spice', 'import-file', str(fixture)],
    )

    assert result.exit_code == 1, result.output
    assert 'html' in result.output.lower() or 'rejected' in result.output.lower()


def test_spice_import_classification_ambiguous(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _ = _setup_env(tmp_path, monkeypatch)
    fixture = _FIXTURES / 'ambiguous_3pin_subckt.lib'

    runner = CliRunner()
    result = runner.invoke(
        build_cli_app(),
        ['spice', 'import-file', str(fixture)],
    )

    assert result.exit_code == 1, result.output
    assert 'ambiguous' in result.output.lower() or 'override' in result.output.lower()


def test_spice_import_invalid_url_scheme(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _ = _setup_env(tmp_path, monkeypatch)

    runner = CliRunner()
    result = runner.invoke(
        build_cli_app(),
        ['spice', 'import-url', 'ftp://example.com/m.lib'],
    )

    assert result.exit_code == 2, result.output
    assert 'scheme' in result.output.lower() or 'download' in result.output.lower()


def test_spice_import_invalid_vendor_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _ = _setup_env(tmp_path, monkeypatch)
    fixture = _FIXTURES / '2n3904_bjt_npn.lib'

    runner = CliRunner()
    result = runner.invoke(
        build_cli_app(),
        ['spice', 'import-file', str(fixture), '--vendor', 'Bad Vendor!'],
    )

    assert result.exit_code != 0
    assert 'vendor' in result.output.lower()
