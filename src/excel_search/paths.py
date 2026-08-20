from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "ExcelSearch"


def app_data_directory() -> Path:
    override = os.environ.get("EXCELSEARCH_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / APP_NAME


def default_database_path() -> Path:
    return app_data_directory() / "index.db"


def canonical_file_key(path: Path) -> str:
    resolved = str(path.expanduser().resolve(strict=False))
    return resolved.casefold() if sys.platform == "win32" else resolved
