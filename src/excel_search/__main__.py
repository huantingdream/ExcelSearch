from __future__ import annotations

import ctypes
import multiprocessing
import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from excel_search.app import MainWindow
from excel_search.database import IndexDatabase
from excel_search.paths import default_database_path


def main() -> int:
    multiprocessing.freeze_support()
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "ExcelSearch.Desktop.0.3"
            )
        except Exception:
            pass

    application = QApplication(sys.argv)
    application.setApplicationName("ExcelSearch")
    application.setOrganizationName("ExcelSearch")

    database = IndexDatabase(default_database_path())
    try:
        database.initialize()
    except Exception as exc:
        QMessageBox.critical(
            None,
            "ExcelSearch 无法启动",
            f"无法创建本地索引数据库：\n{exc}",
        )
        return 1

    window = MainWindow(database)
    window.show()
    if os.environ.get("EXCELSEARCH_SMOKE_TEST") == "1":
        QTimer.singleShot(150, application.quit)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
