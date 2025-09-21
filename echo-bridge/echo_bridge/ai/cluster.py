from __future__ import annotations

import math
import random
from typing import Dict, List, Tuple

from .embedder import embed


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _closest(centroids: list[list[float]], v: list[float]) -> int:
    best = 0
    best_score = -1.0
    for i, c in enumerate(centroids):
        s = _cosine(c, v)
        if s > best_score:
            best_score = s
            best = i
    return best


def kmeans_texts(chunks: dict[int, str], k: int = 3, iters: int = 10, seed: int = 42) -> dict[int, int]:
    ids = list(chunks.keys())
    vecs = {cid: embed(chunks[cid]) for cid in ids}
    random.seed(seed)
    init_ids = random.sample(ids, min(k, len(ids)))
    centroids = [vecs[i][:] for i in init_ids]
    if len(centroids) < k:
        # pad duplicates if not enough
        centroids += [centroids[0][:] for _ in range(k - len(centroids))]
    labels: dict[int, int] = {cid: i % k for i, cid in enumerate(ids)}
    for _ in range(max(1, iters)):
        # Assign
        for cid, v in vecs.items():
            labels[cid] = _closest(centroids, v)
        # Update
        sums = [[0.0] * len(centroids[0]) for _ in range(k)]
        counts = [0] * k
        for cid, lab in labels.items():
            v = vecs[cid]
            counts[lab] += 1
            for j in range(len(v)):
                sums[lab][j] += v[j]
        for i in range(k):
            if counts[i] == 0:
                continue
            centroids[i] = [x / counts[i] for x in sums[i]]
        # Re-normalize to unit length for cosine
        for i in range(k):
            norm = math.sqrt(sum(x * x for x in centroids[i])) or 1.0
            centroids[i] = [x / norm for x in centroids[i]]
    return labels
