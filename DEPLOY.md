# Deployment & local tunneling

Docker (build & run):

```bash
docker build -t echo-bridge:latest .
docker run -e API_KEY=yourkey -p 3333:3333 -p 3337:3337 echo-bridge:latest
```

After the container starts, the MCP will be available on port 3337 and the Bridge on port 3333.

Expose locally with ngrok (example):

```powershell
# Expose MCP
ngrok http 3337
# Or expose the bridge endpoint directly
ngrok http 3333

# Get the public URL
$t = Invoke-RestMethod -Uri http://127.0.0.1:4040/api/tunnels
$t.tunnels | Where-Object { $_.public_url -like 'https:*' } | Select-Object -First 1 -ExpandProperty public_url
```

Notes
- For production, deploy to a VM with a proper TLS cert and restrict CORS/allowed origins.
- If you enable `API_KEY`, configure your tool registration to send the `X-API-Key` header.