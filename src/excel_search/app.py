from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QRectF, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QGuiApplication,
    QPainter,
    QTextDocument,
    QTextOption,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .database import IndexDatabase
from .indexer import IndexService
from .models import IndexSummary, SearchResult
from .system_actions import open_file, reveal_file
from .text import query_terms


class IndexWorker(QObject):
    progress = Signal(int, int, str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        database_path: Path,
        inputs: tuple[Path, ...],
        force: bool,
        register_sources: bool,
    ):
        super().__init__()
        self.database_path = database_path
        self.inputs = inputs
        self.force = force
        self.register_sources = register_sources

    @Slot()
    def run(self) -> None:
        try:
            database = IndexDatabase(self.database_path)
            database.initialize()
            summary = IndexService(database).index(
                self.inputs,
                force=self.force,
                register_sources=self.register_sources,
                progress=lambda current, total, name: self.progress.emit(
                    current, total, name
                ),
            )
            self.completed.emit(summary)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class HighlightDelegate(QStyledItemDelegate):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._terms: tuple[str, ...] = ()

    def set_query(self, query: str) -> None:
        self._terms = tuple(query.split())

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        options = QStyleOptionViewItem(option)
        self.initStyleOption(options, index)
        style = options.widget.style() if options.widget else None
        if style:
            style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, options, painter)

        document = QTextDocument()
        document.setDefaultFont(options.font)
        document.setDocumentMargin(0)
        text_option = document.defaultTextOption()
        text_option.setWrapMode(QTextOption.WrapMode.NoWrap)
        document.setDefaultTextOption(text_option)
        document.setHtml(self._highlight_html(str(index.data() or "")))
        document.setTextWidth(-1)

        painter.save()
        vertical_offset = max(0.0, (options.rect.height() - document.size().height()) / 2)
        painter.translate(options.rect.left() + 6, options.rect.top() + vertical_offset)
        clip = QRectF(0, 0, options.rect.width() - 12, options.rect.height())
        document.drawContents(painter, clip)
        painter.restore()

    def _highlight_html(self, value: str) -> str:
        if not self._terms:
            return html.escape(value)
        pattern = re.compile(
            "|".join(re.escape(term) for term in sorted(self._terms, key=len, reverse=True)),
            re.IGNORECASE,
        )
        pieces: list[str] = []
        position = 0
        for match in pattern.finditer(value):
            pieces.append(html.escape(value[position : match.start()]))
            pieces.append(
                "<span style='background-color:#FFE08A;color:#1F2937;'>"
                f"{html.escape(match.group(0))}</span>"
            )
            position = match.end()
        pieces.append(html.escape(value[position:]))
        return "".join(pieces)

    def sizeHint(self, option: QStyleOptionViewItem, index):
        size = super().sizeHint(option, index)
        size.setHeight(max(size.height(), 38))
        return size


