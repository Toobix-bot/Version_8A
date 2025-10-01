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

Quick ChatGPT testing
---------------------

1. Start MCP server and Bridge (ports 3337 and 3333). Use `run_mcp_http.py` and `uvicorn echo_bridge.main:app` respectively (scripts/examples in `echo-bridge/README.md`).

2. Expose `/mcp` via ngrok and copy the HTTPS URL from http://127.0.0.1:4040.

3. Register the public `/mcp` URL in ChatGPT Developer Mode (or register the bridge POST endpoint `/bridge/link_echo_generate/echo_generate` if you prefer a simple HTTP tool).

4. If you set `API_KEY` in `.env` or environment, remember to provide `X-API-Key` header when calling bridge endpoints.

### Streaming /mcp Proxy (curl Beispiele)

Empfohlener Uvicorn Start für stabile Streams (ein Worker, h11):

```
uvicorn echo_bridge.main:app --host 127.0.0.1 --port 3333 --http h11 --workers 1
```

1) Erfolgreiches SSE Streaming (Verbindung offen, Events/Chunks durchgereicht):

```
curl -H "Accept: text/event-stream" -N http://127.0.0.1:3333/mcp
```

2) Fehlender Accept Header → 406 Not Acceptable:

```
curl -N http://127.0.0.1:3333/mcp -v
```

3) Streaming POST (Body wird ohne Puffern weitergeleitet, Antwort chunked gestreamt):

```
curl -X POST \
	-H "Content-Type: application/json" \
	-d '{"jsonrpc":"2.0","id":1,"method":"list_tools"}' \
	-N http://127.0.0.1:3333/mcp
```

Für einen öffentlichen Tunnel einfach `http://127.0.0.1:3333` durch deine HTTPS Tunnel-URL ersetzen (z.B. Cloudflare / ngrok). Die Endpunkte `/openapi.json` und `/chatgpt_tool_manifest.json` liefern weiterhin 200 für Registrierung/Überprüfung.

## Erweiterte Betriebsoptionen

### Heartbeat (SSE Keepalive)
Setze `MCP_SSE_HEARTBEAT_SECS` (Default 25, leer = aus), um periodisch einen Kommentar-Frame `: heartbeat` zu senden, falls der Backend-Stream länger still ist. Hilft gegen Idle-Timeouts bei einigen Proxies.

Beispiel:
```
set MCP_SSE_HEARTBEAT_SECS=20
uvicorn echo_bridge.main:app --host 127.0.0.1 --port 3333 --http h11 --workers 1
```

### Retry & Backoff
Beim Verbindungsaufbau zum Backend (`http://127.0.0.1:3339/mcp`) nutzt die Bridge jetzt ein einfaches Retry-Schema:
- `MCP_BACKEND_RETRIES` (Default 3)
- `MCP_BACKEND_BACKOFF_BASE` Sekunden (Default 0.3) → exponentiell (0.3, 0.6, 1.2 ...)

### Metrics Endpoint
`/metrics` liefert JSON:
```
{
	"sse": {"active":1,"started":3,"completed":2,"aborted":0},
	"post": {"active":0,"started":5,"completed":5,"aborted":0,"bytes_up":512,"bytes_down":2048}
}
```
Nützlich für einfache Health-Dashboards oder Prometheus-Sidecar (per externem Scraper der JSON parst).

### Named Tunnel (Cloudflare)
Für stabilere URLs statt Quick Tunnel:
1. Cloudflare Account + Domain einrichten.
2. `cloudflared tunnel login`
3. `cloudflared tunnel create echo-bridge`
4. `cloudflared tunnel route dns echo-bridge echo-bridge.example.com`
5. Config `config.yml` (z.B.):
```
tunnel: echo-bridge
credentials-file: C:\Users\<USER>\.cloudflared\<id>.json
ingress:
	- hostname: echo-bridge.example.com
		service: http://127.0.0.1:3333
	- service: http_status:404
```
6. Start: `cloudflared tunnel run echo-bridge`

### Ngrok (Alternative)
```
ngrok config add-authtoken <TOKEN>
ngrok http 3333
```

### Zusammenfassung ENV Variablen
| Variable | Bedeutung | Default |
|----------|-----------|---------|
| MCP_SSE_HEARTBEAT_SECS | Sekunden zwischen Heartbeats (0 = aus) | 25 (falls gesetzt) / aus |
| MCP_BACKEND_RETRIES | Anzahl Verbindungsversuche Backend | 3 |
| MCP_BACKEND_BACKOFF_BASE | Basis für exponentielles Backoff | 0.3 |
| MCP_ALLOW_FALLBACK_GET | Wenn gesetzt (1/true/yes): GET /mcp ohne `Accept: text/event-stream` liefert 200 JSON Hilfetext statt 406 | aus |

Diese Optionen sind optional – ohne Konfiguration bleibt Verhalten wie zuvor.

### Fallback GET /mcp
Manche Plattformen (z.B. erste ChatGPT Probe) senden einen einfachen GET ohne SSE Accept Header. Standard: 406 Not Acceptable (erzwingt korrektes SSE). Mit
```
set MCP_ALLOW_FALLBACK_GET=1
```
liefert die Bridge stattdessen ein JSON mit Instruktionen (Status 200), wodurch die Registrierung/Probe nicht scheitert. Für produktive, strikt-konforme Umgebungen lieber deaktiviert lassen.

### Tests & Smoke
REST Client Datei: `echo-bridge/mcp_tests.http`

Pytest (nur schnelle Verhaltenschecks für /mcp GET Varianten):
```
pytest -q
```

Node Smoke (SSE & POST), benötigt `npm install` (installiert `undici`):
```
cd echo-bridge
npm install
npm run smoke:sse
npm run smoke:post
```
Optional anderes Ziel:
```
set BRIDGE_BASE=https://<tunnel-domain>
npm run smoke:sse
```

### Schnellstart MCP Fallback Test
1. (ohne Fallback) – Erwartet 406:
```
curl -v http://127.0.0.1:3333/mcp
```
2. Fallback aktivieren und Bridge neu starten:
```
set MCP_ALLOW_FALLBACK_GET=1
uvicorn echo_bridge.main:app --host 127.0.0.1 --port 3333 --http h11 --workers 1
curl http://127.0.0.1:3333/mcp
```
3. SSE Verbindung:
```
curl -H "Accept: text/event-stream" -N http://127.0.0.1:3333/mcp
```



