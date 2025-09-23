import asyncio
import os
import sys
from typing import Tuple

# Ensure this folder (which contains the echo_bridge package) is importable
sys.path.insert(0, os.path.dirname(__file__))

from echo_bridge.mcp_setup import mcp


def parse_host_port(argv: list[str]) -> Tuple[str, int]:
    host = os.environ.get("BIND_HOST", "127.0.0.1")
    port_str = os.environ.get("BIND_PORT", "3337")
    # simple CLI parsing: --host 0.0.0.0 --port 3337
    i = 0
    while i < len(argv):
        if argv[i] == "--host" and i + 1 < len(argv):
            host = argv[i + 1]
            i += 2
            continue
        if argv[i] == "--port" and i + 1 < len(argv):
            port_str = argv[i + 1]
            i += 2
            continue
        i += 1
    try:
        port = int(port_str)
    except Exception:
        port = 3337
    return host, port


if __name__ == "__main__":
    # Standalone FastMCP Streamable HTTP server (configurable host/port) under /mcp
    host, port = parse_host_port(sys.argv[1:])
    asyncio.run(
        mcp.run_http_async(
            transport="http",
            host=host,
            port=port,
            path="/mcp",
            stateless_http=True,
            log_level="info",
        )
    )
