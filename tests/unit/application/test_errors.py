"""Application-уровень errors для T098 manifest-primary write-path."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from application.errors import IndexPersistenceError, ProjectManifestMissingError


def test_index_persistence_error_carries_project_name_and_original() -> None:
    cause = SQLAlchemyError('connection lost')
    err = IndexPersistenceError('demo', cause)

    assert err.project_name == 'demo'
    assert err.__cause__ is cause
    assert 'demo' in str(err)
    assert 'reindex' in str(err).lower()


def test_project_manifest_missing_error_carries_path_and_hint() -> None:
    err = ProjectManifestMissingError('demo', Path('/storage/demo'))

    assert err.project_name == 'demo'
    assert err.project_path == Path('/storage/demo')
    msg = str(err)
    assert 'demo' in msg
    assert '/storage/demo' in msg
    assert 'reindex' in msg.lower()
