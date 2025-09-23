# Version_8A Workspace

See `echo-bridge/` for ECHO-BRIDGE project (FastAPI + SQLite FTS5).

Quick start on Windows PowerShell:

```
cd echo-bridge
python -m venv .venv; .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn echo_bridge.main:app --host 127.0.0.1 --port 3333
```


## MCP (Model Context Protocol)

Start standalone Streamable HTTP MCP server:

```
cd echo-bridge
.venv\Scripts\python.exe run_mcp_http.py --host 127.0.0.1 --port 3337
# Endpoint: http://127.0.0.1:3337/mcp
```

Windows helpers (new consoles):

```
scripts\start-standalone-mcp.ps1            # binds 127.0.0.1:3337
scripts\start-standalone-mcp-public.ps1     # binds 0.0.0.0:3337 (LAN)
```

Notes:
- A plain GET to `/mcp` returns 406 Not Acceptable unless the client sends `Accept: text/event-stream`.
- At least one tool is registered (`echo_search`) via `echo_bridge/mcp_setup.py`.

### Local inspection

Use an MCP Inspector to verify tools/prompts/resources and exercise calls. Point it to:

- http://127.0.0.1:3337/mcp (streamable HTTP/SSE)

### Expose to ChatGPT (cloud)

ChatGPT cannot reach `127.0.0.1`. For web Chat:

1) Bind publicly or tunnel:

- Public bind (LAN): `scripts\start-standalone-mcp-public.ps1` then use `http://<LAN-IP>:3337/mcp`.
- Tunnel (recommended): ngrok or Tailscale to get a public HTTPS URL, e.g. `https://<subdomain>.ngrok.io/mcp`.

2) Add as Custom Connector:

- ChatGPT Settings → Connectors → Custom → add your MCP URL.
- If you see “This MCP server doesn't implement our specification”, verify tools schema and transport.

