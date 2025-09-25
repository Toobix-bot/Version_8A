from fastmcp import FastMCP

from .services.memory_service import search as fts_search, get_chunk
from .services.fs_service import read_file

mcp = FastMCP("Echo Bridge", auth=None)  # lokal ohne Auth


@mcp.tool(
    name="search",
    # FastMCP in this environment expects schema under 'output_schema';
    # keep the intended input contract in the function signature and docstring.
    output_schema={"type": "object", "properties": {"results": {"type": "array"}, "content": {"type": "array"}}},
)
def search_tool(query: str, k: int = 5):
    """Structured search for documents using local FTS5 index."""
    hits = fts_search(query, k)
    results = []
    for h in hits:
        results.append({
            "id": str(h.id),
            "title": h.title or "",
            "url": f"mcp://chunk/{h.id}",
            "snippet": h.snippet,
        })
    # Also provide MCP-friendly content array (type=text snippets)
    content = [{"type": "search_results", "results": results}]
    return {"results": results, "content": content}


@mcp.tool(
    name="fetch",
    output_schema={"type": "object", "properties": {"id": {"type": "string"}, "title": {"type": "string"}, "content": {"type": "array"}, "metadata": {"type": "object"}}},
)
def fetch_tool(id: str):
    """Fetch full content by chunk id (or mcp://chunk/<id> url)."""
    # accept both raw id and mcp://chunk/<id>
    if id.startswith("mcp://chunk/"):
        _id = id.split("/")[-1]
    else:
        _id = id
    try:
        cid = int(_id)
    except Exception:
        return {"error": "invalid id"}
    c = get_chunk(cid)
    if not c:
        return {"error": "not found"}
    content = [{"type": "text", "text": c.text}]
    metadata = {"id": str(c.id), "title": c.title or ""}
    return {"id": str(c.id), "title": c.title or "", "content": content, "metadata": metadata}


@mcp.tool(
    name="list_resources",
    output_schema={"type": "object", "properties": {"resources": {"type": "array"}}},
)
def list_resources(q: str | None = None):
    """List available chunk resources (used for source activation)."""
    # Simple listing: return recent chunks or search results if q provided
    from .services.memory_service import search as _search

    items = []
    if q:
        hits = _search(q, 20)
    else:
        # fallback: show latest by id
        # naive direct DB access
        from .db import get_conn

        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT id, doc_title FROM chunks ORDER BY id DESC LIMIT 20")
        rows = cur.fetchall()
        hits = []
        for r in rows:
            class H: pass
            h = H()
            h.id = r["id"]
            h.title = r["doc_title"]
            h.snippet = ""
            hits.append(h)

    for h in hits:
        items.append({"id": str(h.id), "title": h.title or "", "url": f"mcp://chunk/{h.id}"})
    return {"resources": items}


@mcp.tool(
    name="open_resource",
    output_schema={"type": "object", "properties": {"id": {"type": "string"}, "title": {"type": "string"}, "content": {"type": "array"}}},
)
def open_resource(id: str):
    # reuse fetch
    return fetch_tool(id)

