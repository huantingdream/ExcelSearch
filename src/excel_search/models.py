from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CellEntry:
    sheet: str
    row_number: int
    value_a: str
    value_b: str
    content: str
    value_d: str
    normalized: str

    @property
    def cell_reference(self) -> str:
        return f"C{self.row_number} / D{self.row_number}"


@dataclass(frozen=True, slots=True)
class SearchResult:
    file_path: Path
    file_name: str
    modified_ns: int
    sheet: str
    row_number: int
    cell_reference: str
    value_a: str
    value_b: str
    content: str
    value_d: str


@dataclass(frozen=True, slots=True)
class IndexOutcome:
    file_path: Path
    status: str
    cell_count: int = 0
    error: str = ""


@dataclass(frozen=True, slots=True)
class IndexSummary:
    indexed: int
    skipped: int
    failed: int
    cells: int
    outcomes: tuple[IndexOutcome, ...]


@dataclass(frozen=True, slots=True)
class IndexStats:
    ready_files: int
    failed_files: int
    cell_count: int
    source_count: int
