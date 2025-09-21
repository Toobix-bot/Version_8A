from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class SoulConfig:
    values: list[str] = field(default_factory=list)
    policies: dict[str, Any] = field(default_factory=dict)
    tones: dict[str, str] = field(default_factory=dict)
    moods: list[str] = field(default_factory=lambda: ["calm", "focused", "curious", "overwhelmed"])
    transitions: list[dict[str, str]] = field(default_factory=list)


class Soul:
    def __init__(self, cfg: SoulConfig, identity_md: str, rituals: list[dict[str, Any]], timeline_path: Optional[Path] = None) -> None:
        self._cfg = cfg
        self._identity_md = identity_md
        self._rituals = rituals
        self._mood: str = cfg.moods[0] if cfg.moods else "calm"
        self._timeline_path = timeline_path

    # Config accessors
    @property
    def policies(self) -> dict[str, Any]:
        return self._cfg.policies

    @property
    def moods(self) -> list[str]:
        return list(self._cfg.moods)

    @property
    def identity_md(self) -> str:
        return self._identity_md

    @property
    def rituals(self) -> list[dict[str, Any]]:
        return list(self._rituals)

    # Mood/state
    def get_mood(self) -> str:
        return self._mood

    def set_mood(self, mood: str, reason: Optional[str] = None) -> None:
        if mood not in (self._cfg.moods or ["calm"]):
            return
        prev = self._mood
        self._mood = mood
        self._append_timeline({
            "kind": "mood_change",
            "from": prev,
            "to": mood,
            "reason": reason,
        })

    # Timeline
    def _append_timeline(self, event: dict[str, Any]) -> None:
        if not self._timeline_path:
            return
        try:
            self._timeline_path.parent.mkdir(parents=True, exist_ok=True)
            with self._timeline_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception:
            # best-effort only
            pass

    def append_event(self, action: str, payload: dict[str, Any], result: dict[str, Any], consent_checked: bool) -> None:
        self._append_timeline({
            "kind": "action",
            "action": action,
            "payload": payload,
            "result": result,
            "mood": self._mood,
            "consent_checked": consent_checked,
        })


_GLOBAL_SOUL: Optional[Soul] = None


def init_soul(soul: Soul) -> None:
    global _GLOBAL_SOUL
    _GLOBAL_SOUL = soul


def get_soul() -> Soul:
    if _GLOBAL_SOUL is None:
        # Provide a permissive fallback if not initialized
        return Soul(SoulConfig(), identity_md="", rituals=[], timeline_path=None)
    return _GLOBAL_SOUL
