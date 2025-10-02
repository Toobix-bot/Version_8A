# 🔌 Connector Setup Guide

Your bridge is running at: **https://multiplicative-unapprehendably-marisha.ngrok-free.dev**

## ✅ Option A.1: ChatGPT Custom Connector

### 1. Open ChatGPT Settings
1. Go to [ChatGPT](https://chat.openai.com/)
2. Click your profile icon (bottom left)
3. Go to **Settings** → **Beta Features**
4. Enable **Plugins** (if not already enabled)

### 2. Add Custom Connector
1. Open any chat
2. Click the **Plugin Store** icon (puzzle piece)
3. Scroll down and click **"Develop your own plugin"**
4. Enter your endpoint URL:
   ```
   https://multiplicative-unapprehendably-marisha.ngrok-free.dev
   ```
5. ChatGPT will fetch `/.well-known/ai-plugin.json` (auto-redirected to `/public/chatgpt_tool_manifest.json`)
6. Verify the manifest shows:
   - **Name**: ECHO Bridge
   - **Description**: Generieren und Kontext-Ressourcen abrufen
   - **Auth**: None

### 3. Test Queries
Once installed, try these prompts:
- *"Use echo_bridge to generate a summary of quantum computing"*
- *"Search my resources for 'machine learning'"*
- *"List my recent context chunks"*

---

## ✅ Option A.2: Claude Desktop Integration

### 1. Locate Config File
Open this file in your editor:
```
%APPDATA%\Claude\claude_desktop_config.json
```

**Full path**: `C:\Users\<YourUsername>\AppData\Roaming\Claude\claude_desktop_config.json`

### 2. Add MCP Server Configuration
If the file is empty or has `{}`, replace with:

```json
{
  "mcpServers": {
    "toobix-bridge": {
      "url": "https://multiplicative-unapprehendably-marisha.ngrok-free.dev/mcp",
      "transport": {
        "type": "sse"
      }
    }
  }
}
```

If you already have other MCP servers, just add the `"toobix-bridge"` entry inside `mcpServers`.

### 3. Restart Claude Desktop
- Completely quit Claude Desktop (right-click tray icon → Exit)
- Relaunch Claude Desktop
- Look for a **tools icon** (🔧) in the chat input area

### 4. Test with Claude
Try these prompts:
- *"What MCP tools are available?"*
- *"Use echo_generate to create a haiku about autumn"*
- *"Search resources for 'neural networks'"*

---

## 🔍 Verify Connectivity

### Check Bridge Status
Open in browser: [http://127.0.0.1:3333/panel](http://127.0.0.1:3333/panel)

**Green indicators should show**:
- ✅ Manifest OK
- ✅ OpenAPI OK  
- ✅ Backend SSE
- ✅ Fallback Enabled

### Manual API Test
Test the endpoint directly:

**PowerShell**:
```powershell
Invoke-WebRequest -Uri "https://multiplicative-unapprehendably-marisha.ngrok-free.dev/action_ready" -UseBasicParsing
```

**Expected response**:
```json
{
  "public_base_url": "https://multiplicative-unapprehendably-marisha.ngrok-free.dev",
  "fallback_enabled": true,
  "manifest_ok": true,
  "openapi_ok": true,
  "backend_sse": true,
  "timestamp": 1759413123
}
```

All fields should be `true` (except timestamp).

---

## 🚨 Troubleshooting

### ChatGPT: "Could not fetch manifest"
- **Issue**: ngrok URL changed or bridge not running
- **Fix**: Run `.\quick-start.ps1` again, use new URL

### Claude: No tools icon appears
- **Issue**: Config file syntax error or wrong path
- **Fix**: Validate JSON with [jsonlint.com](https://jsonlint.com/), check file path

### Bridge Shows "backend_sse: false"
- **Issue**: MCP backend not responding
- **Fix**: 
  ```powershell
  cd C:\GPT\Version_8\echo-bridge
  .\quick-start.ps1
  ```

### ngrok URL Changes Every Restart
- **Issue**: Free ngrok tier assigns random URLs
- **Solution**: Set up **Named Cloudflare Tunnel** (see `README.md` section on "Named Tunnel")

---

## 📚 Next Steps

After successful connection:
1. **Explore `/panel`** - Real-time metrics and logs
2. **Run tests** - `pytest tests/` or `node tools/sse_smoke.mjs`
3. **Harden bridge** - See `CONNECTOR_SETUP.md` section on "Production Readiness"
4. **Start Toobix Universe** - Long-term federated platform (see vision doc)

---

## 🎯 Production Readiness Checklist

Before heavy use or public release:

- [ ] Move DB init to FastAPI lifespan (idempotent)
- [ ] Implement real `/healthz` with DB probe
- [ ] Add `/seed` endpoint for demo data
- [ ] Set up **Named Cloudflare Tunnel** (stable domain)
- [ ] Enable structured logging (JSON + request IDs)
- [ ] Add global exception handler (consistent error format)
- [ ] Write comprehensive test suite (>80% coverage)
- [ ] Set up CI/CD (GitHub Actions)
- [ ] Add rate limiting (per-IP or per-connector)
- [ ] Implement authentication (if needed)

---

**Questions?** Check the main `README.md` or open an issue in the repo.
