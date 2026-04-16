import aiosqlite
from pathlib import Path
from typing import Any


class AsyncDatabase:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode = WAL")
        await self._conn.execute("PRAGMA synchronous = NORMAL")
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute("PRAGMA busy_timeout = 5000")
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def execute(self, sql: str, params: tuple = ()) -> None:
        assert self._conn, "Database not connected"
        await self._conn.execute(sql, params)
        await self._conn.commit()

    async def execute_returning(self, sql: str, params: tuple = ()) -> int | None:
        assert self._conn, "Database not connected"
        cursor = await self._conn.execute(sql, params)
        await self._conn.commit()
        return cursor.lastrowid

    async def fetchone(self, sql: str, params: tuple = (), *, commit: bool = False) -> dict | None:
        assert self._conn, "Database not connected"
        cursor = await self._conn.execute(sql, params)
        row = await cursor.fetchone()
        if commit:
            await self._conn.commit()
        if row is None:
            return None
        return dict(row)

    async def fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        assert self._conn, "Database not connected"
        cursor = await self._conn.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def executemany(self, sql: str, params_list: list[tuple]) -> None:
        assert self._conn, "Database not connected"
        await self._conn.executemany(sql, params_list)
        await self._conn.commit()


class _DbProxy:
    """Lazy proxy so import-time `from app.database import db` works
    before the db_path is known (set in lifespan)."""

    def __init__(self):
        self._delegate: AsyncDatabase | None = None

    def _init(self, db_path: str) -> None:
        self._delegate = AsyncDatabase(db_path)

    async def connect(self) -> None:
        assert self._delegate
        await self._delegate.connect()

    async def close(self) -> None:
        assert self._delegate
        await self._delegate.close()

    async def execute(self, sql: str, params: tuple = ()) -> None:
        assert self._delegate
        await self._delegate.execute(sql, params)

    async def execute_returning(self, sql: str, params: tuple = ()) -> int | None:
        assert self._delegate
        return await self._delegate.execute_returning(sql, params)

    async def fetchone(self, sql: str, params: tuple = (), *, commit: bool = False) -> dict | None:
        assert self._delegate
        return await self._delegate.fetchone(sql, params, commit=commit)

    async def fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        assert self._delegate
        return await self._delegate.fetchall(sql, params)

    async def executemany(self, sql: str, params_list: list[tuple]) -> None:
        assert self._delegate
        await self._delegate.executemany(sql, params_list)


db = _DbProxy()
