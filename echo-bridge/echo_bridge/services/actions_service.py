from __future__ import annotations

import json
from typing import Any, cast

from ..db import get_conn
from .memory_service import add_chunks
from ..ai.brain import Policy, apply as ai_apply
from ..soul.state import get_soul


class ActionError(Exception):
    pass


class PreconditionFailed(Exception):
    pass


def _audit(action: str, payload: dict[str, Any], result: dict[str, Any]) -> None:
    conn = get_conn()
    cur = conn.cursor()
    mood = ""
    try:
        mood = get_soul().get_mood()
    except Exception:
        mood = ""
    cur.execute(
        "INSERT INTO audits(action, payload_json, result_json, soul_mood) VALUES (?,?,?,?)",
        (action, json.dumps(payload, ensure_ascii=False), json.dumps(result, ensure_ascii=False), mood),
    )
    conn.commit()


def dispatch(command: str, args: dict[str, Any], policy: Policy | None = None) -> dict[str, Any]:
    pol = policy or Policy()
    if command == "memory.add":
        source = args.get("source")
        texts_any = args.get("texts") or []
        if not isinstance(texts_any, list) or not all(isinstance(t, str) for t in texts_any):
            raise ActionError("Invalid texts type")
        title = args.get("title")
        meta = args.get("meta")
        if not isinstance(source, str):
            raise ActionError("Invalid arguments for memory.add")
        texts = cast(list[str], texts_any)
        n = add_chunks(source, title, texts, meta)
        result: dict[str, Any] = {"added": n}
        _audit(command, args, result)
        return result
    elif command == "memory.tag":
        chunk_id = args.get("chunk_id")
        tags_any = args.get("tags") or []
        if not isinstance(tags_any, list) or not all(isinstance(t, str) for t in tags_any):
            raise ActionError("Invalid tags type")
        if not isinstance(chunk_id, int):
            raise ActionError("Invalid arguments for memory.tag")
        conn = get_conn()
        cur = conn.cursor()
        # ensure tags exist and link
        tag_ids: list[int] = []
        tags = cast(list[str], tags_any)
        for name in tags:
            if not isinstance(name, str):
                continue
            cur.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (name,))
            cur.execute("SELECT id FROM tags WHERE name=?", (name,))
            row = cur.fetchone()
            if row:
                tag_ids.append(row["id"])
        for tid in tag_ids:
            cur.execute(
                "INSERT OR IGNORE INTO chunk_tags(chunk_id, tag_id) VALUES (?,?)",
                (chunk_id, tid),
            )
        conn.commit()
        result = {"linked": len(tag_ids)}
        _audit(command, args, result)
        return result
    elif command == "memory.group":
        tag = args.get("tag")
        query = args.get("query")
        if not isinstance(tag, str) or not isinstance(query, str):
            raise ActionError("Invalid arguments for memory.group")
        # store as a tag with meta
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (tag,))
        # For MVP, audit only; grouping is conceptual
        result = {"group": tag, "query": query}
        _audit(command, args, result)
        return result
    elif command == "game.new":
        kind = args.get("kind", "echo")
        state: dict[str, Any] = {"log": [], "choices": []}
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO sessions(kind, state_json) VALUES (?, ?)",
            (kind, json.dumps(state, ensure_ascii=False)),
        )
        session_id = cur.lastrowid
        conn.commit()
        result = {"session_id": session_id, "kind": kind}
        _audit(command, args, result)
        return result
    elif command == "game.choose":
        session_id = args.get("session_id")
        choice = args.get("choice")
        if not isinstance(session_id, int) or not isinstance(choice, str):
            raise ActionError("Invalid arguments for game.choose")
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT state_json FROM sessions WHERE id=?", (session_id,))
        row = cur.fetchone()
        if not row:
            raise ActionError("Session not found")
        state = cast(dict[str, Any], json.loads(row["state_json"]))
        log_list = state.setdefault("log", [])
        if isinstance(log_list, list):
            log_list.append({"choice": choice})
        else:
            state["log"] = [{"choice": choice}]
        cur.execute(
            "UPDATE sessions SET state_json=? WHERE id=?",
            (json.dumps(state, ensure_ascii=False), session_id),
        )
        conn.commit()
        result = {"session_id": session_id, "state": state}
        _audit(command, args, result)
        return result
    elif command == "journal.prompt":
        theme = args.get("theme") or "daily"
        prompts = {
            "daily": [
                "Wofür warst du heute dankbar?",
                "Welche kleine Entscheidung hat deinen Tag verbessert?",
            ],
            "focus": [
                "Was ist heute das Eine, das den Unterschied macht?",
                "Welche Ablenkung kannst du bewusst eliminieren?",
            ],
        }
        result = {"theme": theme, "prompts": prompts.get(theme, prompts["daily"])}
        # Read-only action still audited for traceability
        _audit(command, args, result)
        return result
    elif command == "journal.summarize":
        # AI read-only
        text = args.get("text", "")
        out = ai_apply("journal.summarize", {"text": text}, policy=pol)
        result = out
        _audit(command, args, result)
        return result
    elif command == "memory.auto_tag":
        # Preview by default; confirm=True writes tag links
        chunk_id = args.get("chunk_id")
        text = args.get("text", "")
        confirm = bool(args.get("confirm", False))
        out: dict[str, Any] = ai_apply("memory.auto_tag", {"chunk_id": chunk_id, "text": text}, policy=pol)
        if confirm:
            # perform writes to tags/chunk_tags
            tags = out.get("suggested_tags", [])
            if not isinstance(chunk_id, int):
                raise ActionError("Invalid chunk_id for memory.auto_tag")
            conn = get_conn()
            cur = conn.cursor()
            tag_ids: list[int] = []
            for name in tags:
                if not isinstance(name, str):
                    continue
                cur.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (name,))
                cur.execute("SELECT id FROM tags WHERE name=?", (name,))
                row = cur.fetchone()
                if row:
                    tag_ids.append(row["id"])
            for tid in tag_ids:
                cur.execute("INSERT OR IGNORE INTO chunk_tags(chunk_id, tag_id) VALUES (?,?)", (chunk_id, tid))
            conn.commit()
            out = {**out, "linked": len(tag_ids)}
        _audit(command, args, out)
        return out
    elif command == "game.describe":
        state = args.get("state") or {}
        if not isinstance(state, dict):
            raise ActionError("Invalid state type")
        out = ai_apply("game.describe", {"state": state}, policy=pol)
        _audit(command, args, out)
        return out
    elif command == "lesson.plan":
        text = args.get("text", "")
        out = ai_apply("lesson.plan", {"text": text}, policy=pol)
        _audit(command, args, out)
        return out
    else:
        raise ActionError("Unknown command")
