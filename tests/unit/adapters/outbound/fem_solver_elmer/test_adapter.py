"""Unit: ElmerFemSolver material_model parameter + constructor validation (T133 Phase 1)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from adapters.outbound.fem_solver_elmer.adapter import ElmerFemSolver
from ports.outbound.magnetic_field_solver import (
    MagneticFieldSolverFailedError,
    MagneticFieldSolverUnavailableError,
)


class _FakePyOM:
    """Минимальный stub PyOM — unit-тесты не доходят до calculate_core_data."""

    def get_core_materials(self) -> list[dict[str, Any]]:  # noqa: PLR6301
        return []

    def calculate_core_data(  # noqa: PLR6301
        self,
        _core_fd: dict[str, Any],
        _verbose: bool,  # noqa: FBT001
    ) -> dict[str, Any]:
        msg = 'fake calculate_core_data not used in these unit tests'
        raise NotImplementedError(msg)


def _fake_completed(rc: int = 0, stdout: str = '', stderr: str = '') -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def test_default_material_model_is_linear() -> None:
    """Phase 1 default = linear (single supported value пока что)."""
    solver = ElmerFemSolver(_FakePyOM())
    assert solver.material_model == 'linear'


def test_material_model_rejects_unknown_value() -> None:
    with pytest.raises(ValueError, match='material_model'):
        ElmerFemSolver(_FakePyOM(), material_model='nonlinear-frohlich')  # type: ignore[arg-type]


def test_parse_body_int_a_reads_last_float_in_file(tmp_path: Any) -> None:
    """SaveScalars .dat — последний float в файле."""
    scalars = tmp_path / 'scalars.dat'
    scalars.write_text('   3.14159e-5    \n')
    val = ElmerFemSolver._parse_body_int_a(scalars)  # noqa: SLF001
    assert val == pytest.approx(3.14159e-5)


def test_parse_body_int_a_missing_file_raises(tmp_path: Any) -> None:
    """SaveScalars не запустился → нет файла → MagneticFieldSolverFailedError."""
    from ports.outbound.magnetic_field_solver import MagneticFieldSolverFailedError

    with pytest.raises(MagneticFieldSolverFailedError, match='не создал'):
        ElmerFemSolver._parse_body_int_a(tmp_path / 'missing.dat')  # noqa: SLF001


def test_parse_body_int_a_empty_file_raises(tmp_path: Any) -> None:
    scalars = tmp_path / 'scalars.dat'
    scalars.write_text('')
    with pytest.raises(MagneticFieldSolverFailedError, match='не содержит float'):
        ElmerFemSolver._parse_body_int_a(scalars)  # noqa: SLF001


def test_run_gmsh_missing_binary_raises_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """FileNotFoundError → MagneticFieldSolverUnavailableError с install hint."""

    def fake_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        msg = 'gmsh-not-installed'
        raise FileNotFoundError(msg)

    monkeypatch.setattr(subprocess, 'run', fake_run)
    solver = ElmerFemSolver(_FakePyOM())
    with pytest.raises(MagneticFieldSolverUnavailableError, match='gmsh'):
        solver._run_gmsh(tmp_path / 'in.geo', tmp_path / 'out.msh', tmp_path)  # noqa: SLF001


def test_run_gmsh_nonzero_rc_raises_failed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    def fake_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return _fake_completed(rc=1, stderr='gmsh: mesh fail')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    solver = ElmerFemSolver(_FakePyOM())
    with pytest.raises(MagneticFieldSolverFailedError, match='gmsh failed'):
        solver._run_gmsh(tmp_path / 'in.geo', tmp_path / 'out.msh', tmp_path)  # noqa: SLF001


def test_run_elmer_grid_missing_binary_raises_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    def fake_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        msg = 'ElmerGrid-not-installed'
        raise FileNotFoundError(msg)

    monkeypatch.setattr(subprocess, 'run', fake_run)
    solver = ElmerFemSolver(_FakePyOM())
    with pytest.raises(MagneticFieldSolverUnavailableError, match='ElmerGrid'):
        solver._run_elmer_grid(tmp_path / 'in.msh', tmp_path)  # noqa: SLF001


def test_run_elmer_grid_no_header_file_raises_failed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """ElmerGrid rc=0 но mesh-elmer/mesh.header не создан → fail."""

    def fake_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return _fake_completed(rc=0)

    monkeypatch.setattr(subprocess, 'run', fake_run)
    solver = ElmerFemSolver(_FakePyOM())
    with pytest.raises(MagneticFieldSolverFailedError, match='ElmerGrid failed'):
        solver._run_elmer_grid(tmp_path / 'in.msh', tmp_path)  # noqa: SLF001


def test_run_elmer_solver_missing_binary_raises_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    def fake_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        msg = 'ElmerSolver-not-installed'
        raise FileNotFoundError(msg)

    monkeypatch.setattr(subprocess, 'run', fake_run)
    solver = ElmerFemSolver(_FakePyOM())
    with pytest.raises(MagneticFieldSolverUnavailableError, match='ElmerSolver'):
        solver._run_elmer_solver(tmp_path / 'case.sif', tmp_path)  # noqa: SLF001


def test_run_elmer_solver_nonzero_rc_raises_failed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    def fake_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return _fake_completed(rc=2, stderr='solver explosion')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    solver = ElmerFemSolver(_FakePyOM())
    with pytest.raises(MagneticFieldSolverFailedError, match='ElmerSolver failed'):
        solver._run_elmer_solver(tmp_path / 'case.sif', tmp_path)  # noqa: SLF001


def test_run_elmer_solver_fatal_in_stdout_raises_despite_rc0(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """auto-memory: ElmerSolver rc=0 даже при FATAL → FATAL parsing обязателен."""

    def fake_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return _fake_completed(rc=0, stdout='Load: FATAL: Cannot find procedure')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    solver = ElmerFemSolver(_FakePyOM())
    with pytest.raises(MagneticFieldSolverFailedError, match='FATAL/ERROR'):
        solver._run_elmer_solver(tmp_path / 'case.sif', tmp_path)  # noqa: SLF001


def test_run_elmer_solver_error_marker_in_stderr_raises_despite_rc0(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    def fake_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return _fake_completed(rc=0, stderr='ERROR:: convergence failed')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    solver = ElmerFemSolver(_FakePyOM())
    with pytest.raises(MagneticFieldSolverFailedError, match='FATAL/ERROR'):
        solver._run_elmer_solver(tmp_path / 'case.sif', tmp_path)  # noqa: SLF001
