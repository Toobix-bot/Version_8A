#!/usr/bin/env sh
set -e

echo "Starting ECHO Bridge container"

# Start MCP server (background)
echo "Starting MCP on :3337"
nohup /opt/venv/bin/python /app/run_mcp_http.py --host 0.0.0.0 --port 3337 > /var/log/mcp.log 2>&1 &

sleep 1

echo "Starting Bridge (uvicorn) on :3333"
exec /opt/venv/bin/uvicorn echo_bridge.main:app --host 0.0.0.0 --port 3333
