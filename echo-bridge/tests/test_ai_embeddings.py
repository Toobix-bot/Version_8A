from echo_bridge.ai.embedder import embed, similar
from echo_bridge.ai.cluster import kmeans_texts
from echo_bridge.db import init_db, get_conn


def test_embed_and_similar(tmp_path):
    # Build small DB
    from echo_bridge.main import settings

    settings.db_path = tmp_path / "sim.db"
    init_db(settings.db_path)
    conn = get_conn()
    cur = conn.cursor()
    data = [
        ("A", None, "alpha beta gamma"),
        ("A", None, "alpha beta"),
        ("A", None, "delta epsilon"),
    ]
    for s, t, x in data:
        cur.execute("INSERT INTO chunks(doc_source, doc_title, text) VALUES (?,?,?)", (s, t, x))
    conn.commit()

    # similar to first should include second
    sims = similar(1, k=2)
    ids = [cid for cid, _ in sims]
    assert 2 in ids


def test_kmeans_basic():
    chunks = {
        1: "alpha beta gamma",
        2: "beta gamma",
        3: "delta epsilon",
        4: "delta zeta",
    }
    labels = kmeans_texts(chunks, k=2, iters=5)
    # Expect 1 & 2 together or 3 & 4 together
    assert labels[1] == labels[2] or labels[3] == labels[4]
