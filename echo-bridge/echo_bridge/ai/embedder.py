from __future__ import annotations

import hashlib
import math
from collections import Counter
from typing import Iterable, List, Tuple

from ..db import get_conn
from .reflexes import _tokens, _STOPWORDS


Dim = 256


def _hash_token(t: str) -> int:
    h = hashlib.sha1(t.encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big") % Dim


def embed(text: str) -> list[float] | None:
    toks = [t for t in _tokens(text) if t not in _STOPWORDS]
    if not toks:
        return [0.0] * Dim
    vec = [0.0] * Dim
    tf = Counter(toks)
    for term, count in tf.items():
        idx = _hash_token(term)
        vec[idx] += float(count)
    # L2 normalize
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _cosine_vec(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def similar(chunk_id: int, k: int = 5, threshold: float | None = None) -> list[tuple[int, float]]:
    """Return top-k most similar chunk ids with cosine score.

    Brute-force over all chunks in DB using normalized embeddings.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, text FROM chunks")
    rows = cur.fetchall()
    texts = {row["id"]: row["text"] for row in rows}
    if chunk_id not in texts:
        return []
    vecs: dict[int, list[float]] = {cid: embed(txt) for cid, txt in texts.items()}
    target = vecs[chunk_id]
    scores: list[tuple[int, float]] = []
    for cid, v in vecs.items():
        if cid == chunk_id:
            continue
        score = _cosine_vec(target, v)
        if threshold is None or score >= threshold:
            scores.append((cid, float(score)))
    scores.sort(key=lambda x: (-x[1], x[0]))
    return scores[:k]
