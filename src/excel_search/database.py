from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .models import CellEntry, IndexStats, SearchResult
from .paths import canonical_file_key
from .text import query_terms


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    source_key TEXT NOT NULL UNIQUE,
    path TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('file', 'folder')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY,
    file_key TEXT NOT NULL UNIQUE,
    path TEXT NOT NULL,
    name TEXT NOT NULL,
    size INTEGER NOT NULL DEFAULT 0,
    mtime_ns INTEGER NOT NULL DEFAULT 0,
    indexed_at TEXT,
    status TEXT NOT NULL DEFAULT 'ready',
    error TEXT NOT NULL DEFAULT '',
    cell_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cells (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    sheet TEXT NOT NULL,
    row_number INTEGER NOT NULL,
    cell_reference TEXT NOT NULL,
    value_a TEXT NOT NULL DEFAULT '',
    value_b TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    value_d TEXT NOT NULL DEFAULT '',
    normalized TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cells_file ON cells(file_id);
CREATE INDEX IF NOT EXISTS idx_cells_location ON cells(file_id, sheet, row_number);
CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
"""


class IndexDatabase:
    def __init__(self, path: Path):
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.session() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            connection.executescript(SCHEMA)
            self._migrate_schema(connection)
            self._initialize_full_text_search(connection)
            connection.execute(
                "INSERT INTO meta(key, value) VALUES('schema_version', '3') "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
            )

    @staticmethod
    def _migrate_schema(connection: sqlite3.Connection) -> None:
        version_row = connection.execute(
            "SELECT value FROM meta WHERE key='schema_version'"
        ).fetchone()
        try:
            previous_version = int(version_row["value"]) if version_row else 0
        except (TypeError, ValueError):
            previous_version = 0
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(cells)").fetchall()
        }
        if "value_d" not in columns:
            connection.execute(
                "ALTER TABLE cells ADD COLUMN value_d TEXT NOT NULL DEFAULT ''"
            )
        if previous_version < 3:
            connection.execute(
                "UPDATE files SET status='stale', error='' WHERE status='ready'"
            )

    def _initialize_full_text_search(self, connection: sqlite3.Connection) -> None:
        already_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='cell_fts'"
        ).fetchone()
        try:
            connection.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS cell_fts USING fts5("
                "normalized, content='cells', content_rowid='id', tokenize='trigram')"
            )
            connection.executescript(
                """
                CREATE TRIGGER IF NOT EXISTS cells_ai AFTER INSERT ON cells BEGIN
                    INSERT INTO cell_fts(rowid, normalized) VALUES (new.id, new.normalized);
                END;
                CREATE TRIGGER IF NOT EXISTS cells_ad AFTER DELETE ON cells BEGIN
                    INSERT INTO cell_fts(cell_fts, rowid, normalized)
                    VALUES ('delete', old.id, old.normalized);
                END;
                CREATE TRIGGER IF NOT EXISTS cells_au AFTER UPDATE OF normalized ON cells BEGIN
                    INSERT INTO cell_fts(cell_fts, rowid, normalized)
                    VALUES ('delete', old.id, old.normalized);
                    INSERT INTO cell_fts(rowid, normalized) VALUES (new.id, new.normalized);
                END;
                """
            )
            if not already_exists:
                connection.execute("INSERT INTO cell_fts(cell_fts) VALUES('rebuild')")
            self._set_meta(connection, "search_mode", "fts5_trigram")
        except sqlite3.OperationalError:
            self._set_meta(connection, "search_mode", "substring")

    @staticmethod
    def _set_meta(connection: sqlite3.Connection, key: str, value: str) -> None:
        connection.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def add_source(self, path: Path, kind: str) -> None:
        source_path = path.expanduser().resolve(strict=False)
        with self.session() as connection:
            connection.execute(
                """
                INSERT INTO sources(source_key, path, kind, created_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(source_key) DO UPDATE SET path=excluded.path, kind=excluded.kind
                """,
                (
                    canonical_file_key(source_path),
                    str(source_path),
                    kind,
                    _utc_now(),
                ),
            )

    def list_sources(self) -> tuple[Path, ...]:
        with self.session() as connection:
            rows = connection.execute("SELECT path FROM sources ORDER BY path").fetchall()
        return tuple(Path(row["path"]) for row in rows)

    def file_is_current(self, path: Path, size: int, mtime_ns: int) -> bool:
        with self.session() as connection:
            row = connection.execute(
                "SELECT size, mtime_ns, status FROM files WHERE file_key = ?",
                (canonical_file_key(path),),
            ).fetchone()
        return bool(
            row
            and row["status"] == "ready"
            and row["size"] == size
            and row["mtime_ns"] == mtime_ns
        )

    def replace_file_cells(
        self,
        path: Path,
        size: int,
        mtime_ns: int,
        entries: Iterable[CellEntry],
    ) -> int:
        file_path = path.expanduser().resolve(strict=False)
        file_key = canonical_file_key(file_path)
        count = 0
        with self.session() as connection:
            row = connection.execute(
                "SELECT id FROM files WHERE file_key = ?", (file_key,)
            ).fetchone()
            if row:
                file_id = int(row["id"])
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO files(file_key, path, name, size, mtime_ns, status)
                    VALUES(?, ?, ?, ?, ?, 'indexing')
                    """,
                    (file_key, str(file_path), file_path.name, size, mtime_ns),
                )
                file_id = int(cursor.lastrowid)

            connection.execute("DELETE FROM cells WHERE file_id = ?", (file_id,))
            batch: list[tuple[object, ...]] = []
            for entry in entries:
                batch.append(
                    (
                        file_id,
                        entry.sheet,
                        entry.row_number,
                        entry.cell_reference,
                        entry.value_a,
                        entry.value_b,
                        entry.content,
                        entry.value_d,
                        entry.normalized,
                    )
                )
                count += 1
                if len(batch) >= 1000:
                    self._insert_cells(connection, batch)
                    batch.clear()
            if batch:
                self._insert_cells(connection, batch)

            connection.execute(
                """
                UPDATE files
                SET path = ?, name = ?, size = ?, mtime_ns = ?, indexed_at = ?,
                    status = 'ready', error = '', cell_count = ?
                WHERE id = ?
                """,
                (
                    str(file_path),
                    file_path.name,
                    size,
                    mtime_ns,
                    _utc_now(),
                    count,
                    file_id,
                ),
            )
        return count

    @staticmethod
    def _insert_cells(
        connection: sqlite3.Connection, rows: list[tuple[object, ...]]
    ) -> None:
        connection.executemany(
            """
            INSERT INTO cells(
                file_id, sheet, row_number, cell_reference,
                value_a, value_b, content, value_d, normalized
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    def record_error(self, path: Path, error: str) -> None:
        file_path = path.expanduser().resolve(strict=False)
        try:
            stat = file_path.stat()
            size, mtime_ns = stat.st_size, stat.st_mtime_ns
        except OSError:
            size, mtime_ns = 0, 0
        with self.session() as connection:
            connection.execute(
                """
                INSERT INTO files(
                    file_key, path, name, size, mtime_ns, indexed_at,
                    status, error, cell_count
                ) VALUES(?, ?, ?, ?, ?, ?, 'error', ?, 0)
                ON CONFLICT(file_key) DO UPDATE SET
                    path=excluded.path,
                    name=excluded.name,
                    size=excluded.size,
                    mtime_ns=excluded.mtime_ns,
                    indexed_at=excluded.indexed_at,
                    status='error',
                    error=excluded.error
                """,
                (
                    canonical_file_key(file_path),
                    str(file_path),
                    file_path.name,
                    size,
                    mtime_ns,
                    _utc_now(),
                    error[:2000],
                ),
            )

    def mark_missing_files(self) -> int:
        with self.session() as connection:
            rows = connection.execute("SELECT id, path FROM files").fetchall()
            missing_ids = [int(row["id"]) for row in rows if not Path(row["path"]).is_file()]
            connection.executemany(
                "UPDATE files SET status='missing', error='文件不存在或已被移动' WHERE id=?",
                ((file_id,) for file_id in missing_ids),
            )
        return len(missing_ids)

    def clear_index(self) -> None:
        with self.session() as connection:
            connection.execute("DELETE FROM cells")
            connection.execute("DELETE FROM files")

    def search(self, query: str, limit: int = 500) -> list[SearchResult]:
        terms = query_terms(query)
        if not terms:
            return []
        with self.session() as connection:
            mode_row = connection.execute(
                "SELECT value FROM meta WHERE key='search_mode'"
            ).fetchone()
            mode = mode_row["value"] if mode_row else "substring"
            if mode == "fts5_trigram" and any(len(term) >= 3 for term in terms):
                try:
                    rows = self._search_fts(connection, terms, limit)
                except sqlite3.OperationalError:
                    rows = self._search_substring(connection, terms, limit)
            else:
                rows = self._search_substring(connection, terms, limit)
        return [_row_to_result(row) for row in rows]

    @staticmethod
    def _search_fts(
        connection: sqlite3.Connection, terms: tuple[str, ...], limit: int
    ) -> list[sqlite3.Row]:
        long_terms = tuple(term for term in terms if len(term) >= 3)
        short_terms = tuple(term for term in terms if len(term) < 3)
        match_query = " AND ".join(_fts_quote(term) for term in long_terms)
        short_conditions = "".join(" AND instr(c.normalized, ?) > 0" for _ in short_terms)
        sql = f"""
            SELECT
                f.path, f.name, f.mtime_ns,
                c.sheet, c.row_number, c.cell_reference,
                c.value_a, c.value_b, c.content, c.value_d,
                bm25(cell_fts) AS score
            FROM cell_fts
            JOIN cells c ON c.id = cell_fts.rowid
            JOIN files f ON f.id = c.file_id
            WHERE cell_fts MATCH ?
              AND f.status = 'ready'
              {short_conditions}
            ORDER BY score, f.name COLLATE NOCASE, c.sheet, c.row_number
            LIMIT ?
        """
        parameters: tuple[object, ...] = (match_query, *short_terms, max(1, min(limit, 5000)))
        return connection.execute(sql, parameters).fetchall()

    @staticmethod
    def _search_substring(
        connection: sqlite3.Connection, terms: tuple[str, ...], limit: int
    ) -> list[sqlite3.Row]:
        conditions = " AND ".join("instr(c.normalized, ?) > 0" for _ in terms)
        sql = f"""
            SELECT
                f.path, f.name, f.mtime_ns,
                c.sheet, c.row_number, c.cell_reference,
                c.value_a, c.value_b, c.content, c.value_d
            FROM cells c
            JOIN files f ON f.id = c.file_id
            WHERE f.status = 'ready' AND {conditions}
            ORDER BY f.name COLLATE NOCASE, c.sheet, c.row_number
            LIMIT ?
        """
        parameters: tuple[object, ...] = (*terms, max(1, min(limit, 5000)))
        return connection.execute(sql, parameters).fetchall()

    def stats(self) -> IndexStats:
        with self.session() as connection:
            row = connection.execute(
                """
                SELECT
                    SUM(CASE WHEN status='ready' THEN 1 ELSE 0 END) AS ready_files,
                    SUM(CASE WHEN status IN ('error', 'missing') THEN 1 ELSE 0 END) AS failed_files,
                    SUM(CASE WHEN status='ready' THEN cell_count ELSE 0 END) AS cell_count
                FROM files
                """
            ).fetchone()
            source_count = connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        return IndexStats(
            ready_files=int(row["ready_files"] or 0),
            failed_files=int(row["failed_files"] or 0),
            cell_count=int(row["cell_count"] or 0),
            source_count=int(source_count),
        )

    def has_stale_files(self) -> bool:
        with self.session() as connection:
            row = connection.execute(
                "SELECT 1 FROM files WHERE status='stale' LIMIT 1"
            ).fetchone()
        return row is not None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fts_quote(term: str) -> str:
    return f'"{term.replace(chr(34), chr(34) * 2)}"'


def _row_to_result(row: sqlite3.Row) -> SearchResult:
    return SearchResult(
        file_path=Path(row["path"]),
        file_name=row["name"],
        modified_ns=int(row["mtime_ns"]),
        sheet=row["sheet"],
        row_number=int(row["row_number"]),
        cell_reference=row["cell_reference"],
        value_a=row["value_a"],
        value_b=row["value_b"],
        content=row["content"],
        value_d=row["value_d"],
    )
