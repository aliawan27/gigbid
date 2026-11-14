"""Durable checkpointer + long-term store. Postgres when DATABASE_URL is a postgres URL (deployment, C6),
SQLite otherwise (local dev / tests). Opened once per process."""
from __future__ import annotations

import os
from pathlib import Path

import asyncio

_by_loop: dict[int, tuple] = {}  # one checkpointer/store (and DB pool) per event loop: API loop + worker thread loop
_saver = None
_store = None
_ctx = []


def db_url() -> str:
    return os.getenv("DATABASE_URL", "") or ""


def is_postgres() -> bool:
    return db_url().startswith("postgres")


async def open_persistence():
    key = id(asyncio.get_running_loop())
    if key in _by_loop:
        return _by_loop[key]
    saver, store = await _open()
    _by_loop[key] = (saver, store)
    return saver, store


async def _open():
    global _saver, _store
    if is_postgres():
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from langgraph.store.postgres.aio import AsyncPostgresStore
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool
        url = db_url().replace("postgresql+psycopg://", "postgresql://")
        pool = AsyncConnectionPool(url, max_size=5, open=False,
                                   kwargs={"autocommit": True, "prepare_threshold": None, "row_factory": dict_row})
        await pool.open()
        _ctx.append(pool)
        _saver, _store = AsyncPostgresSaver(pool), AsyncPostgresStore(pool)
    else:
        import aiosqlite
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        from langgraph.store.sqlite.aio import AsyncSqliteStore
        path = Path(os.getenv("GIGBID_SQLITE", Path(__file__).resolve().parents[1] / "data" / "gigbid_graph.db"))
        path.parent.mkdir(parents=True, exist_ok=True)
        c1 = await aiosqlite.connect(str(path), isolation_level=None)
        c2 = await aiosqlite.connect(str(path) + ".store", isolation_level=None)  # noqa: ASYNC
        _ctx.extend([c1, c2])
        _saver, _store = AsyncSqliteSaver(c1), AsyncSqliteStore(c2)
    await _saver.setup()
    await _store.setup()
    saver, store = _saver, _store
    _saver = _store = None
    return saver, store


async def close_persistence():
    global _saver, _store
    for c in _ctx:
        try:
            await c.close()
        except Exception:  # noqa: BLE001
            pass
    _ctx.clear()
    _saver = _store = None
