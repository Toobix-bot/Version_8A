# Registering ECHO-Bridge tools with ChatGPT Developer Mode

This guide shows how to expose and register the ECHO-Bridge `echo_generate` tool so ChatGPT can call it.

1) Make /mcp publicly reachable

- Start MCP server locally (if not running):

```powershell
Start-Job -ScriptBlock { & 'C:\GPT\Version_8\echo-bridge\.venv\Scripts\python.exe' 'C:\GPT\Version_8\run_mcp_http.py' --host 127.0.0.1 --port 3337 *> 'C:\GPT\Version_8\mcp_server.log' 2>&1 }
```

- Start ngrok and forward port 3337:

```powershell
ngrok http 3337
# get public url from http://127.0.0.1:4040/api/tunnels
```

2) Tool registration options

- Option A — Register the MCP endpoint (recommended for full tool discovery):
  - In ChatGPT Dev Tools, provide the public ngrok HTTPS URL + path `/mcp` as the tool endpoint.
  - ChatGPT will call `tools/list` and discover `echo_generate` automatically (no extra manifest needed).

- Option B — Register the Bridge POST endpoint as a simple HTTP tool:
  - Use `https://<public>/bridge/link_echo_generate/echo_generate` as the tool endpoint.
  - Make sure to set `X-API-Key` header in calls (if you enabled `API_KEY` protection).

3) Notes
- If your Groq key is not configured in the server process, generation will fall back to a dummy response.
- Use the `echo-bridge/chatgpt_tool_manifest.json` in this repo as a template for manual registration.

4) Fetch the ngrok public URL programmatically (PowerShell example)

Run this to get the HTTPS tunnel URL and copy it into the manifest or ChatGPT Dev Tools:

```powershell
$t = Invoke-RestMethod -Uri http://127.0.0.1:4040/api/tunnels
$t.tunnels | Where-Object { $_.public_url -like 'https:*' } | Select-Object -First 1 -ExpandProperty public_url
```

5) Manifest template (fill in your public host)

Use this manifest snippet for ChatGPT Developer Mode (replace <PUBLIC_HOST> with the HTTPS host returned by ngrok, without trailing slash):

```json
{
  "schema_version": "v1",
  "name_for_human": "ECHO Bridge (dev)",
  "name_for_model": "echo_bridge",
  "description_for_human": "Generative bridge for the ECHO workspace (dev)",
  "description_for_model": "Tool to call the ECHO generate pipeline",
  "auth": {"type":"none"},
  "api": {
    "type": "openapi",
    "url": "https://<PUBLIC_HOST>/mcp/openapi.json",
    "is_user_authenticated": false
  },
  "logo_url": "https://<PUBLIC_HOST>/public/logo.png",
  "contact_email": "dev@example.com",
  "legal_info_url": "https://example.com/legal"
}
```

Notes
- If you register the MCP endpoint at `https://<PUBLIC_HOST>/mcp` ChatGPT will call `tools/list` and discover the available tools automatically. If you register the Bridge POST endpoint directly you may need to provide an OpenAPI/JSON manifest that describes the single POST route.

If ngrok is flaky, consider using a persistent tunneling solution such as Tailscale or deploying the bridge to a cloud VM and pointing the manifest at that host.
