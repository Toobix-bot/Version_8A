# ECHO-BRIDGE (MVP)

Local bridge for context and controlled actions. FastAPI + SQLite FTS5. Binds 127.0.0.1 only.

## Quickstart

- Python 3.11+
- Create venv and install deps:

```
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
```

Start server:

```
uvicorn echo_bridge.main:app --host 127.0.0.1 --port 3333
```

Example requests in docs and tests. See `config.yaml` for settings.

### MCP server (ChatGPT Developer Mode)

This repo includes a minimal MCP server using FastMCP that exposes tools over HTTP(SSE)/WS at `/mcp`.

Run it locally (separate port):

```
# from repo folder
cd echo-bridge
.venv\Scripts\python.exe -m echo_bridge.mcp_fastmcp http --host 127.0.0.1 --port 3334 --path /mcp
```

Connect in ChatGPT → Developer Mode → Add connector:

- URL: `http://127.0.0.1:3334/mcp`
	- `memory_search(query, k=5)`
	- `memory_add(source, title=None, texts=[], meta=None, key=None)`
	- `fs_list_tool(subdir=None)`
	- `fs_read_tool(path)`
	- `actions_run(command, args=None, tier_mode=None, key=None)`

New bridge endpoint
-------------------

This repo also exposes a bridge-compatible proxy for generation at:

`POST /bridge/link_echo_generate/echo_generate`

It proxies to the local `/generate` handler and can be registered as an MCP tool. Example curl usage:

```
curl -s http://127.0.0.1:3333/bridge/link_echo_generate/echo_generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Write a short scene","contextIds":["1"]}'
```

Writes require the bridge key (same as API key in `config.yaml`).

Quick run & smoke test
-----------------------

1. Start the MCP server (if not already running):

```powershell
Start-Job -ScriptBlock { & 'C:\GPT\Version_8\echo-bridge\.venv\Scripts\python.exe' 'C:\GPT\Version_8\run_mcp_http.py' --host 127.0.0.1 --port 3337 *> 'C:\GPT\Version_8\mcp_server.log' 2>&1 }
```

2. Open the simple UI:

Point your browser to `http://127.0.0.1:3333/public/` and open `generate.html` (or go to `/public/generate.html`).

3. Run the smoke-test script (calls both MCP and Bridge locally):

```powershell
python echo-bridge\scripts\echo_generate_smoke.py
```

Writes require the bridge key (same as API key in `config.yaml`).

## Security

- Write routes require `X-Bridge-Key` header.
- File system routes are read-only and sandboxed to `workspace/`.
- No external network writes; all actions audited.

## License

MIT (project scaffold)