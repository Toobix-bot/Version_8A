import os
import pytest
from fastapi.testclient import TestClient

# Import the FastAPI app
from echo_bridge.main import app  # type: ignore

client = TestClient(app)

@pytest.fixture(autouse=True)
def clear_env():
    prev = os.environ.get('MCP_ALLOW_FALLBACK_GET')
    if 'MCP_ALLOW_FALLBACK_GET' in os.environ:
        del os.environ['MCP_ALLOW_FALLBACK_GET']
    yield
    if prev is not None:
        os.environ['MCP_ALLOW_FALLBACK_GET'] = prev


def test_mcp_get_without_accept_406():
    r = client.get('/mcp')
    assert r.status_code == 406


def test_mcp_get_with_fallback():
    os.environ['MCP_ALLOW_FALLBACK_GET'] = '1'
    r = client.get('/mcp')
    assert r.status_code == 200
    data = r.json()
    assert data['mode'] == 'fallback'


def test_mcp_get_sse_header():
    r = client.get('/mcp', headers={'Accept': 'text/event-stream'})
    # We can't fully stream inside TestClient easily, but we should get status 200
    assert r.status_code == 200
    assert r.headers['content-type'].startswith('text/event-stream')
