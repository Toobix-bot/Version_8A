from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from sqlite3 import Row


_DB_PATH: Path | None = None


def get_conn() -> sqlite3.Connection:
    if _DB_PATH is None:
        raise RuntimeError("Database not initialized. Call init_db(path) first.")
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = Row
    return conn


def init_db(path: str | Path) -> None:
    global _DB_PATH
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    first_time = not db_path.exists()
    _DB_PATH = db_path

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = Row
    cur = conn.cursor()
    # Pragmas for WAL and safety
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA foreign_keys=ON;")
    cur.execute("PRAGMA synchronous=NORMAL;")

    # Core tables
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_source TEXT NOT NULL,
            doc_title TEXT,
            text TEXT NOT NULL,
            meta_json TEXT,
            ts DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            text, content='chunks', content_rowid='id'
        );

        CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
            INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
        END;
        CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
            INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
        END;
        CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
        END;

        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS chunk_tags (
            chunk_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY (chunk_id, tag_id),
            FOREIGN KEY (chunk_id) REFERENCES chunks(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            state_json TEXT NOT NULL,
            ts DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS audits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            result_json TEXT NOT NULL,
            soul_mood TEXT,
            ts DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_chunks_source_ts ON chunks(doc_source, ts DESC);
        CREATE INDEX IF NOT EXISTS idx_chunks_title ON chunks(doc_title);
        CREATE INDEX IF NOT EXISTS idx_chunk_tags_chunk ON chunk_tags(chunk_id);
        CREATE INDEX IF NOT EXISTS idx_chunk_tags_tag ON chunk_tags(tag_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_kind_ts ON sessions(kind, ts DESC);
        CREATE INDEX IF NOT EXISTS idx_audits_action_ts ON audits(action, ts DESC);
        """
    )

    # Ensure soul_mood column exists for older DBs
    try:
        cur.execute("PRAGMA table_info(audits);")
        cols = [r[1] for r in cur.fetchall()]
        if "soul_mood" not in cols:
            cur.execute("ALTER TABLE audits ADD COLUMN soul_mood TEXT;")
    except Exception:
        pass

    conn.commit()
    conn.close()
