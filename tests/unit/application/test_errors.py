"""Application-уровень errors (T098 + T157)."""

from __future__ import annotations

from pathlib import Path

from application.errors import ProjectManifestMissingError


def test_project_manifest_missing_error_carries_path_and_hint() -> None:
    err = ProjectManifestMissingError('demo', Path('/storage/demo'))

    assert err.project_name == 'demo'
    assert err.project_path == Path('/storage/demo')
    msg = str(err)
    assert 'demo' in msg
    assert '/storage/demo' in msg
