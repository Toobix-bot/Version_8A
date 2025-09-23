import asyncio
import os
import sys
from typing import Tuple

# Ensure echo_bridge package (inside echo-bridge folder) is importable when run from repo root
repo_root = os.path.dirname(__file__)
echo_bridge_dir = os.path.join(repo_root, "echo-bridge")
if echo_bridge_dir not in sys.path:
    sys.path.insert(0, echo_bridge_dir)

from echo_bridge.mcp_setup import mcp


def parse_host_port(argv: list[str]) -> Tuple[str, int]:
    host = os.environ.get("BIND_HOST", "127.0.0.1")
    port_str = os.environ.get("BIND_PORT", "3337")
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
    host, port = parse_host_port(sys.argv[1:])
    asyncio.run(
        mcp.run_http_async(
            transport="http",
            host=host,
            port=port,
            path="/mcp",
            log_level="info",
        )
    )
