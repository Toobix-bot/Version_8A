import asyncio
import os
import sys

# Ensure this folder (which contains the echo_bridge package) is importable
sys.path.insert(0, os.path.dirname(__file__))

from echo_bridge.mcp_setup import mcp

if __name__ == "__main__":
    # Standalone FastMCP Streamable HTTP server on 127.0.0.1:3337 under /mcp
    asyncio.run(
        mcp.run_http_async(
            transport="http",
            host="127.0.0.1",
            port=3337,
            path="/mcp",
            log_level="info",
        )
    )
