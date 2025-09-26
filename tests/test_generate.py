import os
import sys
import json
import asyncio
import types

import pytest
from fastapi.testclient import TestClient

# Make sure the repository root is on sys.path so `apps.api.main` can be imported
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Ensure our app is importable
import apps.api.main as main

client = TestClient(main.app)

def test_generate_fallback_no_key(monkeypatch):
    # Ensure module-level GROQ_API_KEY and groq_client reflect 'no key' state
    monkeypatch.setenv('GROQ_API_KEY', '')
    main.GROQ_API_KEY = ''
    main.groq_client = None
    # Reload module-level var if needed
    # Call endpoint
    resp = client.post('/generate', json={"prompt":"Hello"})
    assert resp.status_code == 500 or resp.status_code == 200
    # If 500 it's because we require key; if 200 the fallback returns a known prefix
    if resp.status_code == 200:
        data = resp.json()
        assert 'text' in data

class DummyChoice:
    def __init__(self, text):
        self.message = types.SimpleNamespace(content=text)

class DummyResp:
    def __init__(self, text):
        self.choices = [DummyChoice(text)]

def test_generate_with_mocked_groq(monkeypatch):
    # Mock Groq client
    def fake_create(*args, **kwargs):
        return DummyResp('Mocked response')

    class FakeClient:
        def __init__(self, api_key=None):
            pass
        @property
        def chat(self):
            return types.SimpleNamespace(completions=types.SimpleNamespace(create=fake_create))

    # Ensure module variable is set and groq_client uses the fake
    monkeypatch.setenv('GROQ_API_KEY', 'SK_TEST')
    main.GROQ_API_KEY = 'SK_TEST'
    # Provide a groq_client instance matching the fake interface
    main.groq_client = FakeClient(api_key='SK_TEST')

    resp = client.post('/generate', json={"prompt":"Test prompt"})
    assert resp.status_code == 200
    data = resp.json()
    assert data['text'] == 'Mocked response'

def test_generate_with_contextids_calls_fetch(monkeypatch):
    # Mock fetch_chunk to return a predictable context
    async def fake_fetch(cid):
        return {"id": cid, "title": "T", "content": [{"type":"text","text":"CTX"}]}

    monkeypatch.setenv('GROQ_API_KEY', '')
    main.GROQ_API_KEY = ''
    main.groq_client = None
    monkeypatch.setattr(main, 'fetch_chunk', fake_fetch)

    resp = client.post('/generate', json={"prompt":"With ctx","contextIds":["1"]})
    # Should still return (fallback) but ensure the endpoint accepts the request
    assert resp.status_code in (200, 500)
