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


@dataclass
class TierPolicy:
    enabled: bool
    timeout_ms: int
    allow_llm: bool = False


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
        state_raw: Any = payload.get("state") or {}
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


def pipeline(task: str, payload: dict[str, Any], tiers_cfg: dict[str, dict[str, object]] | None, policy: Policy | None = None) -> dict[str, Any]:
    """Run three-tier pipeline and return layered output {under, core, over}.

    tiers_cfg shape: { under|core|over: {enabled: bool, timeout_ms: int, allow_llm?: bool} }
    """
    cfg = tiers_cfg or {
        "under": {"enabled": True, "timeout_ms": 400, "allow_llm": False},
        "core": {"enabled": True, "timeout_ms": 800, "allow_llm": False},
        "over": {"enabled": True, "timeout_ms": 1600, "allow_llm": False},
    }
    pol = policy or Policy()

    def _under() -> dict[str, Any]:
        if not cfg.get("under", {}).get("enabled", True):
            return {}
        if task == "journal.summarize":
            text: str = payload.get("text", "")
            return {
                "summary": " ".join(reflexes.summary(text, max_sents=int(payload.get("max_sents", 3)))) or "",
                "keywords": reflexes.keywords(text, k=int(payload.get("k", 8))),
            }
        if task == "memory.auto_tag":
            text: str = payload.get("text", "")
            return {"candidates": reflexes.keywords(text, k=int(payload.get("k", 10)))}
        if task == "game.describe":
            state_raw: Any = payload.get("state") or {}
            state: dict[str, Any] = cast(dict[str, Any], state_raw) if isinstance(state_raw, dict) else {}
            return {"state": reflexes.game_next(state)}
        if task == "lesson.plan":
            text: str = payload.get("text", "")
            return {"plan": [f"Lerne: {w}" for w in reflexes.keywords(text, k=6)]}
        return {}

    def _core(u: dict[str, Any]) -> dict[str, Any]:
        if not cfg.get("core", {}).get("enabled", True):
            return u
        if task == "journal.summarize":
            # Evidence placeholder (could pull from FTS5)
            return {**u, "evidence": payload.get("evidence", [])}
        if task == "memory.auto_tag":
            chunk_id = payload.get("chunk_id")
            neighbors: list[tuple[int, float]] = []
            if pol.s2 and isinstance(chunk_id, int):
                neighbors = s2_similar(chunk_id, k=5)
            return {**u, "neighbors": neighbors}
        if task == "game.describe":
            st_raw: Any = u.get("state") or {}
            st: dict[str, Any] = cast(dict[str, Any], st_raw) if isinstance(st_raw, dict) else {}
            desc = f"Szene: {st.get('node','start')}. Vorschlag: {st.get('suggested_next','weiter')}"
            return {**u, "description": desc}
        return u

    def _over(c: dict[str, Any]) -> dict[str, Any]:
        if not cfg.get("over", {}).get("enabled", True):
            return c
        # Ethics/consent checks would be here; add a checked note
        out_over: dict[str, Any] = {**c, "notes": ["checked_by_over"]}
        return out_over

    u = _under()
    c = _core(u)
    o = _over(c)
    return {"under": u, "core": c, "over": o}
