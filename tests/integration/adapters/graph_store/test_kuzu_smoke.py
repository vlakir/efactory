"""Smoke-тест на Kùzu — фиксирует, что embedded-graph БД работает в
нашем окружении (Python 3.14, Linux) и что sync-API корректно
оборачивается в `asyncio.to_thread` для использования из async-кода.

Это integration-тест по `T085` Critical #1: проверяем wheel и базовый
сценарий create node / read node. Production-адаптер Kùzu появится
в задаче дорожной карты, которая первой требует графа (T004 / T005 /
T037).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import kuzu


async def _open_db(db_path: Path) -> tuple[kuzu.Database, kuzu.Connection]:
    db = await asyncio.to_thread(kuzu.Database, str(db_path))
    conn = await asyncio.to_thread(kuzu.Connection, db)
    return db, conn


async def _execute(conn: kuzu.Connection, query: str) -> kuzu.QueryResult:
    return await asyncio.to_thread(conn.execute, query)


async def test_kuzu_create_and_read_node(tmp_path: Path) -> None:
    """Open DB in tmp_path, create a node, read it back via async wrapper."""
    db_path = tmp_path / 'graph.kuzu'

    _, conn = await _open_db(db_path)

    await _execute(
        conn,
        'CREATE NODE TABLE Component(name STRING, PRIMARY KEY(name))',
    )
    await _execute(conn, "CREATE (:Component {name: 'R1'})")

    result = await _execute(conn, 'MATCH (c:Component) RETURN c.name')
    rows: list[list[str]] = []
    while await asyncio.to_thread(result.has_next):
        rows.append(await asyncio.to_thread(result.get_next))

    assert rows == [['R1']]
