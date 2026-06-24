"""Deterministic + fuzzy entity / duplicate matching.

Deterministic rules are preferred where exact (idempotency keys); fuzzy matching handles
near-duplicate customer names.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]")
_SUFFIXES = {"ltd", "gmbh", "sas", "inc", "kk", "llc", "co", "corp"}


def normalize_name(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace, drop common company suffixes."""
    text = _PUNCT.sub(" ", name.lower())
    tokens = [t for t in _WS.sub(" ", text).strip().split(" ") if t and t not in _SUFFIXES]
    return " ".join(tokens)


def name_similarity(a: str, b: str) -> float:
    """Normalized similarity in [0, 1] between two entity names."""
    return SequenceMatcher(None, normalize_name(a), normalize_name(b)).ratio()


@dataclass
class DuplicateMatch:
    key: str
    ids: list[str]


def find_exact_duplicates(items: list[tuple[str, str]]) -> list[DuplicateMatch]:
    """Group ids that share an exact business key. ``items`` is (id, key)."""
    by_key: dict[str, list[str]] = {}
    for item_id, key in items:
        by_key.setdefault(key, []).append(item_id)
    return [DuplicateMatch(key=k, ids=sorted(v)) for k, v in by_key.items() if len(v) > 1]


def fuzzy_match(query: str, candidates: list[tuple[str, str]], threshold: float = 0.85
                ) -> list[tuple[str, float]]:
    """Return (id, score) for candidates whose name similarity to ``query`` >= threshold.

    ``candidates`` is (id, name). Sorted by descending score.
    """
    scored = [(cid, name_similarity(query, name)) for cid, name in candidates]
    matches = [(cid, score) for cid, score in scored if score >= threshold]
    return sorted(matches, key=lambda x: x[1], reverse=True)
