# ECHO Playground — API

This folder contains a lightweight wrapper to run the existing FastAPI app located in `echo-bridge/echo_bridge`.

Start the API locally using the project virtual environment (from the repo root):

PowerShell example:

```powershell
# from repository root
.\echo-bridge\.venv\Scripts\python.exe -m uvicorn echo_bridge.main:app --host 127.0.0.1 --port 3333 --reload
```

API endpoints (provided by the existing project):
- `POST /ingest` — ingest documents (expects JSON with source, title, texts, tags)
- `GET /search?q=...&limit=...` — FTS5 full-text search
- `GET /healthz` — simple healthcheck
- `POST /generate` — dummy generation endpoint (returns a placeholder response)

The MCP server is implemented separately in `run_mcp_http.py` (starts an MCP HTTP/SSE server on `/mcp`).
