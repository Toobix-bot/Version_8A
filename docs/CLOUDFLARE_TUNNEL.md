Cloudflare Tunnel (named) — setup guide

This document explains how to create a persistent Cloudflare Tunnel (named tunnel)
and use it to expose your local `echo-bridge` (listening on 127.0.0.1:3333) under
a stable hostname like `mcp.example.com`.

Prerequisites
- A Cloudflare account with the target domain added as a zone.
- Cloudflare API token or owner account access (optional but helpful for automation).
- Administrator access to your Windows machine to install services.

High-level steps
1. Install `cloudflared` locally
2. Authenticate `cloudflared` with your Cloudflare account (login)
3. Create a named tunnel
4. Route DNS for the chosen hostname to the tunnel
5. Create a `cloudflared` config and install the tunnel as a Windows service
6. Update your repository manifests (OpenAPI & ChatGPT tool manifest) to the stable hostname

Commands (copy/paste into an elevated PowerShell shell).

# Install / download cloudflared (example)
# Download the binary and place into the repo root or somewhere on PATH
Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile .\cloudflared.exe

# Login (opens browser to authorize)
.\cloudflared.exe tunnel login

# Create a named tunnel
.\cloudflared.exe tunnel create echo-bridge

# Route DNS (automatic if you have zone permissions):
.\cloudflared.exe tunnel route dns echo-bridge mcp.example.com

# Example config file: ./cloudflared/echo-bridge.yml
# ---
# tunnel: echo-bridge
# credentials-file: C:\Users\<you>\.cloudflared\<tunnel-id>.json
# ingress:
#   - hostname: mcp.example.com
#     service: http://127.0.0.1:3333
#   - service: http_status:404

# Install as a Windows service (Admin)
.\cloudflared.exe service install --config .\cloudflared\echo-bridge.yml

# Or run manually for testing
.\cloudflared.exe tunnel run echo-bridge --config .\cloudflared\echo-bridge.yml

Updating repository manifests
- Update `public/openapi.json`, `public/chatgpt_tool_manifest.json`, and `docs/*` to use your new stable hostname, for example:
  https://mcp.example.com/public/openapi.json
  https://mcp.example.com/public/chatgpt_tool_manifest.json

- Commit and push changes to your repository. If you host `docs/` via GitHub Pages, make sure `docs/` is on the branch that serves Pages (typically `main`) and the Pages setting is enabled.

Notes & Troubleshooting
- If `cloudflared tunnel route dns` fails due to account permissions, create a CNAME record in the Cloudflare dashboard pointing your hostname to the target shown by `cloudflared tunnel create` (something like `<tunnel-id>.<region>.cfargotunnel.com`).
- Allow DNS propagation a few minutes.
- Ensure your local bridge is reachable at http://127.0.0.1:3333 before starting the tunnel.
- After the tunnel is running, verify:
  - https://mcp.example.com/public/openapi.json returns JSON (content-type application/json)
  - https://mcp.example.com/mcp returns Content-Type text/event-stream (SSE)

If you want, I can update the manifests in the repo to a chosen stable hostname after you provide it, or guide you through the steps interactively.
