r"""
Parser ngspice ASCII raw файла → SimulationResult (T008).

Формат raw (одинаковый для OP / TRAN / AC):

    Title: ...
    Date: ...
    Command: ...
    Plotname: Operating Point | Transient Analysis | AC Analysis
    Flags: real | complex
    No. Variables: <N>
    No. Points: <M>
    Variables:
    \t<i>\t<name>\t<type>
    ...
    Values:
     <point_idx>\t<value_0>
    \t<value_1>
    ...
    \t<value_{N-1}>
    [пустая строка]
     <point_idx+1>\t<value_0>
    ...

Для `Flags: complex` каждое значение записано как `<real>,<imag>`.
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.simulation import AcSweep, SimulationResult, TimeSeries

_PLOTNAME_OP = 'Operating Point'
_PLOTNAME_TRAN = 'Transient Analysis'
_PLOTNAME_AC = 'AC Analysis'

_FLAG_REAL = 'real'
_FLAG_COMPLEX = 'complex'


class NgspiceRawParseError(Exception):
    """Файл ngspice raw не соответствует ожидаемому формату."""


@dataclass(frozen=True)
class _Variable:
    name: str


@dataclass(frozen=True)
class _Header:
    plotname: str
    flags: str
    n_variables: int
    n_points: int


_VARIABLE_TOKEN_COUNT = 3


def parse_ngspice_raw(content: str) -> SimulationResult:
    """Разобрать содержимое ngspice ASCII raw файла."""
    if not content.strip():
        msg = 'ngspice raw is empty.'
        raise NgspiceRawParseError(msg)

    lines = content.splitlines()
    header, idx = _parse_header(lines)
    variables, idx = _parse_variables(
        lines,
        idx,
        n_variables=header.n_variables,
    )
    values = _parse_values(
        lines,
        idx,
        n_points=header.n_points,
        n_variables=header.n_variables,
        complex_mode=header.flags == _FLAG_COMPLEX,
    )
    return _build_result(
        plotname=header.plotname,
        flags=header.flags,
        variables=variables,
        values=values,
    )


def _parse_header(lines: list[str]) -> tuple[_Header, int]:
    required = {'Plotname', 'Flags', 'No. Variables', 'No. Points'}
    found: dict[str, str] = {}
    for idx, raw_line in enumerate(lines):
        line = raw_line.rstrip()
        if line == 'Variables:':
            missing = required - found.keys()
            if missing:
                msg = f'ngspice raw header missing keys: {sorted(missing)}.'
                raise NgspiceRawParseError(msg)
            return (
                _Header(
                    plotname=found['Plotname'].strip(),
                    flags=found['Flags'].strip(),
                    n_variables=int(found['No. Variables'].strip()),
                    n_points=int(found['No. Points'].strip()),
                ),
                idx + 1,
            )
        if ':' in line:
            key, _, value = line.partition(':')
            found[key.strip()] = value
    msg = 'ngspice raw missing "Variables:" section.'
    raise NgspiceRawParseError(msg)


def _parse_variables(
    lines: list[str],
    start: int,
    *,
    n_variables: int,
) -> tuple[list[_Variable], int]:
    variables: list[_Variable] = []
    idx = start
    while idx < len(lines) and len(variables) < n_variables:
        line = lines[idx]
        if line.rstrip() == 'Values:':
            break
        # Строка вида '\t<i>\t<name>\t<type>'
        tokens = line.split('\t')
        if len(tokens) >= _VARIABLE_TOKEN_COUNT:
            variables.append(_Variable(name=tokens[2].strip()))
        idx += 1
    if len(variables) != n_variables:
        msg = f'ngspice raw: expected {n_variables} variables, found {len(variables)}.'
        raise NgspiceRawParseError(msg)
    # Skip until 'Values:'
    while idx < len(lines):
        if lines[idx].rstrip() == 'Values:':
            return variables, idx + 1
        idx += 1
    msg = 'ngspice raw missing "Values:" section.'
    raise NgspiceRawParseError(msg)


def _parse_values(
    lines: list[str],
    start: int,
    *,
    n_points: int,
    n_variables: int,
    complex_mode: bool,
) -> list[list[float | tuple[float, float]]]:
    parsed: list[list[float | tuple[float, float]]] = []
    idx = start
    for _point_idx in range(n_points):
        row: list[float | tuple[float, float]] = []
        # Пропустить пустые строки между точками.
        while idx < len(lines) and lines[idx].strip() == '':
            idx += 1
        for var_position in range(n_variables):
            if idx >= len(lines):
                msg = (
                    f'ngspice raw: ran out of lines in Values block '
                    f'at point {_point_idx}, var {var_position}.'
                )
                raise NgspiceRawParseError(msg)
            tokens = lines[idx].split('\t')
            token = tokens[-1].strip() if tokens else ''
            row.append(_parse_token(token, complex_mode=complex_mode))
            idx += 1
        parsed.append(row)
    return parsed


def _parse_token(
    token: str,
    *,
    complex_mode: bool,
) -> float | tuple[float, float]:
    if complex_mode:
        if ',' not in token:
            msg = f'ngspice raw: expected complex token "<real>,<imag>", got {token!r}.'
            raise NgspiceRawParseError(msg)
        real_s, _, imag_s = token.partition(',')
        return (float(real_s), float(imag_s))
    if ',' in token:
        msg = f'ngspice raw: real-mode value contains comma (complex?): {token!r}.'
        raise NgspiceRawParseError(msg)
    return float(token)


def _build_result(
    *,
    plotname: str,
    flags: str,
    variables: list[_Variable],
    values: list[list[float | tuple[float, float]]],
) -> SimulationResult:
    if plotname == _PLOTNAME_OP:
        _require_flag(plotname, flags, _FLAG_REAL)
        operating_points = {
            var.name: _as_float(values[0][i]) for i, var in enumerate(variables)
        }
        return SimulationResult(operating_points=operating_points)
    if plotname == _PLOTNAME_TRAN:
        _require_flag(plotname, flags, _FLAG_REAL)
        axis_idx = 0
        time = tuple(_as_float(row[axis_idx]) for row in values)
        traces = {
            var.name: tuple(_as_float(row[i]) for row in values)
            for i, var in enumerate(variables)
            if i != axis_idx
        }
        return SimulationResult(
            time_series=TimeSeries(time=time, traces=traces),
        )
    if plotname == _PLOTNAME_AC:
        _require_flag(plotname, flags, _FLAG_COMPLEX)
        axis_idx = 0
        frequency = tuple(_as_complex(row[axis_idx])[0] for row in values)
        traces_real = {
            var.name: tuple(_as_complex(row[i])[0] for row in values)
            for i, var in enumerate(variables)
            if i != axis_idx
        }
        traces_imag = {
            var.name: tuple(_as_complex(row[i])[1] for row in values)
            for i, var in enumerate(variables)
            if i != axis_idx
        }
        return SimulationResult(
            ac_sweep=AcSweep(
                frequency=frequency,
                traces_real=traces_real,
                traces_imag=traces_imag,
            ),
        )
    msg = f'ngspice raw: unsupported Plotname {plotname!r}.'
    raise NgspiceRawParseError(msg)


def _require_flag(plotname: str, flags: str, expected: str) -> None:
    if flags != expected:
        msg = (
            f'ngspice raw: Plotname {plotname!r} expects Flags={expected!r}, '
            f'got {flags!r}.'
        )
        raise NgspiceRawParseError(msg)


def _as_float(value: float | tuple[float, float]) -> float:
    if isinstance(value, tuple):
        msg = f'ngspice raw: expected real value, got complex {value!r}.'
        raise NgspiceRawParseError(msg)
    return value


def _as_complex(value: float | tuple[float, float]) -> tuple[float, float]:
    if isinstance(value, tuple):
        return value
    msg = f'ngspice raw: expected complex value, got real {value!r}.'
    raise NgspiceRawParseError(msg)
