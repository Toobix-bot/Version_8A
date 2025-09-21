from fastapi.testclient import TestClient

from echo_bridge.main import app, settings
from echo_bridge.db import init_db, get_conn
from echo_bridge.services.memory_service import add_chunks


def test_ai_actions_preview_and_confirm(tmp_path):
    # isolated DB
    settings.db_path = tmp_path / "ai.db"
    settings.workspace_dir = tmp_path / "ws"
    settings.workspace_dir.mkdir(parents=True, exist_ok=True)
    init_db(settings.db_path)

    client = TestClient(app)
    key = {"X-Bridge-Key": settings.bridge_key}

    # Seed memory
    add_chunks("journal", "T", ["alpha beta gamma", "alpha beta"], None)

    # journal.summarize (read-only)
    r = client.post(
        "/actions/run",
        headers=key,
        json={"command": "journal.summarize", "args": {"text": "Heute dient mir Freude. Morgen stärke ich meinen Fokus."}},
    )
    assert r.status_code == 200
    assert "summary" in r.json()["result"]

    # memory.auto_tag preview (no confirm) should not write but return suggestions
    r = client.post(
        "/actions/run",
        headers=key,
        json={"command": "memory.auto_tag", "args": {"chunk_id": 1, "text": "alpha beta gamma", "confirm": False}},
    )
    assert r.status_code == 200
    res = r.json()["result"]
    assert "suggested_tags" in res and isinstance(res["suggested_tags"], list)
    # confirm=true should write links and create audit
    r = client.post(
        "/actions/run",
        headers=key,
        json={"command": "memory.auto_tag", "args": {"chunk_id": 1, "text": "alpha beta gamma", "confirm": True}},
    )
    assert r.status_code == 200
    # verify there are tag links for chunk 1
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM chunk_tags WHERE chunk_id=1")
    assert cur.fetchone()["c"] >= 1
