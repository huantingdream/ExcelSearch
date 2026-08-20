from pathlib import Path

from excel_search.database import IndexDatabase
from excel_search.models import CellEntry
from excel_search.text import normalize_text


def _entry(row: int, content: str) -> CellEntry:
    return CellEntry(
        sheet="物料表",
        row_number=row,
        value_a="HZ015",
        value_b=f"B{row}",
        content=content,
        normalized=normalize_text(content),
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
            _entry(3, "美式排插 六孔长方形 1.5M TYPE-C"),
        ],
    )

    chinese = database.search("四孔长方形")
    assert len(chinese) == 1
    assert chinese[0].cell_reference == "C2"
    assert chinese[0].value_a == "HZ015"

    mixed = database.search("0.9m 墨西哥")
    assert [result.row_number for result in mixed] == [2]

    assert [result.row_number for result in database.search("type-c")] == [3]


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
