from fastmcp import FastMCP

mcp = FastMCP("Echo Bridge", auth=None)  # lokal ohne Auth

@mcp.tool()
def echo_search(q: str, limit: int = 10):
    return {"results": []}  # später echte FTS5-Suche einbauen
