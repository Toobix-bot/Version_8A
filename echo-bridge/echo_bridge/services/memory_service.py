from __future__ import annotations

from typing import Any, Optional
import re
import sqlite3

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
        rowid = cur.lastrowid
        count += 1
        # if meta contains tags, persist them
        if meta and isinstance(meta.get("tags"), (list, tuple)):
            tags = meta.get("tags")
            for tag in tags:
                # insert or ignore tag
                cur.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (tag,))
                # get tag id
                cur.execute("SELECT id FROM tags WHERE name=?", (tag,))
                tr = cur.fetchone()
                if tr:
                    tag_id = tr[0]
                    cur.execute(
                        "INSERT OR IGNORE INTO chunk_tags(chunk_id, tag_id) VALUES (?,?)",
                        (rowid, tag_id),
                    )
    conn.commit()
    return count


def get_tags_for_chunk(chunk_id: int) -> list[str]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT t.name FROM tags t JOIN chunk_tags ct ON ct.tag_id=t.id WHERE ct.chunk_id=?",
        (chunk_id,),
    )
    return [r[0] for r in cur.fetchall()]


def _sanitize_query(q: str) -> str:
    # Keep only alphanumerics (incl. basic German letters); drop special syntax like ':' that can break FTS MATCH
    toks = re.findall(r"[A-Za-zÄÖÜäöüß0-9]+", q)
    return " ".join(toks[:32])  # cap tokens for safety


def search(q: str, k: int = 5) -> list[Hit]:
    conn = get_conn()
    cur = conn.cursor()
    sanitized = _sanitize_query(q or "")
    if not sanitized:
        return []
    try:
        # Using rank and snippet for highlights; sanitized query avoids FTS parser errors
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
            (sanitized, k),
        )
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        # In case of unexpected syntax, fall back to empty
        return []
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