class MainWindow(QMainWindow):
    def __init__(self, database: IndexDatabase):
        super().__init__()
        self.database = database
        self._thread: QThread | None = None
        self._worker: IndexWorker | None = None
        self._results: list[SearchResult] = []
        self._highlight_delegate = HighlightDelegate(self)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(220)
        self._search_timer.timeout.connect(self.search)

        self.setWindowTitle("ExcelSearch - Excel 内容搜索")
        self.resize(1280, 760)
        self.setMinimumSize(920, 580)
        self._build_ui()
        self._apply_style()
        self.refresh_stats()
        if self.database.has_stale_files():
            QTimer.singleShot(0, self.refresh_index)

    def _build_ui(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)

        title = QLabel("Excel 内容搜索")
        title.setObjectName("title")
        subtitle = QLabel("搜索工作表 A、B、C、D 四列文字；图片不会被索引。")
        subtitle.setObjectName("subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.add_files_button = QPushButton("添加 Excel 文件")
        self.add_folder_button = QPushButton("添加文件夹")
        self.refresh_button = QPushButton("刷新索引")
        self.clear_button = QPushButton("清空索引")
        self.add_files_button.clicked.connect(self.add_files)
        self.add_folder_button.clicked.connect(self.add_folder)
        self.refresh_button.clicked.connect(self.refresh_index)
        self.clear_button.clicked.connect(self.clear_index)
        action_row.addWidget(self.add_files_button)
        action_row.addWidget(self.add_folder_button)
        action_row.addWidget(self.refresh_button)
        action_row.addWidget(self.clear_button)
        action_row.addStretch()
        layout.addLayout(action_row)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "输入 A–D 任一列关键词，例如：HZ015  B20103S16  四孔长方形  墨西哥"
        )
        self.search_input.setClearButtonEnabled(True)
        self.search_input.returnPressed.connect(self.search)
        self.search_input.textChanged.connect(lambda: self._search_timer.start())
        layout.addWidget(self.search_input)

        self.status_label = QLabel()
        self.status_label.setObjectName("status")
        layout.addWidget(self.status_label)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                "文件",
                "工作表",
                "位置",
                "工厂代码（A）",
                "物料编号（B）",
                "物料名称（C）",
                "D 列内容",
                "修改时间",
                "完整路径",
            ]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_result_menu)
        self.table.cellDoubleClicked.connect(lambda row, _column: self.open_result(row))
        self.table.setItemDelegateForColumn(3, self._highlight_delegate)
        self.table.setItemDelegateForColumn(4, self._highlight_delegate)
        self.table.setItemDelegateForColumn(5, self._highlight_delegate)
        self.table.setItemDelegateForColumn(6, self._highlight_delegate)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.table.setColumnWidth(0, 180)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 120)
        self.table.setColumnWidth(4, 140)
        self.table.setColumnWidth(5, 340)
        self.table.setColumnWidth(6, 220)
        layout.addWidget(self.table, 1)

        hint = QLabel("提示：双击结果可打开原始 Excel；右键可以在文件管理器中显示或复制路径。")
        hint.setObjectName("hint")
        layout.addWidget(hint)
        self.setCentralWidget(central)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #F5F7FA; color: #1F2937; }
            QWidget { font-family: "Segoe UI", "Microsoft YaHei UI", "PingFang SC"; font-size: 13px; }
            QLabel#title { font-size: 25px; font-weight: 700; color: #123B65; }
            QLabel#subtitle, QLabel#hint { color: #607086; }
            QLabel#status { color: #315C86; font-weight: 600; padding: 2px 0; }
            QPushButton {
                background: #FFFFFF; border: 1px solid #C9D4E1; border-radius: 6px;
                padding: 8px 14px; min-height: 20px;
            }
            QPushButton:hover { border-color: #2474C5; color: #145DA0; }
            QPushButton:pressed { background: #E9F2FB; }
            QPushButton:disabled { color: #9AA7B5; background: #EEF1F4; }
            QLineEdit {
                background: #FFFFFF; border: 2px solid #B9C8D8; border-radius: 8px;
                padding: 10px 12px; font-size: 15px; selection-background-color: #2474C5;
            }
            QLineEdit:focus { border-color: #2474C5; }
            QTableWidget {
                background: #FFFFFF; alternate-background-color: #F7FAFD;
                border: 1px solid #D6DEE8; border-radius: 7px; gridline-color: #E4EAF0;
                selection-background-color: #D9EAFB; selection-color: #172B3F;
            }
            QHeaderView::section {
                background: #E8F0F8; color: #264967; border: none;
                border-right: 1px solid #D5DFE8; border-bottom: 1px solid #CAD6E1;
                padding: 9px 7px; font-weight: 600;
            }
            QMenu { background: #FFFFFF; border: 1px solid #C9D4E1; padding: 5px; }
            QMenu::item { padding: 7px 24px; }
            QMenu::item:selected { background: #D9EAFB; }
            """
        )

    @Slot()
    def add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择 Excel 文件",
            "",
            "Excel 文件 (*.xlsx *.xlsm *.xls)",
        )
        if paths:
            self._start_index(tuple(Path(path) for path in paths), register_sources=True)

    @Slot()
    def add_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择包含 Excel 的文件夹")
        if path:
            self._start_index((Path(path),), register_sources=True)

    @Slot()
    def refresh_index(self) -> None:
        sources = self.database.list_sources()
        if not sources:
            QMessageBox.information(self, "尚未添加文件", "请先添加 Excel 文件或文件夹。")
            return
        self._start_index(sources, register_sources=False)

    @Slot()
    def clear_index(self) -> None:
        answer = QMessageBox.question(
            self,
            "清空索引",
            "确定清空所有搜索索引吗？\n\n原始 Excel 文件不会被删除。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.database.clear_index()
            self._results.clear()
            self.table.setRowCount(0)
            self.refresh_stats()

    def _start_index(self, paths: tuple[Path, ...], register_sources: bool) -> None:
        if self._thread and self._thread.isRunning():
            return
        self._set_busy(True)
        self.status_label.setText("正在准备索引…")
        thread = QThread(self)
        worker = IndexWorker(
            self.database.path,
            paths,
            force=False,
            register_sources=register_sources,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress)
        worker.completed.connect(self._on_index_completed)
        worker.failed.connect(self._on_index_failed)
        worker.completed.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.completed.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(self._on_thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        thread.start()

    @Slot(int, int, str)
    def _on_progress(self, current: int, total: int, name: str) -> None:
        self.status_label.setText(f"正在建立索引：{current}/{total}  {name}")

    @Slot(object)
    def _on_index_completed(self, summary: IndexSummary) -> None:
        self._set_busy(False)
        self.refresh_stats()
        self.search()
        if summary.failed:
            failures = [item for item in summary.outcomes if item.status == "failed"]
            details = "\n".join(
                f"• {item.file_path.name}：{item.error}" for item in failures[:8]
            )
            if len(failures) > 8:
                details += f"\n…另有 {len(failures) - 8} 个文件"
            QMessageBox.warning(
                self,
                "部分文件未能索引",
                f"成功更新 {summary.indexed} 个文件，失败 {summary.failed} 个。\n\n{details}",
            )
        elif summary.indexed == 0 and summary.skipped == 0:
            QMessageBox.information(
                self,
                "没有找到 Excel",
                "所选位置中没有找到 .xlsx、.xlsm 或 .xls 文件。",
            )

    @Slot(str)
    def _on_index_failed(self, message: str) -> None:
        self._set_busy(False)
        self.refresh_stats()
        QMessageBox.critical(self, "索引失败", message)

    @Slot()
    def _on_thread_finished(self) -> None:
        self._thread = None
        self._worker = None

    def _set_busy(self, busy: bool) -> None:
        for button in (
            self.add_files_button,
            self.add_folder_button,
            self.refresh_button,
            self.clear_button,
        ):
            button.setDisabled(busy)

    @Slot()
    def search(self) -> None:
        query = self.search_input.text().strip()
        self._highlight_delegate.set_query(query)
        if not query:
            self._results = []
            self.table.setRowCount(0)
            self.refresh_stats()
            return
        try:
            self._results = self.database.search(query)
        except Exception as exc:
            self.status_label.setText(f"搜索失败：{exc}")
            return
        self._populate_results(self._results)
        terms = query_terms(query)
        self.status_label.setText(
            f"找到 {len(self._results)} 条结果；关键词按“全部包含”匹配：{' + '.join(terms)}"
        )

    def _populate_results(self, results: list[SearchResult]) -> None:
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(len(results))
            for row, result in enumerate(results):
                values = (
                    result.file_name,
                    result.sheet,
                    result.cell_reference,
                    result.value_a,
                    result.value_b,
                    result.content,
                    result.value_d,
                    format_modified_time(result.modified_ns),
                    str(result.file_path),
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setToolTip(value)
                    if column == 0:
                        item.setData(Qt.ItemDataRole.UserRole, str(result.file_path))
                    self.table.setItem(row, column, item)
        finally:
            self.table.setUpdatesEnabled(True)
            self.table.viewport().update()

    @Slot(int)
    def open_result(self, row: int) -> None:
        path = self._path_for_row(row)
        if not path:
            return
        if not path.is_file():
            QMessageBox.warning(self, "文件不存在", "该文件已被移动或删除，请刷新索引。")
            return
        if not open_file(path):
            QMessageBox.warning(self, "无法打开文件", f"系统无法打开：\n{path}")

    @Slot(object)
    def show_result_menu(self, position) -> None:
        row = self.table.rowAt(position.y())
        path = self._path_for_row(row)
        if not path:
            return
        menu = QMenu(self)
        open_action = QAction("打开 Excel", self)
        reveal_action = QAction("在文件管理器中显示", self)
        copy_action = QAction("复制文件路径", self)
        open_action.triggered.connect(lambda: self.open_result(row))
        reveal_action.triggered.connect(lambda: reveal_file(path))
        copy_action.triggered.connect(lambda: QGuiApplication.clipboard().setText(str(path)))
        menu.addAction(open_action)
        menu.addAction(reveal_action)
        menu.addSeparator()
        menu.addAction(copy_action)
        menu.exec(self.table.viewport().mapToGlobal(position))

    def _path_for_row(self, row: int) -> Path | None:
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if not item:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return Path(value) if value else None

    def refresh_stats(self) -> None:
        stats = self.database.stats()
        status = f"已索引 {stats.ready_files} 个文件、{stats.cell_count} 条 A–D 列内容"
        if stats.failed_files:
            status += f"；{stats.failed_files} 个文件需要处理"
        self.status_label.setText(status)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._thread and self._thread.isRunning():
            QMessageBox.information(self, "正在建立索引", "请等待当前索引任务完成后再关闭程序。")
            event.ignore()
            return
        super().closeEvent(event)


def format_modified_time(modified_ns: int) -> str:
    return datetime.fromtimestamp(modified_ns / 1_000_000_000).strftime("%Y-%m-%d %H:%M")
