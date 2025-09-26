from fastmcp import FastMCP

from .services.memory_service import search as fts_search, get_chunk
from .services.fs_service import read_file
from .services.memory_service import add_chunks

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


# New helper tools for Project-ECHO playground


@mcp.tool(name="echo_search", output_schema={"type": "object"})
def echo_search_tool(query: str | None = None, k: int = 5):
    """Search tool exposed as 'echo_search' using (query, k) to match the 'search' tool naming.
    This avoids an extra nested 'arguments' property in the input schema.
    """
    q = query or ""
    try:
        k = int(k)
    except Exception:
        k = 5
    hits = fts_search(q, k)
    results = [{"id": str(h.id), "title": h.title or "", "snippet": h.snippet} for h in hits]
    return {"results": results}


@mcp.tool(name="echo_ingest", output_schema={"type": "object"})
def echo_ingest_tool(source: str, title: str | None = None, text: str | None = None, tags: list[str] | None = None):
    """Ingest tool exposed as 'echo_ingest' with explicit signature for source/title/text/tags.
    Accepts direct fields (source, title, text, tags) so clients don't need to nest under 'arguments'.
    """
    texts = [text] if text else []
    meta = {"tags": tags} if tags else {}
    added = add_chunks(source, title, texts, meta)
    return {"added": added}


# echo_generate tool: expose the /generate behavior via MCP tools
try:
    # Prefer using the API module if present
    from apps.api.main import build_user_prompt, GROQ_API_KEY, build_system_prompt
    from apps.api.main import fetch_chunk as api_fetch_chunk
    _HAS_API = True
except Exception:
    _HAS_API = False


@mcp.tool(name="echo_generate", output_schema={"type": "object"})
def echo_generate_tool(prompt: str, contextIds: list[str] | None = None, model: str | None = None, temperature: float | None = None, max_tokens: int | None = None):
    """Generate using Groq (or fallback) — mirrors the /generate endpoint."""
    # Simple implementation: fetch contexts, build messages, call groq
    contexts = []
    if contextIds:
        for cid in contextIds[:8]:
            try:
                if _HAS_API:
                    contexts.append(api_fetch_chunk(cid))
                else:
                    # local fetch via memory service
                    c = get_chunk(int(cid))
                    if c:
                        contexts.append({"id": str(c.id), "title": c.title or "", "content": [{"type": "text", "text": c.text}]})
            except Exception:
                pass

    # Build messages
    if _HAS_API:
        messages = build_user_prompt(prompt, contexts)
    else:
        # minimal builder
        parts = []
        for c in contexts:
            txt = "".join(t.get("text", "") for t in c.get("content", []) if t.get("type") == "text")
            parts.append(f"# {c.get('title','')}\n{txt[:2000]}")
        ctx_block = "\n\n".join(parts)
        messages = [{"role": "system", "content": "Du bist der Erzähler/Assistent."}, {"role": "user", "content": f"Benutzeranfrage:\n{prompt}\n\n---\nKontext:\n{ctx_block}" if parts else prompt}]

    # Call groq SDK if available
    try:
        from groq import Groq
        key = None
        try:
            key = GROQ_API_KEY if _HAS_API else None
        except Exception:
            key = None
        if key:
            client = Groq(api_key=key)
            mdl = model or ("moonshotai/kimi-k2-instruct")
            resp = client.chat.completions.create(model=mdl, messages=messages, temperature=temperature or 0.6, max_tokens=max_tokens or 800)
            text = resp.choices[0].message.content
        else:
            text = "(groq not configured) " + prompt[:400]
    except Exception:
        text = "(groq call failed) " + prompt[:200]

    sources = [{"id": c.get("id"), "title": c.get("title")} for c in contexts]
    return {"text": text, "sources": sources}

