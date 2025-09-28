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
# Ensure the main app module is imported so DB initialization (init_db) runs
# when the MCP server is started standalone. This sets the internal _DB_PATH
# used by memory_service.get_conn().
try:
    # Importing has side-effects: load settings and call init_db(path)
    import echo_bridge.main  # type: ignore
except Exception:
    # If import fails, continue — the MCP server may still work if DB is
    # initialized elsewhere. We don't want startup to hard-fail here.
    pass


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
    # To ensure external probes (GET with Accept: text/event-stream) see
    # a real SSE handshake we run the FastMCP HTTP server on a backend port
    # and expose a tiny aiohttp-based proxy on the requested (public) port
    # which streams responses back to the client. This avoids cases where
    # tunnels or probes receive HTML (ngrok landing) and makes activation
    # more reliable for ChatGPT Developer Tools.
    import aiohttp
    from aiohttp import web

    backend_port = port + 1

    async def start_backend():
        await mcp.run_http_async(
            transport="http",
            host="127.0.0.1",
            port=backend_port,
            path="/mcp",
            stateless_http=True,
            log_level="info",
        )

    async def proxy_handler(request: web.Request) -> web.StreamResponse:
        # Build target URL on backend
        target_url = f"http://127.0.0.1:{backend_port}{request.rel_url}"
        # Copy headers but let the client control Accept
        headers = {k: v for k, v in request.headers.items()}

        session_timeout = aiohttp.ClientTimeout(total=None)
        async with aiohttp.ClientSession(timeout=session_timeout) as session:
            if request.method == "GET":
                # Stream backend response to client
                async with session.get(target_url, headers=headers) as resp:
                    # Prepare streaming response with same content-type
                    sr = web.StreamResponse(status=resp.status, headers={"Content-Type": resp.headers.get("Content-Type", "application/octet-stream")})
                    await sr.prepare(request)
                    async for chunk in resp.content.iter_chunked(1024):
                        await sr.write(chunk)
                    await sr.write_eof()
                    return sr
            else:
                body = await request.read()
                async with session.request(request.method, target_url, data=body, headers=headers) as resp:
                    sr = web.StreamResponse(status=resp.status, headers={"Content-Type": resp.headers.get("Content-Type", "application/octet-stream")})
                    await sr.prepare(request)
                    async for chunk in resp.content.iter_chunked(1024):
                        await sr.write(chunk)
                    await sr.write_eof()
                    return sr

    async def start_proxy():
        app = web.Application()
        # catch-all route so /mcp and related paths are proxied
        app.router.add_route('*', '/{tail:.*}', proxy_handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()
        # keep running until cancelled
        while True:
            await asyncio.sleep(3600)

    async def main():
        # Run backend and proxy concurrently
        backend_task = asyncio.create_task(start_backend())
        proxy_task = asyncio.create_task(start_proxy())
        await asyncio.gather(backend_task, proxy_task)

    asyncio.run(main())
