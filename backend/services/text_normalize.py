from __future__ import annotations

import re
import unicodedata

from opencc import OpenCC

_TRADITIONAL_CONVERTER = OpenCC("s2t")


def normalize_text(value: str) -> str:
    """Normalize user-provided/searchable text without changing its language."""
    normalized = unicodedata.normalize("NFKC", value)
    return re.sub(r"\s+", " ", normalized).strip()


def to_traditional(value: str) -> str:
    """Convert Simplified Chinese text to Traditional Chinese."""
    return _TRADITIONAL_CONVERTER.convert(value)
