from pathlib import Path

from openpyxl import Workbook

from excel_search.database import IndexDatabase
from excel_search.indexer import IndexService, collect_excel_files


def _make_workbook(path: Path) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "物料"
    worksheet.append(["工厂代码", "物料编号", "物料名称", "其他列"])
    worksheet.append(["HZ015", "B20103S16", "美式排插 四孔长方形 0.9M", "不应被搜索"])
    worksheet.append(["HZ021", "B20102S2E", "美式转换插座", "忽略内容"])
    workbook.save(path)


def test_indexes_only_a_b_c_context_and_content(tmp_path: Path) -> None:
    workbook_path = tmp_path / "示例.xlsx"
    _make_workbook(workbook_path)
    database = IndexDatabase(tmp_path / "index.db")
    database.initialize()

    summary = IndexService(database).index([workbook_path], register_sources=True)

    assert summary.indexed == 1
    assert summary.cells == 3  # header plus two non-empty C cells
    result = database.search("四孔长方形")[0]
    assert result.value_a == "HZ015"
    assert result.value_b == "B20103S16"
    assert result.cell_reference == "C2"
    assert database.search("不应被搜索") == []
    assert database.stats().source_count == 1


def test_folder_scan_ignores_excel_temporary_files(tmp_path: Path) -> None:
    real = tmp_path / "real.xlsx"
    temporary = tmp_path / "~$real.xlsx"
    unsupported = tmp_path / "notes.csv"
    for path in (real, temporary, unsupported):
        path.touch()

    assert collect_excel_files([tmp_path]) == (real,)
