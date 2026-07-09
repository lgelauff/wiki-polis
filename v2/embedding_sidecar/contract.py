from __future__ import annotations

import math

MAX_TEXTS = 32
MAX_TEXT_CHARS = 2000


def validate_text(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("text must be a string")
    text = value.strip()
    if not text:
        raise ValueError("text must not be empty")
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError(f"text must be at most {MAX_TEXT_CHARS} characters")
    return text


def validate_texts(values: list[str]) -> list[str]:
    if not isinstance(values, list):
        raise ValueError("texts must be a list")
    if not values:
        raise ValueError("texts must not be empty")
    if len(values) > MAX_TEXTS:
        raise ValueError(f"texts must contain at most {MAX_TEXTS} items")
    return [validate_text(value) for value in values]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding dimensions must match")
    if not left:
        raise ValueError("embeddings must not be empty")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        raise ValueError("embeddings must not be zero vectors")
    return dot / (left_norm * right_norm)
