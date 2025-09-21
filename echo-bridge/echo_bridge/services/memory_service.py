from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

from ..db import get_conn


class Chunk(BaseModel):
    id: int
    source: str
    title: Optional[str]
    text: str
    meta: dict[str, Any] | None = None


class Hit(BaseModel):
    id: int
    score: float
    snippet: str
    source: str | None = None
    title: str | None = None


def add_chunks(source: str, title: str | None, texts: list[str], meta: dict[str, Any] | None) -> int:
    if not texts:
        return 0
    conn = get_conn()
    cur = conn.cursor()
    count = 0
    meta_json = None
    if meta is not None:
        import json

        meta_json = json.dumps(meta, ensure_ascii=False)
    for t in texts:
        cur.execute(
            "INSERT INTO chunks(doc_source, doc_title, text, meta_json) VALUES (?,?,?,?)",
            (source, title, t, meta_json),
        )
        count += 1
    conn.commit()
    return count


def search(q: str, k: int = 5) -> list[Hit]:
    conn = get_conn()
    cur = conn.cursor()
    # Using bm25 for ranking and snippet for highlights
    cur.execute(
        """
        SELECT c.id as id,
               0.0 AS score,
               snippet(chunks_fts, 0, '[', ']', ' … ', 10) AS snip,
               c.doc_source as source,
               c.doc_title as title
        FROM chunks_fts
        JOIN chunks c ON c.id = chunks_fts.rowid
        WHERE chunks_fts MATCH ?
        ORDER BY rank LIMIT ?
        """,
        (q, k),
    )
    rows = cur.fetchall()
    hits = [Hit(id=row["id"], score=row["score"], snippet=row["snip"], source=row["source"], title=row["title"]) for row in rows]
    return hits


def get_chunk(id: int) -> Chunk | None:
    import json

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, doc_source, doc_title, text, meta_json FROM chunks WHERE id=?",
        (id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    meta = json.loads(row["meta_json"]) if row["meta_json"] else None
    return Chunk(id=row["id"], source=row["doc_source"], title=row["doc_title"], text=row["text"], meta=meta)
