from fastapi.testclient import TestClient

from echo_bridge.main import app, settings
from echo_bridge.db import get_conn, init_db


def test_actions_and_audits(tmp_path):
    # isolated DB
    settings.db_path = tmp_path / "test.db"
    settings.workspace_dir = tmp_path / "ws"
    settings.workspace_dir.mkdir(parents=True, exist_ok=True)
    init_db(settings.db_path)

    client = TestClient(app)
    key = {"X-Bridge-Key": settings.bridge_key}

    # memory.add
    r = client.post(
        "/actions/run",
        headers=key,
        json={
            "command": "memory.add",
            "args": {
                "source": "journal",
                "title": "T",
                "texts": ["Alpha", "Beta Echo"],
                "meta": {"k": 1},
            },
        },
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["result"]["added"] == 2

    # memory.tag on chunk 1
    r = client.post(
        "/actions/run",
        headers=key,
        json={"command": "memory.tag", "args": {"chunk_id": 1, "tags": ["morgen", "echo"]}},
    )
    assert r.status_code == 200
    assert r.json()["result"]["linked"] >= 1

    # game.new
    r = client.post(
        "/actions/run",
        headers=key,
        json={"command": "game.new", "args": {"kind": "echo"}},
    )
    assert r.status_code == 200
    sid = r.json()["result"]["session_id"]
    assert isinstance(sid, int)

    # game.choose
    r = client.post(
        "/actions/run",
        headers=key,
        json={"command": "game.choose", "args": {"session_id": sid, "choice": "go"}},
    )
    assert r.status_code == 200
    assert r.json()["result"]["state"]["log"][0]["choice"] == "go"

    # journal.prompt (read-only)
    r = client.post(
        "/actions/run",
        headers=key,
        json={"command": "journal.prompt", "args": {"theme": "focus"}},
    )
    assert r.status_code == 200
    assert len(r.json()["result"]["prompts"]) >= 1

    # Unknown command -> 400
    r = client.post(
        "/actions/run",
        headers=key,
        json={"command": "unknown.cmd", "args": {}},
    )
    assert r.status_code == 400

    # Verify audits written
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM audits")
    c = cur.fetchone()["c"]
    assert c >= 4
