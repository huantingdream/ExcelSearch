from __future__ import annotations

import os
import pickle
import tempfile
from collections.abc import Callable, Iterable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import BinaryIO

from .database import IndexDatabase
from .models import CellEntry, IndexOutcome, IndexSummary
from .paths import canonical_file_key
from .readers import SUPPORTED_EXTENSIONS, iter_searchable_cells


ProgressCallback = Callable[[int, int, str], None]


def index_worker_count(file_count: int) -> int:
    if file_count <= 1:
        return max(0, file_count)
    configured = os.environ.get("EXCELSEARCH_INDEX_WORKERS", "").strip()
    if configured:
        try:
            return min(file_count, max(1, int(configured)))
        except ValueError:
            pass
    cpu_count = os.cpu_count() or 2
    return min(file_count, max(2, min(4, cpu_count)))


def _read_workbook(path: Path) -> BinaryIO:
    buffer = tempfile.TemporaryFile(mode="w+b")
    try:
        for entry in iter_searchable_cells(path):
            pickle.dump(entry, buffer, protocol=pickle.HIGHEST_PROTOCOL)
        buffer.seek(0)
        return buffer
    except Exception:
        buffer.close()
        raise


def _iter_buffered_entries(buffer: BinaryIO) -> Iterable[CellEntry]:
    while True:
        try:
            yield pickle.load(buffer)
        except EOFError:
            return


def collect_excel_files(inputs: Iterable[Path]) -> tuple[Path, ...]:
    found: dict[str, Path] = {}
    for raw_path in inputs:
        path = Path(raw_path).expanduser().resolve(strict=False)
        if path.is_file():
            _add_if_supported(found, path)
            continue
        if not path.is_dir():
            continue
        for root, _directories, files in os.walk(path):
            root_path = Path(root)
            for name in files:
                _add_if_supported(found, root_path / name)
    return tuple(sorted(found.values(), key=lambda item: str(item).casefold()))


def _add_if_supported(found: dict[str, Path], path: Path) -> None:
    if path.name.startswith("~$"):
        return
    if path.suffix.casefold() not in SUPPORTED_EXTENSIONS:
        return
    found[canonical_file_key(path)] = path


class IndexService:
    def __init__(self, database: IndexDatabase):
        self.database = database

    def index(
        self,
        inputs: Iterable[Path],
        *,
        force: bool = False,
        register_sources: bool = False,
        progress: ProgressCallback | None = None,
    ) -> IndexSummary:
        input_paths = tuple(Path(item).expanduser().resolve(strict=False) for item in inputs)
        if register_sources:
            for path in input_paths:
                kind = "file" if path.is_file() else "folder"
                self.database.add_source(path, kind)

        files = collect_excel_files(input_paths)
        outcomes: list[IndexOutcome] = []
        indexed = skipped = failed = cells = 0
        completed = 0
        pending: list[tuple[Path, int, int]] = []

        for file_path in files:
            try:
                stat = file_path.stat()
                if not force and self.database.file_is_current(
                    file_path, stat.st_size, stat.st_mtime_ns
                ):
                    skipped += 1
                    outcomes.append(IndexOutcome(file_path, "skipped"))
                    completed += 1
                    if progress:
                        progress(completed, len(files), file_path.name)
                else:
                    pending.append((file_path, stat.st_size, stat.st_mtime_ns))
            except Exception as exc:  # one bad workbook must not stop the batch
                message = _friendly_error(exc)
                self.database.record_error(file_path, message)
                failed += 1
                outcomes.append(IndexOutcome(file_path, "failed", error=message))
                completed += 1
                if progress:
                    progress(completed, len(files), file_path.name)

        worker_count = index_worker_count(len(pending))
        if worker_count:
            if progress:
                progress(completed, len(files), f"使用 {worker_count} 个线程并行读取 Excel")
            with ThreadPoolExecutor(
                max_workers=worker_count,
                thread_name_prefix="excel-index",
            ) as executor:
                futures: dict[Future[BinaryIO], tuple[Path, int, int]] = {
                    executor.submit(_read_workbook, path): (path, size, mtime_ns)
                    for path, size, mtime_ns in pending
                }
                for future in as_completed(futures):
                    file_path, size, mtime_ns = futures[future]
                    try:
                        buffer = future.result()
                        try:
                            cell_count = self.database.replace_file_cells(
                                file_path,
                                size,
                                mtime_ns,
                                _iter_buffered_entries(buffer),
                            )
                        finally:
                            buffer.close()
                        indexed += 1
                        cells += cell_count
                        outcomes.append(IndexOutcome(file_path, "indexed", cell_count))
                    except Exception as exc:  # one bad workbook must not stop the batch
                        message = _friendly_error(exc)
                        self.database.record_error(file_path, message)
                        failed += 1
                        outcomes.append(IndexOutcome(file_path, "failed", error=message))
                    completed += 1
                    if progress:
                        progress(completed, len(files), file_path.name)

        self.database.mark_missing_files()
        return IndexSummary(
            indexed=indexed,
            skipped=skipped,
            failed=failed,
            cells=cells,
            outcomes=tuple(outcomes),
        )


def _friendly_error(error: Exception) -> str:
    name = type(error).__name__
    message = str(error).strip()
    if "password" in message.casefold() or "encrypted" in message.casefold():
        return "文件已加密或受密码保护"
    if isinstance(error, PermissionError):
        return "没有权限读取文件，或文件正被其他程序独占"
    if isinstance(error, FileNotFoundError):
        return "文件不存在或已被移动"
    return f"{name}: {message}" if message else name
