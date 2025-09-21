from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any, Iterable, Literal, TypedDict


_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


# Minimal multilingual stopwords (en/de), can be extended safely
_STOPWORDS = {
    # English
    "the","a","an","and","or","but","if","then","with","to","of","in","on","for","is","are","was","were","it","as","at","by","be","this","that","these","those","from","into","about","over","under","after","before","not","no","so","we","you","i","they","he","she","them","him","her","my","your","our","their",
    # German
    "der","die","das","ein","eine","einer","eines","und","oder","aber","wenn","dann","mit","zu","von","im","in","am","als","auf","ist","sind","war","waren","es","wie","bei","durch","für","aus","den","dem","des","nicht","kein","so","wir","ihr","sie","ich","du","euch","uns","einen","einem","einer","eines","einig","auch","heute","morgen",
}


class SimpleChunk(TypedDict, total=False):
    id: int
    text: str
    meta: dict[str, Any]
    dup_of: int


def _sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    # Robust sentence split: fallback to newline/period split
    sents = re.split(r"(?<=[.!?])\s+|\n+", text)
    sents = [s.strip() for s in sents if s.strip()]
    return sents


def _tokens(text: str) -> list[str]:
    # Keep letters and numbers, lowercase
    # Simplified pattern to avoid regex property support issues on Windows Python
    toks = re.findall(r"[A-Za-zÄÖÜäöüß0-9]+", text.lower())
    return toks


def _idf_from_sentences(sent_tokens: list[list[str]]) -> dict[str, float]:
    N = max(1, len(sent_tokens))
    df: Counter[str] = Counter()
    for toks in sent_tokens:
        df.update(set(t for t in toks if t not in _STOPWORDS))
    idf: dict[str, float] = {}
    for term, d in df.items():
        idf[term] = math.log(1 + (N / (1 + d)))
    return idf


def summary(text: str, max_sents: int = 3) -> list[str]:
    sents = _sentences(text)
    if not sents:
        return []
    sent_tokens = [_tokens(s) for s in sents]
    idf = _idf_from_sentences(sent_tokens)
    scores: list[float] = []
    N = len(sents)
    for idx, toks in enumerate(sent_tokens):
        tf = Counter(t for t in toks if t not in _STOPWORDS)
        tfidf = sum(tf[t] * idf.get(t, 0.0) for t in tf)
        # Position bonus: earlier sentences get a slight boost
        pos_bonus = 1.0 + 0.25 * (1.0 - (idx / max(1, N - 1))) if N > 1 else 1.0
        scores.append(tfidf * pos_bonus)
    # Always include the first sentence if possible, then fill remainder by ranking
    k = max(0, min(max_sents, N))
    if k == 0:
        return []
    chosen = {0}
    if k > 1:
        rest = sorted(range(1, N), key=lambda i: (-scores[i], i))[: k - 1]
        chosen.update(rest)
    return [sents[i] for i in range(N) if i in chosen]


def keywords(text: str, k: int = 8) -> list[str]:
    sents = _sentences(text)
    if not sents:
        return []
    sent_tokens = [_tokens(s) for s in sents]
    idf = _idf_from_sentences(sent_tokens)
    tf_total: Counter[str] = Counter()
    for toks in sent_tokens:
        tf_total.update(t for t in toks if t not in _STOPWORDS)
    scores: dict[str, float] = {}
    for term, tf in tf_total.items():
        scores[term] = tf * idf.get(term, 0.0)
    top = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
    return [t for t, _ in top]


def _cosine(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[t] * b.get(t, 0) for t in a)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def dedupe(chunks: list[SimpleChunk], threshold: float = 0.9) -> list[SimpleChunk]:
    # Mark duplicates by adding dup_of to later items matching earlier ones
    bow = []
    for ch in chunks:
        toks = _tokens(ch.get("text", ""))
        bow.append(Counter(t for t in toks if t not in _STOPWORDS))
    masters: list[int] = []
    out: list[SimpleChunk] = []
    for i, ch in enumerate(chunks):
        dup_of: int | None = None
        for j in masters:
            if _cosine(bow[i], bow[j]) >= threshold:
                # mark as duplicate of earliest master
                base_id = chunks[j].get("id") if chunks[j].get("id") is not None else j
                dup_of = int(base_id)
                break
        cp: SimpleChunk = {"id": ch.get("id", i), "text": ch.get("text", "")}
        if ch.get("meta") is not None:
            cp["meta"] = dict(ch.get("meta", {}))
        if dup_of is None:
            masters.append(i)
        else:
            cp["dup_of"] = dup_of
            # also mark in meta for visibility
            m = cp.setdefault("meta", {})
            m["dup_of"] = dup_of
        out.append(cp)
    return out


def game_next(state: dict[str, Any]) -> dict[str, Any]:
    # Simple suggestion engine: if state has choices list, suggest the first
    choices = state.get("choices") or []
    if isinstance(choices, list) and choices:
        state = dict(state)
        state["suggested_next"] = choices[0]
    return state
