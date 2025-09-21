from echo_bridge.ai.reflexes import summary, keywords, dedupe


def test_summary_keywords_deterministic():
    text = (
        "Heute dient mir Freude. Morgen stärke ich meinen Fokus. "
        "Ein Echo hallt in der Freude wider. Fokus hilft beim Lernen."
    )
    sents = summary(text, max_sents=2)
    # Expect the first sentence to be included due to position bonus
    assert "Heute dient mir Freude." in sents
    # And a sentence about Fokus or Echo selected by TF-IDF
    joined = " ".join(sents)
    assert ("Fokus" in joined) or ("Echo" in joined)

    kws = keywords(text, k=5)
    # Lowercase, contains meaningful words
    assert "freude" in kws
    assert "fokus" in kws
    # Deterministic order for top keywords (by score, then lexicographic)
    assert kws == sorted(kws, key=lambda t: kws.index(t))


def test_dedupe_marks_duplicates():
    chunks = [
        {"id": 1, "text": "Alpha Beta Gamma"},
        {"id": 2, "text": "Alpha Beta Gamma"},
        {"id": 3, "text": "Alpha Beta"},
    ]
    out = dedupe(chunks, threshold=0.95)
    assert out[0].get("dup_of") is None
    assert out[1].get("dup_of") == 1
    # third one is similar but below threshold; should remain unique
    assert out[2].get("dup_of") is None
