from fastapi.testclient import TestClient

from echo_bridge.main import app, settings
from echo_bridge.db import init_db, get_conn
from echo_bridge.soul.state import get_soul


def test_soul_endpoints_and_policies(tmp_path):
    # Isolated DB
    settings.db_path = tmp_path / "soul.db"
    settings.workspace_dir = tmp_path / "ws"
    settings.workspace_dir.mkdir(parents=True, exist_ok=True)
    init_db(settings.db_path)

    client = TestClient(app)

    # /soul/state
    r = client.get("/soul/state")
    assert r.status_code == 200
    body = r.json()
    assert "mood" in body and "policies" in body

    # /soul/rituals
    r = client.get("/soul/rituals")
    assert r.status_code == 200
    assert "rituals" in r.json()

    # Enforce write confirmation
    soul = get_soul()
    pol = soul.policies
    pol["write_requires_confirmation"] = True

    key = {"X-Bridge-Key": settings.bridge_key}

    # Without confirm -> 412
    r = client.post(
        "/actions/run",
        headers=key,
        json={
            "command": "memory.add",
            "args": {
                "source": "journal",
                "title": "Z",
                "texts": ["Test"],
                # confirm omitted -> treated as False
            },
        },
    )
    assert r.status_code == 412

    # With confirm -> 200
    r = client.post(
        "/actions/run",
        headers=key,
        json={
            "command": "memory.add",
            "args": {
                "source": "journal",
                "title": "Z",
                "texts": ["Test"],
                "confirm": True,
            },
        },
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # Verify an audit row exists and soul_mood column is present
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT action, soul_mood FROM audits ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    assert row is not None
    assert "actions.run:memory.add" in str(row["action"]) or "memory.add" in str(row["action"])  # loose check
    # soul_mood may be empty string if not initialized, but column should exist
    assert "soul_mood" in row.keys()
