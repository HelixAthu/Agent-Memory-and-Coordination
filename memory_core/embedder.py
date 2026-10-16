"""Tokenizer, stemmer, mock hashing embedder, and cosine similarity calculations."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any

STOPWORDS: set[str] = {
    "a", "an", "the", "on", "in", "of", "to", "for", "my", "i", "me", "is", "was",
    "it", "and", "or", "about", "with", "by", "at", "as", "be", "are", "were",
    "this", "that", "her", "his", "she", "he", "you", "your", "we", "they",
    "their", "has", "have", "had", "from", "am",
}


def tokens(text: str) -> list[str]:
    """Tokenize text into lowercase alphanumeric tokens, stripping stopwords."""
    raw = re.split(r"[^a-zA-Z0-9]+", text.lower())
    return [t for t in raw if t and t not in STOPWORDS]


def stem(w: str) -> str:
    """Stem word using spec suffix stripping rules."""
    for suf in ("ing", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[:-len(suf)]
            break
    if w.endswith("e") and len(w) > 3:
        w = w[:-1]
    return w


def mock_embed(text: str, dim: int = 4096) -> list[float]:
    """Deterministic hashing embedder with L2 normalization."""
    t_list = tokens(text)
    if not t_list:
        return [0.0] * dim
    vec: list[float] = [0.0] * dim
    for t in t_list:
        s = stem(t)
        idx = int(hashlib.md5(s.encode("utf-8")).hexdigest(), 16) % dim
        vec[idx] += 1.0
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return [0.0] * dim
    return [x / norm for x in vec]


def cosine(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two float vectors, clamped to [0, 1]."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    val = dot / (na * nb)
    return max(0.0, min(1.0, float(val)))
