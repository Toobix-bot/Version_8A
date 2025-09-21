from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, cast

from ..db import get_conn
from ..soul.state import get_soul
from . import reflexes
from .embedder import similar as s2_similar


@dataclass
class Policy:
    s1: bool = True
    s2: bool = True
    s3: bool = False


def _audit_ai(task: str, payload: dict[str, Any], result: dict[str, Any], duration_ms: int, chosen: str) -> None:
    conn = get_conn()
    cur = conn.cursor()
    mood = ""
    try:
        mood = get_soul().get_mood()
    except Exception:
        mood = ""
    cur.execute(
        "INSERT INTO audits(action, payload_json, result_json, soul_mood) VALUES (?,?,?,?)",
        (
            f"ai.{task}:{chosen}",
            json.dumps({"payload": payload, "duration_ms": duration_ms}, ensure_ascii=False),
            json.dumps(result, ensure_ascii=False),
            mood,
        ),
    )
    conn.commit()


def apply(task: str, payload: dict[str, Any], policy: Policy | None = None) -> dict[str, Any]:
    """Apply an AI task via S1/S2/S3 depending on policy.

    Tasks:
      - journal.summarize -> uses S1 summary
      - memory.auto_tag -> uses S1 keywords + S2 similar
      - game.describe -> uses S1 game_next (template)
      - lesson.plan -> S1 rules over keywords
    """
    pol = policy or Policy()
    start = time.perf_counter()
    chosen = "s1"
    result: dict[str, Any] = {}

    if task == "journal.summarize":
        text: str = payload.get("text", "")
        max_sents: int = int(payload.get("max_sents", 3))
        sents = reflexes.summary(text, max_sents=max_sents)
        result = {"summary": " ".join(sents)}
        chosen = "s1"
    elif task == "memory.auto_tag":
        # Suggest tags: keywords of provided text + neighbors titles
        text: str = payload.get("text", "")
        k: int = int(payload.get("k", 8))
        kws = reflexes.keywords(text, k=k)
        chunk_id = payload.get("chunk_id")
        neighbors: list[tuple[int, float]] = []
        if pol.s2 and isinstance(chunk_id, int):
            neighbors = s2_similar(chunk_id, k=5)
        result = {"suggested_tags": kws, "neighbors": neighbors}
        chosen = "s2" if neighbors else "s1"
    elif task == "game.describe":
        state_raw = payload.get("state") or {}
        state = cast(dict[str, Any], state_raw) if isinstance(state_raw, dict) else {}
        state2 = reflexes.game_next(state)
        desc = f"Szene: {state2.get('node','start')}. Vorschlag: {state2.get('suggested_next','weiter')}"
        result = {"description": desc, "state": state2}
        chosen = "s1"
    elif task == "lesson.plan":
        text: str = payload.get("text", "")
        kws = reflexes.keywords(text, k=6)
        steps = [f"Lerne: {w}" for w in kws]
        result = {"plan": steps}
        chosen = "s1"
    else:
        raise ValueError("Unknown AI task")

    duration_ms = int((time.perf_counter() - start) * 1000)
    _audit_ai(task, payload, result, duration_ms, chosen)
    return result
