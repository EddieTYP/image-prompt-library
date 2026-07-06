from __future__ import annotations

from dataclasses import dataclass, field
import re


DATE_VALUES = {"today", "yesterday", "7d", "30d"}
HAS_VALUES = {"image", "result", "reference", "prompt"}
LIST_KEYS = {
    "tag": "tags",
    "collection": "collections",
    "model": "models",
    "source": "sources",
}
FAVORITE_KEYS = {"fav", "favorite"}
TOKEN_RE = re.compile(r"[^,\s]+")


@dataclass(frozen=True)
class ParsedItemSearchQuery:
    keyword: str = ""
    created: str | None = None
    updated: str | None = None
    tags: list[str] = field(default_factory=list)
    collections: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    favorite: bool | None = None
    archived: bool | None = None
    has: set[str] = field(default_factory=set)


def parse_item_search_query(query: str) -> ParsedItemSearchQuery:
    keyword_parts: list[str] = []
    created: str | None = None
    updated: str | None = None
    tags: list[str] = []
    collections: list[str] = []
    models: list[str] = []
    sources: list[str] = []
    favorite: bool | None = None
    archived: bool | None = None
    has_values: set[str] = set()

    list_values = {
        "tags": tags,
        "collections": collections,
        "models": models,
        "sources": sources,
    }

    for token in TOKEN_RE.findall(query):
        key, separator, value = token.partition(":")
        key = key.lower()
        value = value.lower()

        if separator != ":":
            keyword_parts.append(token)
        elif key == "created" and value in DATE_VALUES:
            created = value
        elif key == "updated" and value in DATE_VALUES:
            updated = value
        elif key in LIST_KEYS and value:
            values = list_values[LIST_KEYS[key]]
            if value not in values:
                values.append(value)
        elif key in FAVORITE_KEYS and value in {"true", "false"}:
            favorite = value == "true"
        elif key == "archived" and value in {"true", "false"}:
            archived = value == "true"
        elif key == "has" and value in HAS_VALUES:
            has_values.add(value)
        else:
            keyword_parts.append(token)

    return ParsedItemSearchQuery(
        keyword=" ".join(keyword_parts),
        created=created,
        updated=updated,
        tags=tags,
        collections=collections,
        models=models,
        sources=sources,
        favorite=favorite,
        archived=archived,
        has=has_values,
    )
