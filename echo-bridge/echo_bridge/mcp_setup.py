from fastmcp import FastMCP

from .services.memory_service import search as fts_search, get_chunk
from .services.fs_service import read_file

mcp = FastMCP("Echo Bridge", auth=None)  # lokal ohne Auth


@mcp.tool(
    name="search",
    input_schema={"type": "object", "properties": {"query": {"type": "string"}, "k": {"type": "integer"}}, "required": ["query"]},
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
    return {"results": results}


@mcp.tool(
    name="fetch",
    input_schema={"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
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
    return {"id": str(c.id), "title": c.title or "", "text": c.text}

