from typing import Dict, Any

from fastmcp import FastMCP


# FastMCP server instance to be mounted into FastAPI
mcp = FastMCP("Echo Bridge")


@mcp.tool()
def echo_search(q: str, limit: int = 10) -> Dict[str, Any]:
    """
    Suche in der lokalen ECHO-Datenbank nach dem String `q`.
    Rückgabe-Struktur: {"results": [{"id": str, "snippet": str}]}
    (Platzhalter – binde unten in main.py an eure echte FTS5-Suche an.)
    """
    # TODO: Replace with real SQLite FTS5 query results
    return {"results": []}
