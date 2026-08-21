import sqlite3
from contextlib import closing
from pathlib import Path

from excel_search.database import IndexDatabase
from excel_search.models import CellEntry
from excel_search.text import normalize_text


def _entry(row: int, content: str, value_d: str = "") -> CellEntry:
    value_a = "HZ015"
    value_b = f"B{row}"
    return CellEntry(
        sheet="物料表",
        row_number=row,
        value_a=value_a,
        value_b=value_b,
        content=content,
        value_d=value_d,
        normalized=normalize_text(f"{value_a} {value_b} {content} {value_d}"),
    )


def _index(database: IndexDatabase, path: Path, entries: list[CellEntry]) -> None:
    path.touch(exist_ok=True)
    stat = path.stat()
    database.replace_file_cells(path, stat.st_size, stat.st_mtime_ns, entries)


def test_searches_chinese_and_mixed_fragments(tmp_path: Path) -> None:
    database = IndexDatabase(tmp_path / "index.db")
    database.initialize()
    workbook = tmp_path / "物料清单.xlsx"
    _index(
        database,
        workbook,
        [
            _entry(2, "美式排插 四孔长方形 0.9M 带开关 白色 墨西哥"),
            _entry(3, "美式排插 六孔长方形 1.5M", "TYPE-C 墨西哥许可"),
        ],
    )

    chinese = database.search("四孔长方形")
    assert len(chinese) == 1
    assert chinese[0].cell_reference == "C2 / D2"
    assert chinese[0].value_a == "HZ015"

    mixed = database.search("0.9m 墨西哥")
    assert [result.row_number for result in mixed] == [2]

    d_column = database.search("type-c")
    assert [result.row_number for result in d_column] == [3]
    assert d_column[0].value_d == "TYPE-C 墨西哥许可"

    cross_column = database.search("六孔 墨西哥")
    assert [result.row_number for result in cross_column] == [3]

    a_b_columns = database.search("hz015 B3 type-c")
    assert [result.row_number for result in a_b_columns] == [3]


def test_replacing_a_file_removes_stale_results(tmp_path: Path) -> None:
    database = IndexDatabase(tmp_path / "index.db")
    database.initialize()
    workbook = tmp_path / "replace.xlsx"
    _index(database, workbook, [_entry(2, "旧内容")])
    _index(database, workbook, [_entry(2, "新内容")])

    assert database.search("旧内容") == []
    assert len(database.search("新内容")) == 1


def test_short_queries_fall_back_to_substring_search(tmp_path: Path) -> None:
    database = IndexDatabase(tmp_path / "index.db")
    database.initialize()
    workbook = tmp_path / "short.xlsx"
    _index(database, workbook, [_entry(8, "USB C 接口")])

    assert [result.row_number for result in database.search("C")] == [8]


def test_schema_v1_is_migrated_and_existing_files_become_stale(tmp_path: Path) -> None:
    database_path = tmp_path / "old-index.db"
    with closing(sqlite3.connect(database_path)) as connection:
        connection.executescript(
            """
            CREATE TABLE files (
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
            CREATE TABLE cells (
                id INTEGER PRIMARY KEY,
                file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
                sheet TEXT NOT NULL,
                row_number INTEGER NOT NULL,
                cell_reference TEXT NOT NULL,
                value_a TEXT NOT NULL DEFAULT '',
                value_b TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                normalized TEXT NOT NULL
            );
            INSERT INTO files(file_key, path, name, status)
            VALUES('old', 'old.xlsx', 'old.xlsx', 'ready');
            """
        )
        connection.commit()

    database = IndexDatabase(database_path)
    database.initialize()

    with database.session() as connection:
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(cells)").fetchall()
        }
        status = connection.execute("SELECT status FROM files").fetchone()["status"]
    assert "value_d" in columns
    assert status == "stale"
    assert database.has_stale_files()


def test_schema_v2_files_become_stale_for_a_b_search_upgrade(tmp_path: Path) -> None:
    database = IndexDatabase(tmp_path / "v2-index.db")
    database.initialize()
    _index(database, tmp_path / "old-v2.xlsx", [_entry(2, "旧版索引")])
    with database.session() as connection:
        connection.execute(
            "UPDATE meta SET value='2' WHERE key='schema_version'"
        )

    database.initialize()

    assert database.has_stale_files()
    assert database.stats().ready_files == 0
