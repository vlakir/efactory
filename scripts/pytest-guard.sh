#!/usr/bin/env bash
# Serialise heavy test runs across all git worktrees of this project.
#
# Why: several worktrees (see AGENTS.md → "Параллельная работа в нескольких
# git worktree") share one machine. A full / coverage test run holds a lot of
# RSS; two or three at once — next to a heavy IDE — can stack into OOM or a
# frozen machine. This wrapper is a strict mutex: at most one heavy run
# executes at a time; a second run quietly waits its turn (blocking) and starts
# by itself once the first releases the lock. Only the *launch* is serialised —
# code and uncommitted session state are never touched.
#
# Drop-in prefix for the test runner (pass any pytest arguments through):
#   scripts/pytest-guard.sh                                   # source defaults include cov80
#   scripts/pytest-guard.sh --cov=src --cov-report=term-missing --cov-fail-under=80
#   scripts/pytest-guard.sh tests/test_foo.py -k bar         # any pytest args
#
# The lock is per-user, so different users on one machine never block each other.
#
# Cross-platform: `flock` is util-linux (Linux / macOS-like). Where it is
# absent (e.g. Windows), the wrapper degrades gracefully — it prints one notice
# and runs the tests directly (no serialisation), never failing. CI runners are
# isolated (nothing to share), so they can call the runner directly.
set -euo pipefail

runner_exec() {
    exec uv run pytest "$@"
}

# Optional per-run memory cap (opt-in, off by default → behaves as a plain
# mutex). When PYTEST_GUARD_MEM_MAX is a non-"0" value AND the host is Linux
# with a systemd user session, the run is launched inside a transient cgroup
# with an RSS limit, so a runaway test (e.g. one materialising a giant list) is
# killed by the OOM-killer *inside its own cgroup* — the run fails, but the
# machine and the developer's IDE survive — instead of a system-wide OOM that
# takes down whatever it pleases. `MemorySwapMax=0` avoids swap thrashing.
# Value format is systemd's (e.g. "4G"); "0" disables the cap. Anywhere without
# systemd (macOS, Windows, containers, plain SSH) this is a no-op — the run
# still goes through the mutex below.
run_with_optional_cap() {
    local mem_max="${PYTEST_GUARD_MEM_MAX:-0}"
    if [[ "$mem_max" != "0" ]] \
        && command -v systemd-run >/dev/null 2>&1 \
        && systemctl --user is-active -q default.target 2>/dev/null; then
        exec systemd-run --user --scope --quiet \
            -p "MemoryMax=$mem_max" -p MemorySwapMax=0 \
            -- uv run pytest "$@"
    fi
    runner_exec "$@"
}

# No flock (Windows / non-util-linux): degrade to a direct, unserialised run.
if ! command -v flock >/dev/null 2>&1; then
    echo '>>> [pytest-guard] flock недоступен — запускаю прогон напрямую (без сериализации).' >&2
    run_with_optional_cap "$@"
fi

lock="${TMPDIR:-/tmp}/efactory-pytest-$(id -u).lock"

# fd 9 holds the open lock description; the flock lock lives as long as the fd
# is open and is released on process exit (fd survives exec, closes at the end).
exec 9>"$lock"

if ! flock -n 9; then
    echo '>>> [pytest-guard] Другой тяжёлый прогон уже идёт — жду очереди (мьютекс)…' >&2
    flock 9  # blocking wait until the previous run releases the lock
    echo '>>> [pytest-guard] Лок получен, стартую.' >&2
fi

# fd 9 (the lock) is inherited across exec, so the mutex holds for the whole
# run; the runner's exit code propagates out unchanged.
run_with_optional_cap "$@"
