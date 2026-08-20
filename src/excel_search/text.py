from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, time
from decimal import Decimal


_WHITESPACE = re.compile(r"\s+")


def display_value(value: object) -> str:
    """Convert an Excel value into stable, readable text."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value).strip()


def normalize_text(value: str) -> str:
    """Normalize Unicode, case, and whitespace for cross-platform searching."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return _WHITESPACE.sub(" ", normalized).strip()


def query_terms(query: str) -> tuple[str, ...]:
    """Split a query into de-duplicated AND terms."""
    normalized = normalize_text(query)
    if not normalized:
        return ()
    return tuple(dict.fromkeys(term for term in normalized.split(" ") if term))
