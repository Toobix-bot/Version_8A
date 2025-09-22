from __future__ import annotations

"""
FastMCP-based MCP server exposing echo-bridge tools.

Transports:
- STDIO: python -m echo_bridge.mcp_fastmcp
- HTTP (SSE/WS): python -m echo_bridge.mcp_fastmcp http --host 127.0.0.1 --port 3334 --path /mcp

This module does not alter the FastAPI app; it's a sidecar MCP server suitable
for ChatGPT Developer Mode connectors (ws://127.0.0.1:3334/mcp).
"""

from typing import Any, Optional
import argparse
import os

from fastmcp import FastMCP
from fastmcp.server.auth.auth import (
    RemoteAuthProvider,
    TokenVerifier,
)

from .main import settings
from .services.memory_service import search as mem_search, add_chunks
from .services.fs_service import list_dir as fs_list, read_file as fs_read
from .services.actions_service import dispatch as actions_dispatch
from .ai.brain import Policy

# Default server used for tool registration and tests (no auth by default)
mcp: FastMCP = FastMCP("ECHO Bridge MCP")


@mcp.tool
def memory_search(query: str, k: int = 5) -> list[dict[str, Any]]:
    """Full-text search over local memory (SQLite FTS5). Returns ranked hits.

    Arguments:
    - query: search string
    - k: max number of hits (default 5)
    """
    hits = mem_search(query, k)
    return [h.model_dump() for h in hits]


@mcp.tool
def memory_add(
    source: str,
    title: Optional[str] = None,
    texts: list[str] = [],
    meta: Optional[dict[str, Any]] = None,
    key: Optional[str] = None,
) -> dict[str, int]:
    """Insert text chunks into local memory. Requires bridge key for writes.

    Arguments:
    - source: logical source name
    - title: optional title
    - texts: list of texts to ingest
    - meta: optional metadata
    - key: X-Bridge-Key for authorization
    """
    if not key or key != settings.bridge_key:
        raise PermissionError("Missing or invalid key")
    n = add_chunks(source, title, texts, meta)
    return {"inserted": n}


@mcp.tool
def fs_list_tool(subdir: Optional[str] = None) -> dict[str, Any]:
    """List files within the sandboxed workspace directory."""
    items = fs_list(settings.workspace_dir, subdir)
    return {"items": items}


@mcp.tool
def fs_read_tool(path: str) -> dict[str, Any]:
    """Read a file from the workspace (text only)."""
    text = fs_read(settings.workspace_dir, path)
    return {"path": path, "text": text}


@mcp.tool
def actions_run(
    command: str,
    args: dict[str, Any] | None = None,
    tier_mode: Optional[str] = None,
    key: Optional[str] = None,
) -> dict[str, Any]:
    """Run a whitelisted action. Writes require bridge key.

    Common commands:
    - memory.add/tag/group
    - journal.summarize
    - memory.auto_tag (preview/confirm)
    - game.new/choose/describe
    """
    args = args or {}
    write_cmds = {"memory.add", "memory.tag", "memory.group", "game.new", "game.choose"}
    if command in write_cmds and (not key or key != settings.bridge_key):
        raise PermissionError("Missing or invalid key for write")
    policy = Policy(s1=settings.ai_s1, s2=settings.ai_s2, s3=settings.ai_s3)
    result = actions_dispatch(command, args, policy, tier_mode=tier_mode, tiers_cfg=settings.ai_tiers)
    return result


def _parse_scopes(scopes_csv: Optional[str]) -> Optional[list[str]]:
    scopes_csv = (scopes_csv or "").strip()
    if not scopes_csv:
        return None
    return [s.strip() for s in scopes_csv.split(",") if s.strip()]


def _resolve_auth(
    provider: str | None,
    base_url: str,
    issuer_url: Optional[str] = None,
    service_doc_url: Optional[str] = None,
    required_scopes_csv: Optional[str] = None,
) -> Optional[RemoteAuthProvider]:
    """Return a RemoteAuthProvider (generic OAuth/OIDC resource protection) or None.

    This secures the MCP server as a protected resource that accepts bearer tokens
    issued by your authorization server (issuer_url). No client registration is performed.
    """
    name = (provider or "").strip().lower()
    if not name or name == "none":
        return None
    if name != "oauth":
        print(f"[MCP] Unknown auth provider '{name}'; supported: 'oauth'. Continuing without auth.")
        return None
    if not issuer_url:
        print("[MCP] OAuth requested but --issuer-url missing; continuing without auth")
        return None

    required_scopes = _parse_scopes(required_scopes_csv)

    try:
        verifier = TokenVerifier(base_url=issuer_url, required_scopes=required_scopes)
        return RemoteAuthProvider(
            token_verifier=verifier,
            authorization_servers=[issuer_url],  # type: ignore[arg-type]
            base_url=base_url,  # type: ignore[arg-type]
            resource_name="ECHO Bridge MCP",
            resource_documentation=service_doc_url,  # type: ignore[arg-type]
        )
    except Exception as e:
        print(f"[MCP] Failed to initialize OAuth (RemoteAuthProvider): {e}; continuing without auth")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ECHO Bridge MCP server")
    parser.add_argument(
        "transport",
        nargs="?",
        default="http",
        choices=["stdio", "http", "sse"],
        help="Transport protocol (default: http)",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3334)
    parser.add_argument("--path", default="/mcp")
    # Auth options (optional)
    parser.add_argument("--auth", choices=["none", "oauth"], default=os.getenv("ECHO_MCP_AUTH", "none"))
    parser.add_argument("--base-url", default=os.getenv("ECHO_MCP_BASE_URL"))
    parser.add_argument("--issuer-url", default=os.getenv("ECHO_MCP_OAUTH_ISSUER_URL"))
    parser.add_argument("--doc-url", default=os.getenv("ECHO_MCP_OAUTH_DOC_URL"))
    parser.add_argument("--scopes", default=os.getenv("ECHO_MCP_OAUTH_SCOPES"))  # comma-separated
    args = parser.parse_args()

    base_url = args.base_url or f"http://{args.host}:{args.port}"

    auth_provider = _resolve_auth(
        args.auth,
        base_url=base_url,
        issuer_url=args.issuer_url,
        service_doc_url=args.doc_url,
        required_scopes_csv=args.scopes,
    )
    server = mcp
    if auth_provider:
        print(f"[MCP] Starting with OAuth provider @ issuer: {args.issuer_url} base: {base_url}")
    server = FastMCP("ECHO Bridge MCP", auth=auth_provider)
    # Mount existing tools/resources/prompts without a prefix
    server.mount(mcp)

    if args.transport == "stdio":
        server.run(transport="stdio")
    elif args.transport == "sse":
        server.run(transport="sse", host=args.host, port=args.port)
    else:
        server.run(transport="http", host=args.host, port=args.port, path=args.path)


if __name__ == "__main__":
    main()
