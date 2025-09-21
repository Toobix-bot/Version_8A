from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .state import Soul, SoulConfig


def load_soul(root: Path, timeline_path: Path | None = None) -> Soul:
    soul_dir = root / "soul"
    constitution_path = soul_dir / "constitution.yaml"
    consent_path = soul_dir / "consent.yaml"
    identity_path = soul_dir / "identity.md"
    rituals_path = soul_dir / "rituals.jsonl"

    values: list[str] = []
    policies: dict[str, Any] = {}
    tones: dict[str, str] = {}
    moods = ["calm", "focused", "curious", "overwhelmed"]
    transitions: list[dict[str, str]] = []

    if constitution_path.exists():
        try:
            raw = yaml.safe_load(constitution_path.read_text(encoding="utf-8"))
            data: dict[str, Any] = raw if isinstance(raw, dict) else {}
            vals = data.get("values", [])
            pols = data.get("policies", {})
            tns = data.get("tones", {})
            values = [str(v) for v in (vals or [])] if isinstance(vals, list) else []
            policies = dict(pols) if isinstance(pols, dict) else {}
            tones = {str(k): str(v) for k, v in (tns or {}).items()} if isinstance(tns, dict) else {}
        except Exception:
            pass

    # Consent could later drive granular checks; for MVP, treat as policies overlay
    if consent_path.exists():
        try:
            raw = yaml.safe_load(consent_path.read_text(encoding="utf-8"))
            consent_data: dict[str, Any] = raw if isinstance(raw, dict) else {}
            # Overlay into policies under key 'consent'
            policies["consent"] = consent_data
        except Exception:
            pass

    identity_md = identity_path.read_text(encoding="utf-8") if identity_path.exists() else ""

    rituals: list[dict[str, Any]] = []
    if rituals_path.exists():
        try:
            for line in rituals_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rituals.append(json.loads(line))
                except Exception:
                    continue
        except Exception:
            pass

    cfg = SoulConfig(values=values, policies=policies, tones=tones, moods=moods, transitions=transitions)
    return Soul(cfg, identity_md=identity_md, rituals=rituals, timeline_path=timeline_path)
