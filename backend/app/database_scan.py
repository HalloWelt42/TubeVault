"""
TubeVault – Scan-Index Datenbank v1.5.61
Separate DB für persistenten Datei-Index.
© HalloWelt42 – Private Nutzung
"""

import aiosqlite
import logging
from pathlib import Path
from app.config import SCAN_DB_PATH

logger = logging.getLogger(__name__)

SCAN_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS scan_index (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    filename TEXT NOT NULL,
    folder TEXT NOT NULL DEFAULT '(Root)',
    title TEXT,
    channel_name TEXT,
    status TEXT NOT NULL DEFAULT 'discovered',
    youtube_id TEXT,
    match_id TEXT,
    match_confidence REAL,
    match_title TEXT,
    file_size INTEGER DEFAULT 0,
    duration INTEGER,
    resolution TEXT,
    has_nfo BOOLEAN DEFAULT 0,
    has_thumb BOOLEAN DEFAULT 0,
    has_subs BOOLEAN DEFAULT 0,
    scanned_at TEXT NOT NULL,
    imported_at TEXT,
    error_msg TEXT
);

CREATE INDEX IF NOT EXISTS idx_scan_status ON scan_index(status);
CREATE INDEX IF NOT EXISTS idx_scan_folder ON scan_index(folder);
CREATE INDEX IF NOT EXISTS idx_scan_youtube_id ON scan_index(youtube_id);
CREATE INDEX IF NOT EXISTS idx_scan_path ON scan_index(path);

CREATE TABLE IF NOT EXISTS scan_state (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


class ScanDatabase:
    """Async SQLite für den Scan-Index (separate DB)."""

    def __init__(self, db_path: Path = SCAN_DB_PATH):
        self.db_path = db_path
        self._connection: aiosqlite.Connection | None = None

    async def connect(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(str(self.db_path))
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.executescript(SCAN_SCHEMA_SQL)
        await self._connection.commit()
        logger.info(f"Scan-DB verbunden: {self.db_path}")

    async def disconnect(self):
        if self._connection:
            await self._connection.close()
            self._connection = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if not self._connection:
            raise RuntimeError("Scan-DB nicht verbunden")
        return self._connection

    async def execute(self, sql: str, params=None):
        cursor = await self.conn.execute(sql, params or ())
        await self.conn.commit()
        return cursor

    async def execute_many(self, sql: str, params_list: list):
        await self.conn.executemany(sql, params_list)
        await self.conn.commit()

    async def fetch_one(self, sql: str, params=None):
        cursor = await self.conn.execute(sql, params or ())
        return await cursor.fetchone()

    async def fetch_all(self, sql: str, params=None):
        cursor = await self.conn.execute(sql, params or ())
        return await cursor.fetchall()

    async def fetch_val(self, sql: str, params=None):
        row = await self.fetch_one(sql, params)
        return row[0] if row else None


# Singleton
scan_db = ScanDatabase()
