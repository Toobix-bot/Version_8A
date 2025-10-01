Echo-Bridge — quick start (Windows)

This small README gives the exact commands I used to run MCP and the Bridge on Windows for local development.

## ChatGPT manifest smoke-test (free)

Run the included free smoke-test to verify the public manifest/OpenAPI are reachable and CORS-enabled.

PowerShell (from repo root):

```powershell
.\echo-bridge\tools\smoke_test.ps1
```

Expected: each endpoint prints Status 200 and `ACAO: *`.

Import into ChatGPT → Developer Tools / Actions using the manifest URL:

- https://delete-organised-gsm-posing.trycloudflare.com/chatgpt_tool_manifest.json
- or: https://delete-organised-gsm-posing.trycloudflare.com/openapi.json

Notes: the trycloudflare URL is ephemeral; if it changes, set the env var `PUBLIC_BASE_URL` and restart the bridge.

Prereqs
- Python 3.11+ and a virtualenv created in `echo-bridge/.venv`
- From repo root: `cd echo-bridge` and create venv if needed.

Start MCP (background)
```powershell
# from repo root
$log = 'C:\GPT\Version_8\mcp_server.log'
if (Test-Path $log) { Remove-Item $log -Force }
Start-Process -FilePath '.\.venv\Scripts\python.exe' -ArgumentList 'run_mcp_http.py','--host','0.0.0.0','--port','3337' -WorkingDirectory (Join-Path (Get-Location) 'echo-bridge') -RedirectStandardOutput $log -RedirectStandardError $log -NoNewWindow
```

Start Bridge (background) — with API key
```powershell
# set API key and start bridge (background)
Start-Process -FilePath 'echo-bridge\scripts\start_bridge_cmd_wrapper.bat' -ArgumentList 'test-secret-123','127.0.0.1','3333' -WorkingDirectory (Join-Path (Get-Location) 'echo-bridge') -NoNewWindow
```

Run smoke test
```powershell
echo-bridge\.venv\Scripts\python.exe echo-bridge\scripts\echo_generate_smoke.py --bridge-key test-secret-123
```

Notes
- If you start the Bridge without setting `API_KEY`, the endpoint will not require X-API-Key.
- The smoke script now accepts `--bridge-key` or reads `BRIDGE_KEY` / `API_KEY` from the environment.

## GUI control panel

If you prefer a small desktop helper instead of juggling terminals, launch the Tk interface:

```
python tools/control_panel.py
```

Features:
- Start/stop MCP, Bridge, and a Cloudflare quick tunnel with individual buttons
- Automatic detection of the public trycloudflare URL (and optional auto-fill of `PUBLIC_BASE_URL`)
- Built-in smoke test to verify local/public manifest, OpenAPI, and `/mcp` SSE connectivity
- Combined log viewer so you can watch all processes at once
- Instant copy buttons for the tunnel origin and the recommended ChatGPT connector URL (`<origin>/mcp`)

Tips:
- Update the Python executable or cloudflared path at the top of the window if you use a virtualenv or a named tunnel.
- When a tunnel URL is detected you can copy it straight from the UI or push it into the bridge's `PUBLIC_BASE_URL` field.
- The smoke test results appear both in the status line and in the log pane.
- When registering in ChatGPT Developer Tools, use `https://<your-public-origin>/mcp` and ensure the client sends `Accept: text/event-stream` for SSE connections.
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

## Named tunnel helper (cloudflared)

If you want a stable public URL for ChatGPT to fetch your manifest, use a Cloudflare Tunnel.

- Requirements: install `cloudflared` and authenticate it with `cloudflared login` (requires a Cloudflare account and permissions to manage DNS for the hostname you choose).
- The repository includes a small helper to create or run a named tunnel:

PowerShell (from repo root):

```powershell
powershell -ExecutionPolicy Bypass -File .\echo-bridge\tools\create_named_tunnel.ps1 -Name my-echo-tunnel -Port 3333
```

Options:
- `-Hostname example.yourdomain.com` — create a DNS route for a stable hostname (requires Cloudflare DNS control).
- `-RunInBackground` — start cloudflared in the background (ephemeral trycloudflare URLs may be printed in the cloudflared output).

After the helper creates a hostname mapping it writes `echo-bridge/.env` with `PUBLIC_BASE_URL=https://your-hostname` for convenience. Set that environment variable when starting the bridge and restart uvicorn so the manifest/OpenAPI reference the stable public URL.

Note: creating a hostname-based tunnel requires Cloudflare account access and DNS configuration. If you only need a quick ephemeral URL, the helper can start a tunnel that prints a trycloudflare URL in its output.