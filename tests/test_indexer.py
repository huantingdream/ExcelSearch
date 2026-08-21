import threading
import time
from pathlib import Path

from openpyxl import Workbook

import excel_search.indexer as indexer_module
from excel_search.database import IndexDatabase
from excel_search.indexer import IndexService, collect_excel_files
from excel_search.models import CellEntry
from excel_search.text import normalize_text


def _make_workbook(path: Path) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "物料"
    worksheet.append(["工厂代码", "物料编号", "物料名称", "补充说明", "其他列"])
    worksheet.append(
        ["HZ015", "B20103S16", "美式排插 四孔长方形 0.9M", "D列墨西哥说明", "不应被搜索"]
    )
    worksheet.append(["HZ021", "B20102S2E", "美式转换插座", "D列许可内容", "忽略内容"])
    worksheet.append(["HZ022", "B20102S2F", None, "仅D列关键词", "忽略内容"])
    workbook.save(path)


def test_indexes_and_searches_a_through_d_content(tmp_path: Path) -> None:
    workbook_path = tmp_path / "示例.xlsx"
    _make_workbook(workbook_path)
    database = IndexDatabase(tmp_path / "index.db")
    database.initialize()

    summary = IndexService(database).index([workbook_path], register_sources=True)

    assert summary.indexed == 1
    assert summary.cells == 4  # header plus three rows with A-D content
    result = database.search("四孔长方形")[0]
    assert result.value_a == "HZ015"
    assert result.value_b == "B20103S16"
    assert result.cell_reference == "C2 / D2"
    assert result.value_d == "D列墨西哥说明"
    assert database.search("HZ015")[0].row_number == 2
    assert database.search("B20102S2E D列许可内容")[0].row_number == 3
    assert database.search("D列许可内容")[0].row_number == 3
    assert database.search("仅D列关键词")[0].row_number == 4
    assert database.search("不应被搜索") == []
    assert database.stats().source_count == 1


def test_folder_scan_ignores_excel_temporary_files(tmp_path: Path) -> None:
    real = tmp_path / "real.xlsx"
    temporary = tmp_path / "~$real.xlsx"
    unsupported = tmp_path / "notes.csv"
    for path in (real, temporary, unsupported):
        path.touch()

    assert collect_excel_files([tmp_path]) == (real,)


def test_multiple_workbooks_are_read_on_multiple_threads(
    tmp_path: Path, monkeypatch
) -> None:
    workbook_paths = [tmp_path / f"book-{number}.xlsx" for number in range(4)]
    for path in workbook_paths:
        path.touch()

    thread_ids: set[int] = set()
    thread_lock = threading.Lock()

    def fake_reader(path: Path):
        with thread_lock:
            thread_ids.add(threading.get_ident())
        time.sleep(0.05)
        value = path.stem
        return iter(
            [
                CellEntry(
                    sheet="Sheet1",
                    row_number=1,
                    value_a=value,
                    value_b="",
                    content="",
                    value_d="",
                    normalized=normalize_text(value),
                )
            ]
        )

    monkeypatch.setattr(indexer_module, "iter_searchable_cells", fake_reader)
    database = IndexDatabase(tmp_path / "parallel.db")
    database.initialize()

    summary = IndexService(database).index(workbook_paths)

    assert summary.indexed == 4
    assert len(thread_ids) >= 2
