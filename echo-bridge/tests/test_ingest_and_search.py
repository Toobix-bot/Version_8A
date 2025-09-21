from fastapi.testclient import TestClient

from echo_bridge.main import app, settings


def test_ingest_and_search_flow(tmp_path):
    # Override DB and workspace for test isolation
    settings.db_path = tmp_path / "test.db"
    settings.workspace_dir = tmp_path / "ws"
    from echo_bridge.db import init_db

    settings.workspace_dir.mkdir(parents=True, exist_ok=True)
    init_db(settings.db_path)

    client = TestClient(app)
    # Missing key should 401
    r = client.post(
        "/ingest/text",
        json={"source": "journal", "title": "Morgen", "texts": ["Heute dient mir Freude."]},
    )
    assert r.status_code == 401

    # With key
    r = client.post(
        "/ingest/text",
        headers={"X-Bridge-Key": settings.bridge_key},
        json={
            "source": "journal",
            "title": "Morgen",
            "texts": [
                "Heute dient mir Freude.",
                "Morgen stärke ich meinen Fokus.",
                "Ein Echo hallt in der Freude wider.",
            ],
            "meta": {"tags": ["echo"]},
        },
    )
    assert r.status_code == 200
    assert r.json()["added"] == 3

    # Search for Freude
    r = client.get("/search", params={"q": "Freude", "k": 5})
    assert r.status_code == 200
    hits = r.json()["hits"]
    assert len(hits) >= 1
    assert any("Freude" in h["snippet"] for h in hits)
