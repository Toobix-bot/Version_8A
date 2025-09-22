from fastmcp.server import FastMCP
from fastapi import FastAPI
import uvicorn

mcp = FastMCP("Echo Bridge (min)", auth=None)  # keine Auth

@mcp.tool()
def echo_search(q: str, limit: int = 5):
    """Dummy-Tool, damit /mcp Tools listen kann."""
    return {"results": [{"text": q, "rank": i} for i in range(limit)]}

app = FastAPI()

# Create the ASGI app for FastMCP and mount it under /mcp
sub_app = mcp.http_app(path="/")
app.mount("/mcp", sub_app, name="mcp")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=3336)
