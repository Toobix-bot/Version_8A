from __future__ import annotations

import json
import os
import logging
import asyncio
import anyio
from pathlib import Path
from time import perf_counter
from typing import Any, Optional, cast, Awaitable, Callable, AsyncGenerator, Dict, List
from urllib.parse import urlparse, urlunparse

import yaml
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Body
from fastapi import Request
from starlette.responses import Response

from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
import httpx
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
try:
    # FastMCP FastAPI integration (optional)
    from fastmcp.fastapi import mount_mcp  # type: ignore
except Exception:
    mount_mcp = None  # type: ignore
from pydantic import BaseModel

from .db import init_db, get_conn
from .services.actions_service import ActionError, PreconditionFailed, dispatch
from .ai.brain import Policy
from .soul.loader import load_soul
from .soul.state import get_soul, init_soul
from .mcp_server import router as mcp_router
from .services.fs_service import FSError, list_dir, read_file
from .services.memory_service import Chunk, Hit, add_chunks, get_chunk, search
from .mcp_server import register_mcp
from .mcp_setup import mcp as mcp_server


class Settings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 3333
    bridge_key: Optional[str] = "SECRET"
    db_path: Path
    workspace_dir: Path
    ai_s1: bool = True
    ai_s2: bool = True
    ai_s3: bool = False
    ai_tiers: dict[str, dict[str, object]] = {
        "under": {"enabled": True, "timeout_ms": 400, "allow_llm": False},
        "core": {"enabled": True, "timeout_ms": 800, "allow_llm": False},
        "over": {"enabled": True, "timeout_ms": 1600, "allow_llm": False},
    }


def load_settings() -> Settings:
    cfg_path = Path(__file__).resolve().parent.parent / "config.yaml"
    # Fallback if moved, also try repo root
    if not cfg_path.exists():
        cfg_path = Path.cwd() / "config.yaml"
    data: dict[str, Any] = {}
    if cfg_path.exists():
        with cfg_path.open("r", encoding="utf-8") as f:
            loaded: Any = yaml.safe_load(f) or {}
            data = cast(dict[str, Any], loaded) if isinstance(loaded, dict) else {}
    server: dict[str, Any] = data.get("server", {}) if isinstance(data.get("server", {}), dict) else {}
    database: dict[str, Any] = data.get("database", {}) if isinstance(data.get("database", {}), dict) else {}
    workspace: dict[str, Any] = data.get("workspace", {}) if isinstance(data.get("workspace", {}), dict) else {}
    ai: dict[str, Any] = data.get("ai", {}) if isinstance(data.get("ai", {}), dict) else {}
    settings = Settings(
        host=server.get("host", "127.0.0.1"),
        port=int(server.get("port", 3333)),
        bridge_key=server.get("bridge_key", "SECRET"),
        db_path=Path(database.get("path", "./echo-bridge/data/bridge.db")),
        workspace_dir=Path(workspace.get("dir", "./echo-bridge/workspace")),
        ai_s1=bool(ai.get("s1", True)),
        ai_s2=bool(ai.get("s2", True)),
        ai_s3=bool(ai.get("s3", False)),
        ai_tiers=ai.get("tiers", {
            "under": {"enabled": True, "timeout_ms": 400, "allow_llm": False},
            "core": {"enabled": True, "timeout_ms": 800, "allow_llm": False},
            "over": {"enabled": True, "timeout_ms": 1600, "allow_llm": False},
        }),
    )
    return settings


settings = load_settings()
# DB and soul initialization moved to lifespan handler for proper startup error handling


class Health(BaseModel):
    status: str


class IngestRequest(BaseModel):
    source: str
    title: Optional[str] = None
    texts: list[str]
    tags: Optional[list[str]] = None
    meta: Optional[dict[str, Any]] = None


class IngestResponse(BaseModel):
    added: int


class SearchResponse(BaseModel):
    hits: list[Hit]


class ChunkResponse(Chunk):
    pass


class ActionRequest(BaseModel):
    command: str
    args: dict[str, Any]
    tier_mode: Optional[str] = None
    confirm: Optional[bool] = None


class ActionResponse(BaseModel):
    ok: bool
    result: dict[str, Any]


def get_api_key(x_bridge_key: Optional[str] = Header(default=None, alias="X-Bridge-Key")) -> None:
    # Only required for write endpoints; the dependency is attached only there.
    # Use ECHO_BRIDGE_API_KEY if set, otherwise fall back to API_KEY or settings.bridge_key
    expected = os.environ.get("ECHO_BRIDGE_API_KEY") or os.environ.get("API_KEY") or settings.bridge_key
    if not x_bridge_key or x_bridge_key != expected:
        raise HTTPException(status_code=401, detail="Missing or invalid X-Bridge-Key")


logger = logging.getLogger("echo_bridge")
handler = logging.StreamHandler()


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # add known structured fields if present
        for k in ("path", "method", "duration_ms", "outcome"):
            if hasattr(record, k):
                payload[k] = getattr(record, k)
        return json.dumps(payload, ensure_ascii=False)


handler.setFormatter(JsonLogFormatter())
logger.addHandler(handler)
logger.setLevel(logging.INFO)

## metrics moved below after app creation


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan handler: run startup tasks previously registered with
    @app.on_event("startup"). This centralizes startup logic and is
    the recommended modern FastAPI pattern.
    """
    # Run startup routines (they are defined further down in the module).
    
    # 1. Initialize database (idempotent, with error handling)
    try:
        logger.info("Initializing workspace and database...")
        settings.workspace_dir.mkdir(parents=True, exist_ok=True)
        settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        init_db(settings.db_path)
        logger.info(f"Database initialized at {settings.db_path}")
    except Exception as e:
        logger.exception(f"CRITICAL: Database initialization failed: {e}")
        raise  # Fatal error, app should not start without DB
    
    # 2. Initialize soul system (optional, non-fatal)
    try:
        logger.info("Loading soul system...")
        soul_root = Path(__file__).resolve().parent.parent
        soul = load_soul(soul_root, timeline_path=Path("./echo-bridge/data/timeline.jsonl"))
        init_soul(soul)
        logger.info("Soul system loaded successfully")
    except Exception as e:
        logger.warning(f"Soul system initialization failed (non-fatal): {e}")
        # Continue without soul - this is optional functionality
    
    # 3. Generate public specs and manifests
    try:
        write_runtime_manifests()
    except Exception:
        logger.exception("write_runtime_manifests failed during startup")
    try:
        _on_startup_write_public_specs()
    except Exception:
        logger.exception("_on_startup_write_public_specs failed during startup")
    try:
        generate_public_specs_on_startup()
    except Exception:
        logger.exception("generate_public_specs_on_startup failed during startup")
    
    logger.info("Startup complete, app ready to serve requests")
    
    # Yield to run the app
    yield
    
    # Shutdown cleanup (if needed in future)
    logger.info("Shutting down gracefully...")


app = FastAPI(title="ECHO-BRIDGE", lifespan=lifespan)
# -----------------------------
# Simple in-process metrics (defined after app creation)
# -----------------------------
class Metrics:
    active_sse: int = 0
    started_sse: int = 0
    completed_sse: int = 0
    aborted_sse: int = 0
    started_post: int = 0
    active_post: int = 0
    completed_post: int = 0
    aborted_post: int = 0
    bytes_up_post: int = 0
    bytes_down_post: int = 0

    def snapshot(self) -> dict[str, dict[str, int]]:
        return {
            "sse": {
                "active": self.active_sse,
                "started": self.started_sse,
                "completed": self.completed_sse,
                "aborted": self.aborted_sse,
            },
            "post": {
                "active": self.active_post,
                "started": self.started_post,
                "completed": self.completed_post,
                "aborted": self.aborted_post,
                "bytes_up": self.bytes_up_post,
                "bytes_down": self.bytes_down_post,
            },
        }


metrics = Metrics()


@app.get("/metrics")
def metrics_endpoint() -> JSONResponse:  # type: ignore[misc]
    data = {
        "sse": {
            "active": metrics.active_sse,
            "started": metrics.started_sse,
            "completed": metrics.completed_sse,
            "aborted": metrics.aborted_sse,
        },
        "post": {
            "active": metrics.active_post,
            "started": metrics.started_post,
            "completed": metrics.completed_post,
            "aborted": metrics.aborted_post,
            "bytes_up": metrics.bytes_up_post,
            "bytes_down": metrics.bytes_down_post,
        },
    }
    return JSONResponse(content=data)
# Allow CORS for local testing and for ChatGPT/tool tooling. In production you
# should restrict origins to your hosted manifest / UI origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Ensure CORS headers are present for static/public/openapi endpoints and
# handle OPTIONS preflight for them. This complements CORSMiddleware in
# case a reverse-proxy or static file handler omits the headers.
@app.middleware("http")
async def ensure_cors_for_public(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    path = request.url.path or ""
    public_prefixes = ("/public", "/openapi.json", "/chatgpt_tool_manifest.json", "/mcp")
    should_apply = any(path.startswith(p) for p in public_prefixes)

    # Fast path: respond to OPTIONS preflights for guarded public endpoints
    if should_apply and request.method.upper() == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS,PUT,PATCH,DELETE",
            "Access-Control-Allow-Headers": "Authorization,Content-Type,X-API-Key,X-Bridge-Key",
        }
        return Response(status_code=200, headers=headers)

    resp = await call_next(request)

    if should_apply:
        # Always ensure these CORS headers are present for public endpoints.
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS,PUT,PATCH,DELETE"
        resp.headers["Access-Control-Allow-Headers"] = "Authorization,Content-Type,X-API-Key,X-Bridge-Key"

    return resp


def _public_read_protection_enabled() -> bool:
    """Return True when public/read endpoints should require X-API-Key.

    Controlled by the env var REQUIRE_X_API_KEY_FOR_PUBLIC. When enabled
    the header X-API-Key must match the API_KEY env var value.
    """
    return os.environ.get("REQUIRE_X_API_KEY_FOR_PUBLIC", "false").lower() in ("1", "true", "yes")


@app.middleware("http")
async def require_api_key_for_public_reads(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Optional middleware that enforces X-API-Key on a small set of public/read endpoints.

    This avoids accidentally exposing the generated manifest/openapi or the MCP proxy
    when the developer wants to gate them with the same API_KEY used for write endpoints.
    """
    try:
        if _public_read_protection_enabled():
            # Only guard read-style endpoints used by ChatGPT tooling
            path = request.url.path or ""
            guarded_prefixes = ("/public/", "/mcp")
            guarded_exact = ("/public/openapi.json", "/public/chatgpt_tool_manifest.json", "/openapi.json", "/chatgpt_tool_manifest.json", "/mcp/openapi.json")
            should_guard = False
            if any(path.startswith(p) for p in guarded_prefixes) or path in guarded_exact:
                # also allow health/debug endpoints for local inspection
                if not path.startswith("/health") and not path.startswith("/debug"):
                    should_guard = True

            if should_guard:
                # Use the same key resolution as get_api_key: prefer ECHO_BRIDGE_API_KEY,
                # fall back to API_KEY, then settings.bridge_key
                expected = os.environ.get("ECHO_BRIDGE_API_KEY") or os.environ.get("API_KEY") or settings.bridge_key
                # If no expected key configured, treat as unlocked
                if expected:
                    header = request.headers.get("x-api-key") or request.headers.get("X-API-Key")
                    if not header or header != expected:
                        return JSONResponse(status_code=401, content={"detail": "Missing or invalid X-API-Key"})
    except Exception:
        # On unexpected errors, fall through to normal handling so we don't block unrelated endpoints
        pass
    return await call_next(request)
public_dir = Path(__file__).resolve().parent.parent / "public"


def _load_json_file(p: Path):
    """Load a JSON file tolerantly, decoding BOM if present."""
    # Use utf-8-sig so files saved with a UTF-8 BOM are handled correctly.
    txt = p.read_text(encoding="utf-8-sig")
    return json.loads(txt)


def _get_public_base_url() -> Optional[str]:
    """Return PUBLIC_BASE_URL env var if set, otherwise None."""
    v = os.environ.get("PUBLIC_BASE_URL")
    if v:
        # normalize: strip trailing slash
        return v.rstrip("/")
    return None


def _replace_origin_in_string(s: str, new_origin: str) -> str:
    try:
        parsed = urlparse(s)
        if parsed.scheme and parsed.netloc:
            # keep path/query/fragment, replace scheme+netloc with new_origin
            new_parsed = urlparse(new_origin)
            rebuilt = urlunparse((new_parsed.scheme, new_parsed.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
            return rebuilt
    except Exception:
        pass
    return s


def _recursive_replace_origins(obj: Any, new_origin: str) -> Any:
    # Recursively walk JSON-like structure and replace string origins
    if isinstance(obj, dict):
        return {k: _recursive_replace_origins(v, new_origin) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_recursive_replace_origins(v, new_origin) for v in obj]
    if isinstance(obj, str):
        return _replace_origin_in_string(obj, new_origin)
    return obj


@app.get("/public/openapi.json")
def serve_openapi() -> JSONResponse:
    """Serve the public OpenAPI JSON with explicit application/json content-type."""
    p = public_dir / "openapi.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="openapi.json not found")
    try:
        data = _load_json_file(p)
        public = _get_public_base_url()
        if public:
            data = _recursive_replace_origins(data, public)
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS,PUT,PATCH,DELETE",
            "Access-Control-Allow-Headers": "Authorization,Content-Type,X-API-Key,X-Bridge-Key",
        }
        return JSONResponse(content=data, media_type="application/json", headers=headers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read openapi.json: {e}")


@app.get("/public/chatgpt_tool_manifest.json")
def serve_manifest() -> JSONResponse:
    """Serve the ChatGPT tool manifest with explicit application/json content-type."""
    p = public_dir / "chatgpt_tool_manifest.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="chatgpt_tool_manifest.json not found")
    try:
        data = _load_json_file(p)
        public = _get_public_base_url()
        if public:
            data = _recursive_replace_origins(data, public)
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS,PUT,PATCH,DELETE",
            "Access-Control-Allow-Headers": "Authorization,Content-Type,X-API-Key,X-Bridge-Key",
        }
        return JSONResponse(content=data, media_type="application/json", headers=headers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read chatgpt manifest: {e}")


## NOTE: Removed earlier duplicate /openapi.json and /chatgpt_tool_manifest.json route
## definitions to avoid FastAPI warnings about duplicate Operation IDs and
## conflicting path registrations. The canonical implementations now live
## further below (serve_top_openapi / serve_top_manifest) which include
## explicit CORS headers and generated-file fallbacks.


@app.middleware("http")
async def public_json_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    # Intercept requests for /public/*.json and serve them as JSONResponse
    # before the StaticFiles mount handles them. This guarantees application/json
    # content-type even when proxied by tunnels like ngrok.
    try:
        path = request.url.path
        if path.startswith("/public/") and path.lower().endswith(".json"):
            # Build the file path relative to public_dir (strip leading '/public/')
            rel = path[len("/public/"):]
            p = public_dir / rel
            if p.exists() and p.is_file():
                try:
                    data = _load_json_file(p)
                    headers = {
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "GET,POST,OPTIONS,PUT,PATCH,DELETE",
                        "Access-Control-Allow-Headers": "Authorization,Content-Type,X-API-Key,X-Bridge-Key",
                    }
                    return JSONResponse(content=data, media_type="application/json", headers=headers)
                except Exception as e:
                    headers = {
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "GET,POST,OPTIONS,PUT,PATCH,DELETE",
                        "Access-Control-Allow-Headers": "Authorization,Content-Type,X-API-Key,X-Bridge-Key",
                    }
                    return JSONResponse(status_code=500, content={"detail": f"Failed to read JSON: {e}"}, headers=headers)
    except Exception:
        # If anything goes wrong here, fall through to normal handling so we
        # don't block unrelated endpoints.
        pass
    return await call_next(request)


app.mount(
    "/_public_static",
    StaticFiles(directory=str(Path(__file__).resolve().parent.parent / "public"), html=True),
    name="public_static",
)


@app.middleware("http")
async def asgi_public_cors_middleware(request: Request, call_next):
    """ASGI middleware to ensure CORS headers on /public responses and
    to answer preflight OPTIONS requests early.
    """
    path = request.url.path or ""
    # paths we care about
    public_prefix = "/public"
    top_openapi = "/openapi.json"
    top_manifest = "/chatgpt_tool_manifest.json"

    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS,PUT,PATCH,DELETE",
        "Access-Control-Allow-Headers": "Authorization,Content-Type,X-API-Key,X-Bridge-Key",
        # allow credentials when needed
        "Access-Control-Allow-Credentials": "true",
    }

    # Handle OPTIONS preflight for /public and top-level handlers
    if request.method.upper() == "OPTIONS" and (
        path.startswith(public_prefix) or path in (top_openapi, top_manifest)
    ):
        return Response(status_code=204, headers=cors_headers)

    # Call the downstream app and then attach headers if the path matches
    response = await call_next(request)
    if path.startswith(public_prefix) or path in (top_openapi, top_manifest):
        for k, v in cors_headers.items():
            # set only if not present already
            if k not in response.headers:
                response.headers[k] = v
    return response


# Serve top-level openapi and chatgpt manifest with explicit CORS headers so
# external clients (ChatGPT Actions) always get JSON + CORS even if the
# StaticFiles mount bypasses middleware ordering.
@app.get("/openapi.json")
def serve_top_openapi() -> JSONResponse:
    p = public_dir / "openapi.json"
    if not p.exists():
        # fall back to generated one
        p = public_dir / "openapi.generated.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="openapi.json not found")
    try:
        data = _load_json_file(p)
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS,PUT,PATCH,DELETE",
            "Access-Control-Allow-Headers": "Authorization,Content-Type,X-API-Key,X-Bridge-Key",
        }
        public = _get_public_base_url()
        if public:
            data = _recursive_replace_origins(data, public)
        return JSONResponse(content=data, media_type="application/json", headers=headers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read openapi.json: {e}")


@app.get("/chatgpt_tool_manifest.json")
def serve_top_manifest() -> JSONResponse:
    p = public_dir / "chatgpt_tool_manifest.json"
    if not p.exists():
        p = public_dir / "chatgpt_tool_manifest.generated.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="chatgpt_tool_manifest.json not found")
    try:
        data = _load_json_file(p)
        public = _get_public_base_url()
        if public:
            data = _recursive_replace_origins(data, public)
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS,PUT,PATCH,DELETE",
            "Access-Control-Allow-Headers": "Authorization,Content-Type,X-API-Key,X-Bridge-Key",
        }
        return JSONResponse(content=data, media_type="application/json", headers=headers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read chatgpt manifest: {e}")


@app.get("/public/chatgpt_tool_manifest.json")
def serve_public_manifest() -> JSONResponse:
    # Serve the same content for /public/... path to override StaticFiles and guarantee CORS
    p = public_dir / "chatgpt_tool_manifest.json"
    if not p.exists():
        p = public_dir / "chatgpt_tool_manifest.generated.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="chatgpt_tool_manifest.json not found")
    try:
        data = _load_json_file(p)
        public = _get_public_base_url()
        if public:
            data = _recursive_replace_origins(data, public)
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS,PUT,PATCH,DELETE",
            "Access-Control-Allow-Headers": "Authorization,Content-Type,X-API-Key,X-Bridge-Key",
            "Access-Control-Allow-Credentials": "true",
        }
        return JSONResponse(content=data, media_type="application/json", headers=headers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read public chatgpt manifest: {e}")


# DUPLICATE REMOVED - second definition commented out (canonical version exists at line ~360)
# @app.get("/public/openapi.json")
# def serve_public_openapi() -> JSONResponse:
#     ...


def write_runtime_manifests() -> None:
    """Generate runtime OpenAPI and ChatGPT manifest files under public/*.generated.json.

    This function writes generated files but intentionally does not overwrite
    the user's original files (`openapi.json`, `chatgpt_tool_manifest.json`).
    Generated files are written as `openapi.generated.json` and
    `chatgpt_tool_manifest.generated.json` for inspection and to help
    automated tooling when registering the connector.
    """
    try:
        pub_dir = Path(__file__).resolve().parent.parent / "public"
        pub_dir.mkdir(parents=True, exist_ok=True)

        # Build OpenAPI spec from dynamic builder
        try:
            spec = _build_dynamic_openapi_spec()
            gen_openapi = pub_dir / "openapi.generated.json"
            gen_openapi.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info("wrote generated openapi: %s", str(gen_openapi))
        except Exception as e:
            logger.warning("failed to build/write generated openapi: %s", e)

        # Build a simple ChatGPT manifest that points to the public openapi route
        try:
            public_base = _get_public_base_url()
            api_url = (public_base.rstrip('/') if public_base else '') + "/public/openapi.json" if public_base else "/public/openapi.json"
            manifest = {
                "schema_version": "v1",
                "name_for_human": "ECHO Bridge",
                "name_for_model": "echo_bridge",
                "description_for_human": "Suchen, Abrufen, und Generieren auf deiner ECHO-Wissensbasis.",
                "description_for_model": "Tools: /ingest, /search, /fetch, /generate. Use search→fetch to build context, then call generate. /resources lists stored chunks.",
                "auth": {"type": "none"},
                "api": {"type": "openapi", "url": api_url, "is_user_authenticated": False},
                "contact_email": "admin@example.com",
            }
            gen_manifest = pub_dir / "chatgpt_tool_manifest.generated.json"
            gen_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info("wrote generated manifest: %s", str(gen_manifest))
        except Exception as e:
            logger.warning("failed to build/write generated manifest: %s", e)
    except Exception:
        logger.exception("unexpected error while writing runtime manifests")

# Serve a small public UI for testing and interacting with the bridge.
static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static_ui")


@app.get("/ui", response_class=HTMLResponse)
def serve_ui() -> HTMLResponse:
    p = static_dir / "ui.html"
    if not p.exists():
        raise HTTPException(status_code=404, detail="ui.html not found")
    return HTMLResponse(content=p.read_text(encoding="utf-8"))


@app.post("/ui/generate")
async def ui_generate(request: Request):
    """Proxy endpoint used by the UI to POST to the bridge generate endpoint.
    It forwards the X-Bridge-Key header and JSON body to the existing bridge handler.
    """
    body = await request.body()
    headers = {}
    if "x-bridge-key" in request.headers:
        headers["X-Bridge-Key"] = request.headers["x-bridge-key"]
    # Forward to internal handler by calling the route function directly if available
    # Fallback: return the raw body to help debugging.
    try:
        # Direct import to avoid circulars; use FastAPI test client style call is avoided
        # to keep this simple and synchronous.
        from fastapi import responses

        # Construct a Response-like passthrough
        # If the bridge has a function exposed for generate, call it; otherwise return body
        return responses.PlainTextResponse(content=body, media_type="application/json")
    except Exception:
        return JSONResponse(status_code=500, content={"error": "failed to proxy generate"})

# Mount MCP under /mcp
mounted = False
if mount_mcp:
    # Some versions of fastmcp.fastapi.mount_mcp mount directly at /mcp which
    # shadows routes in this main app (like /mcp/openapi.json). To avoid that
    # unpredictable behavior we skip the helper and always use the http_app
    # approach below which mounts the MCP under /mcp_app and leaves /mcp/* for
    # the main bridge to serve (notably /mcp/openapi.json).
    logger.info("fastmcp.fastapi.mount_mcp available but intentionally skipped to preserve /mcp routes")

# Create FastMCP ASGI app and mount it under /mcp_app (stateless for embedding)
if not mounted:
    try:
        sub_app = mcp_server.http_app(path="/", stateless_http=True)
        # Wrap the MCP sub_app so we can serve a dynamic /openapi.json from the mounted app
        try:
            wrapper = FastAPI()

            @wrapper.get("/openapi.json")
            def mcp_openapi_inside() -> JSONResponse:
                try:
                    spec = _build_dynamic_openapi_spec()
                    return JSONResponse(content=spec)
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"Failed to build dynamic openapi: {e}")

            # Mount the MCP http_app under the wrapper at root, then expose it
            # at /mcp_app so the main application keeps ownership of /mcp/*
            wrapper.mount("/", sub_app)
            app.mount("/mcp_app", wrapper, name="mcp")
            logger.info("mounted MCP http_app under /mcp_app (wrapper provides /openapi.json)")
        except Exception:
            # Fallback to direct mount if wrapper fails
            app.mount("/mcp_app", sub_app, name="mcp")
            logger.info("mounted MCP http_app under /mcp_app (direct mount)")
    except Exception as e:
        logger.error(f"failed to mount mcp http_app fallback: {e}")


@app.middleware("http")
async def logging_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    start = perf_counter()
    outcome = "error"
    try:
        response = await call_next(request)  # type: ignore[no-any-return]
        outcome = "success" if response.status_code < 400 else "error"
    except Exception:
        outcome = "exception"
        raise
    finally:
        duration = perf_counter() - start
        logger.info(
            "request",
            extra={
                "path": request.url.path,
                "method": request.method,
                "duration_ms": int(duration * 1000),
                "outcome": outcome,
            },
        )
    return response


@app.get("/health", response_model=Health)
def health() -> Health:
    return Health(status="ok")


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    """
    Comprehensive health check with database connectivity probe.
    Returns structured JSON with status, timestamp, and component health.
    """
    import time
    
    health_status = {
        "status": "healthy",
        "timestamp": int(time.time()),
        "components": {}
    }
    
    # Check database connectivity
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        conn.close()
        
        if result and result[0] == 1:
            health_status["components"]["database"] = {
                "status": "healthy",
                "message": "Database connection OK"
            }
        else:
            health_status["components"]["database"] = {
                "status": "unhealthy",
                "message": "Database query returned unexpected result"
            }
            health_status["status"] = "degraded"
    except Exception as e:
        health_status["components"]["database"] = {
            "status": "unhealthy",
            "message": f"Database connection failed: {str(e)}"
        }
        health_status["status"] = "unhealthy"
    
    # Check workspace directory
    try:
        if settings.workspace_dir.exists() and settings.workspace_dir.is_dir():
            health_status["components"]["workspace"] = {
                "status": "healthy",
                "message": f"Workspace accessible at {settings.workspace_dir}"
            }
        else:
            health_status["components"]["workspace"] = {
                "status": "unhealthy",
                "message": "Workspace directory not accessible"
            }
            health_status["status"] = "degraded"
    except Exception as e:
        health_status["components"]["workspace"] = {
            "status": "unhealthy",
            "message": f"Workspace check failed: {str(e)}"
        }
        health_status["status"] = "degraded"
    
    # Check soul system (optional component)
    try:
        soul_state = get_soul()
        if soul_state is not None:
            health_status["components"]["soul"] = {
                "status": "healthy",
                "message": "Soul system operational"
            }
        else:
            health_status["components"]["soul"] = {
                "status": "not_initialized",
                "message": "Soul system not loaded (optional)"
            }
    except Exception as e:
        health_status["components"]["soul"] = {
            "status": "not_initialized",
            "message": f"Soul system check failed (optional): {str(e)}"
        }
    
    return health_status


@app.post("/ingest/text", response_model=IngestResponse, dependencies=[Depends(get_api_key)])
def ingest_text(req: IngestRequest) -> IngestResponse:
    meta = req.meta or {}
    if req.tags:
        meta["tags"] = req.tags
    added = add_chunks(req.source, req.title, req.texts, meta)
    return IngestResponse(added=added)


@app.post("/ingest", response_model=IngestResponse, dependencies=[Depends(get_api_key)])
def ingest(req: IngestRequest) -> IngestResponse:
    # generic ingest endpoint
    meta = req.meta or {}
    if req.tags:
        meta["tags"] = req.tags
    added = add_chunks(req.source, req.title, req.texts, meta)
    return IngestResponse(added=added)


@app.post("/seed", dependencies=[Depends(get_api_key)])
def seed_demo_data() -> dict[str, Any]:
    """
    Populate database with sample notes, tags, and references for testing/demo.
    Idempotent: checks for existing data before inserting.
    """
    try:
        conn = get_conn()
        cursor = conn.cursor()
        
        # Check if we already have demo data
        cursor.execute("SELECT COUNT(*) FROM chunks WHERE doc_source = 'demo_seed'")
        existing_count = cursor.fetchone()[0]
        
        if existing_count > 0:
            conn.close()
            return {
                "status": "skipped",
                "message": f"Demo data already exists ({existing_count} chunks with source 'demo_seed')",
                "chunks_added": 0,
                "tags_added": 0
            }
        
        # Sample demo notes
        demo_notes = [
            {
                "title": "Getting Started with Toobix",
                "text": "Toobix is a local-first life management platform. It emphasizes privacy, [[federation]], and [[plugin architecture]]. Start by creating your first note!",
                "tags": ["tutorial", "getting-started"]
            },
            {
                "title": "Plugin Architecture",
                "text": "The plugin system allows hot-reload of modules. Plugins can extend [[Notes]], [[Tasks]], and [[Calendar]] functionality. Written in TypeScript with clear API boundaries.",
                "tags": ["architecture", "plugins"]
            },
            {
                "title": "Federation Concepts",
                "text": "Toobix uses simplified [[ActivityPub]] or [[AT Protocol]] for federation. Your data stays local, but you can selectively share with trusted peers. [[DID]]-based identity.",
                "tags": ["federation", "privacy"]
            },
            {
                "title": "Local-First Philosophy",
                "text": "All data lives in SQLite on your machine. No mandatory cloud sync. Optional backup to S3-compatible storage using [[Litestream]]. You own your data.",
                "tags": ["philosophy", "local-first"]
            },
            {
                "title": "AI Integration",
                "text": "Use [[Ollama]] for local LLM inference or connect to cloud providers like Groq. AI features: semantic search, auto-tagging, summary generation, and more.",
                "tags": ["ai", "ollama", "features"]
            },
            {
                "title": "Daily Notes",
                "text": "Create daily notes with YYYY-MM-DD format. Backlinks automatically connect related concepts. Use templates for recurring structures.",
                "tags": ["notes", "daily-notes"]
            },
            {
                "title": "Graph Visualization",
                "text": "See connections between notes with [[D3.js]] or [[Cytoscape.js]]. Filter by tags, date range, or link types. Explore knowledge visually.",
                "tags": ["visualization", "graph"]
            },
            {
                "title": "Search Capabilities",
                "text": "Full-text search powered by [[Orama]]. Semantic search with embeddings. Search across notes, tasks, and calendar events instantly.",
                "tags": ["search", "features"]
            }
        ]
        
        chunks_added = 0
        tags_added = 0
        
        # Insert demo notes
        for note in demo_notes:
            # Insert chunk
            cursor.execute(
                "INSERT INTO chunks (doc_source, doc_title, text, meta_json) VALUES (?, ?, ?, ?)",
                ("demo_seed", note["title"], note["text"], json.dumps({"tags": note["tags"]}))
            )
            chunk_id = cursor.lastrowid
            chunks_added += 1
            
            # Insert tags
            for tag_name in note["tags"]:
                # Get or create tag
                cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                tag_row = cursor.fetchone()
                
                if tag_row:
                    tag_id = tag_row[0]
                else:
                    cursor.execute("INSERT INTO tags (name) VALUES (?)", (tag_name,))
                    tag_id = cursor.lastrowid
                    tags_added += 1
                
                # Link chunk to tag
                cursor.execute(
                    "INSERT OR IGNORE INTO chunk_tags (chunk_id, tag_id) VALUES (?, ?)",
                    (chunk_id, tag_id)
                )
        
        conn.commit()
        conn.close()
        
        logger.info(f"Seeded database: {chunks_added} chunks, {tags_added} new tags")
        
        return {
            "status": "success",
            "message": "Demo data seeded successfully",
            "chunks_added": chunks_added,
            "tags_added": tags_added,
            "demo_notes": [n["title"] for n in demo_notes]
        }
        
    except Exception as e:
        logger.exception(f"Seed operation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Seed failed: {str(e)}")


@app.get("/search", response_model=SearchResponse)
def search_route(q: str = Query(...), k: int = Query(5, ge=1, le=50)) -> SearchResponse:
    hits = search(q, k)
    return SearchResponse(hits=hits)


@app.get("/chunks/{id}", response_model=ChunkResponse)
def get_chunk_route(id: int) -> ChunkResponse:
    c = get_chunk(id)
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    return ChunkResponse(**c.model_dump())


@app.get("/resources")
def list_resources(q: Optional[str] = Query(default=None), limit: int = Query(default=20, ge=1, le=200)) -> Any:
    """List stored resources (chunks).

    If `q` is provided, perform a search using the existing `search()` function
    and return matching hits. Otherwise return a simple listing of recent chunks
    (id, title, source).
    """
    try:
        if q:
            hits = search(q, k=limit)
            # convert Hit models to serializable dicts
            return {"hits": [h.model_dump() for h in hits]}
        # No query: list recent chunks from the DB
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT id, doc_title AS title, doc_source AS source, ts FROM chunks ORDER BY ts DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        items = [{"id": r["id"], "title": r["title"], "source": r["source"], "ts": r["ts"]} for r in rows]
        return {"items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/resources/{id}")
def open_resource(id: int) -> Any:
    """Open a resource (chunk) by id. Returns full chunk with text and meta."""
    c = get_chunk(id)
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    return c.model_dump()


@app.get("/fs/list")
def fs_list(subdir: Optional[str] = Query(default=None)) -> Any:
    try:
        items = list_dir(settings.workspace_dir, subdir)
        return {"items": items}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Directory not found")
    except NotADirectoryError:
        raise HTTPException(status_code=400, detail="Not a directory")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid path")


@app.get("/fs/read")
def fs_read(path: str = Query(...)) -> Any:
    try:
        data = read_file(settings.workspace_dir, path)
        return {"path": path, "text": data}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Not found")
    except IsADirectoryError:
        raise HTTPException(status_code=400, detail="Path is not a file")
    except FSError as e:
        raise HTTPException(status_code=415, detail=str(e))


@app.post("/actions/run", response_model=ActionResponse, dependencies=[Depends(get_api_key)])
def actions_run(req: ActionRequest) -> ActionResponse:
    try:
        policy = Policy(s1=settings.ai_s1, s2=settings.ai_s2, s3=settings.ai_s3)
        soul = get_soul()
        consent_checked = False
        write_commands = {"memory.add", "memory.tag", "memory.group", "game.new", "game.choose"}
        if req.command in write_commands:
            consent_checked = True
            requires_confirm = bool(soul.policies.get("write_requires_confirmation", False))
            confirm_flag = req.confirm if req.confirm is not None else bool(req.args.get("confirm", False))
            if requires_confirm and not confirm_flag:
                raise PreconditionFailed("Write requires confirmation")
        result = dispatch(req.command, req.args, policy, tier_mode=req.tier_mode, tiers_cfg=settings.ai_tiers)
        try:
            soul.append_event(f"actions.run:{req.command}", req.args, result, consent_checked=consent_checked)
        except Exception:
            pass
        return ActionResponse(ok=True, result=result)
    except ActionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PreconditionFailed as e:
        # 412 when a precondition like S3 usage is disabled by config
        raise HTTPException(status_code=412, detail=str(e))


# Extra: /ingest/chatgpt simple compatibility wrapper
class ChatGPTIngest(BaseModel):
    source: str
    title: Optional[str] = None
    messages: list[dict[str, Any]]
    meta: Optional[dict[str, Any]] = None


@app.post("/ingest/chatgpt", response_model=IngestResponse, dependencies=[Depends(get_api_key)])
def ingest_chatgpt(req: ChatGPTIngest) -> IngestResponse:
    # Extract message contents as texts
    texts: list[str] = []
    for m in req.messages:
        content = m.get("content")
        if isinstance(content, str):
            texts.append(content)
    added = add_chunks(req.source, req.title, texts, req.meta)
    return IngestResponse(added=added)


class GenerateRequest(BaseModel):
    prompt: str
    contextIds: Optional[list[int]] = None


@app.post("/generate")
def generate(req: GenerateRequest) -> dict[str, object]:
    # Dummy response for now
    return {"response": "Hier kommt später die KI-Antwort", "prompt": req.prompt, "contextIds": req.contextIds}


# Bridge-compatible proxy endpoint for the echo_generate tool (module-level)
@app.post("/bridge/link_echo_generate/echo_generate")
def bridge_echo_generate(
    body: GenerateRequest = Body(...),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> dict[str, object]:
    """Proxy handler used by bridge tools. It calls the local /generate implementation.

    Behavior:
    - If an API_KEY env is set ("API_KEY"), the handler will validate X-API-Key header.
    - Otherwise it proxies directly to the internal generate() function.
    """
    # Optional API key guard (useful if the bridge should authenticate callers)
    env_key = os.getenv("API_KEY")
    allow_unauth = os.environ.get("ALLOW_UNAUTH_BRIDGE", "false").lower() in ("1", "true", "yes")
    if env_key and not allow_unauth:
        if not x_api_key or x_api_key != env_key:
            raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key")

    # Call the internal generate implementation directly (same-process)
    try:
        result = generate(body)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Bridge proxy error: {e}")


@app.get("/soul/state")
def soul_state() -> Any:
    s = get_soul()
    return {"mood": s.get_mood(), "policies": s.policies}


@app.get("/soul/rituals")
def soul_rituals() -> Any:
    s = get_soul()
    return {"rituals": s.rituals}


@app.get("/", response_class=HTMLResponse)
def index_page() -> HTMLResponse:
    public_dir = Path(__file__).resolve().parent.parent / "public"
    index_path = public_dir / "index.html"
    if index_path.exists():
        return HTMLResponse(index_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>ECHO-BRIDGE</h1><p>Minimal UI not found.</p>")


# Serve a static OpenAPI spec for ChatGPT/Developer-Mode registration.
@app.get("/mcp/openapi.json")
def mcp_openapi() -> Response:
    """Expose the MCP OpenAPI document, preferring the live backend, then static, then dynamic."""
    backend = _backend_mcp_base()
    candidates = [f"{backend}/mcp/openapi.json", f"{backend}/openapi.json", f"{backend}/mcp"]
    for url in candidates:
        try:
            r = httpx.get(url, timeout=3.0)
            if r.status_code == 200:
                ctype = r.headers.get("content-type", "")
                if "application/json" in ctype or url.endswith("openapi.json"):
                    return Response(content=r.content, media_type="application/json")
                return Response(content=r.text, media_type="text/plain")
        except Exception:
            continue

    public_dir = Path(__file__).resolve().parent.parent / "public"
    openapi_path = public_dir / "mcp_openapi.json"
    if openapi_path.exists():
        try:
            data = _load_json_file(openapi_path)
            return JSONResponse(content=data)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to load openapi spec: {e}")

    try:
        spec = _build_dynamic_openapi_spec()
        return JSONResponse(content=spec, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build dynamic openapi spec: {e}")


# Proxy endpoints for MCP so the bridge can serve /mcp and /mcp/openapi.json on the
# same public origin. This helps ChatGPT Developer Tools register and connect.
def _backend_mcp_base() -> str:
    # Allow overriding via env var for tests; default to the run_mcp_http backend.
    return os.environ.get("MCP_BACKEND_URL", "http://127.0.0.1:3339")


#############################
# Robust /mcp streaming proxy
#############################

# Hop-by-hop headers per RFC 7230 we never forward directly
_HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "transfer-encoding", "upgrade"}

def _filter_response_headers(h: dict[str, str]) -> dict[str, str]:
    """Remove hop-by-hop headers (RFC 7230)."""
    return {k: v for k, v in h.items() if k.lower() not in _HOP_BY_HOP}

def _forward_request_headers(req: Request) -> dict[str, str]:
    """Whitelist and normalize headers we forward to backend."""
    allowed = {"accept", "content-type", "authorization", "x-api-key", "x-bridge-key"}
    out: Dict[str, str] = {}
    for k, v in req.headers.items():
        if k.lower() in allowed:
            out[k] = v
    if "accept" in req.headers and "text/event-stream" in req.headers.get("accept", ""):
        out["Accept"] = req.headers["accept"]
    return out

BACKEND_MCP_URL = "http://127.0.0.1:3339/mcp"
HEARTBEAT_SECS = float(os.environ.get("MCP_SSE_HEARTBEAT_SECS", "25")) if os.environ.get("MCP_SSE_HEARTBEAT_SECS") else 0.0
MAX_RETRIES = int(os.environ.get("MCP_BACKEND_RETRIES", "3"))
BACKOFF_BASE = float(os.environ.get("MCP_BACKEND_BACKOFF_BASE", "0.3"))

async def _retry_backoff(func: Callable[[], Awaitable[Any]]):
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await func()
        except Exception as e:  # noqa: BLE001
            last_exc = e
            if attempt == MAX_RETRIES:
                break
            await asyncio.sleep(BACKOFF_BASE * (2 ** (attempt - 1)))
    if last_exc:
        raise last_exc
    raise RuntimeError("retry logic failed without exception")

@app.get("/mcp", name="mcp_sse", operation_id="mcp_sse_stream")
async def mcp_get_sse(request: Request):  # Returning either JSONResponse or StreamingResponse
        """SSE pass-through.

        Behavior:
            * If header `Accept` includes `text/event-stream`, open a streaming
                connection to the backend MCP server and proxy raw SSE frames.
            * Otherwise, by default return 406 to signal the client must request
                SSE explicitly.
            * If env var `MCP_ALLOW_FALLBACK_GET` is truthy (1/true/yes) and the
                client did NOT request SSE, return a JSON 200 instructional payload
                instead of 406. This helps platforms (e.g. ChatGPT) that probe the
                endpoint once without the SSE Accept header before establishing the
                real streaming connection.

        Response headers for SSE mode:
            - Content-Type: text/event-stream
            - Cache-Control: no-cache
            - Connection: keep-alive
            - X-Accel-Buffering: no
        """
        accept = request.headers.get("accept", "")
        wants_sse = "text/event-stream" in accept.lower()
        allow_fallback = os.environ.get("MCP_ALLOW_FALLBACK_GET", "false").lower() in ("1", "true", "yes")
        if not wants_sse:
            if allow_fallback:
                return JSONResponse(
                    status_code=200,
                    content={
                        "ok": True,
                        "mode": "fallback",
                        "detail": "SSE Accept header missing. To open a streaming MCP session send GET /mcp with 'Accept: text/event-stream'.",
                        "env": {"MCP_ALLOW_FALLBACK_GET": True},
                        "instructions": [
                            "curl -H 'Accept: text/event-stream' https://YOUR_DOMAIN/mcp",
                            "Ensure your client sets Accept header before upgrading connection",
                        ],
                    },
                    headers={"Access-Control-Allow-Origin": "*"},
                )
            raise HTTPException(status_code=406, detail="Missing Accept: text/event-stream for SSE endpoint")

        fwd_headers = _forward_request_headers(request)
        metrics.started_sse += 1
        metrics.active_sse += 1

        async def sse_iterator() -> AsyncGenerator[bytes, None]:
            try:
                async with httpx.AsyncClient(timeout=None) as client:
                    async def _open():
                        return client.stream("GET", BACKEND_MCP_URL, headers=fwd_headers)
                    stream_ctx = await _retry_backoff(_open)  # type: ignore[arg-type]
                    async with stream_ctx as resp:
                        if resp.status_code != 200:
                            yield f"event: error\ndata: backend status {resp.status_code}\n\n".encode()
                            return
                        try:
                            last_send = perf_counter()
                            async for chunk in resp.aiter_raw():
                                now = perf_counter()
                                if HEARTBEAT_SECS and (now - last_send) >= HEARTBEAT_SECS:
                                    yield b": heartbeat\n\n"
                                    last_send = now
                                if chunk:
                                    yield chunk
                                    last_send = perf_counter()
                                elif HEARTBEAT_SECS and (now - last_send) >= HEARTBEAT_SECS:
                                    yield b": heartbeat\n\n"
                                    last_send = perf_counter()
                        except (httpx.RemoteProtocolError, httpx.ReadError):
                            logger.info("mcp SSE: backend stream terminated")
                        except (ConnectionResetError, asyncio.CancelledError):
                            logger.info("mcp SSE: client or connection reset")
                            metrics.aborted_sse += 1
                        except Exception as e:  # noqa: BLE001
                            logger.warning("mcp SSE: unexpected stream error: %s", e)
                            metrics.aborted_sse += 1
            except (anyio.ClosedResourceError, asyncio.CancelledError, ConnectionResetError):  # type: ignore[name-defined]
                logger.info("mcp SSE: client disconnected early")
                metrics.aborted_sse += 1
            except Exception as e:  # noqa: BLE001
                logger.warning("mcp SSE: outer error: %s", e)
                metrics.aborted_sse += 1
            finally:
                metrics.active_sse -= 1
                metrics.completed_sse += 1

        headers = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        }
        return StreamingResponse(sse_iterator(), media_type="text/event-stream", headers=headers)


@app.post("/mcp", name="mcp_stream_post", operation_id="mcp_post_stream")
async def mcp_post_stream(request: Request) -> StreamingResponse:
    """Bidirectional streaming proxy for POST /mcp.

    Streams request body to backend and yields backend response chunks without buffering.
    """
    fwd_headers = _forward_request_headers(request)

    metrics.started_post += 1
    metrics.active_post += 1
    async def req_body_iter() -> AsyncGenerator[bytes, None]:
        try:
            async for chunk in request.stream():  # type: ignore[attr-defined]
                if chunk:
                    metrics.bytes_up_post += len(chunk)
                    yield chunk
        except (anyio.ClosedResourceError, asyncio.CancelledError, ConnectionResetError):  # type: ignore[name-defined]
            logger.info("mcp POST: client upload aborted")
            metrics.aborted_post += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("mcp POST: upload stream error: %s", e)
            metrics.aborted_post += 1

    try:
        client = httpx.AsyncClient(timeout=None)
        async def _open_post():  # returns context manager
            return client.stream("POST", BACKEND_MCP_URL, headers=fwd_headers, content=req_body_iter())
        resp_ctx = await _retry_backoff(_open_post)  # type: ignore[arg-type]
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Failed to connect backend: {e}")

    async def response_iter() -> AsyncGenerator[bytes, None]:
        try:
            async with resp_ctx as resp:
                status = resp.status_code
                # Filter headers once we have them; yield body regardless
                preserved = _filter_response_headers({k: v for k, v in resp.headers.items()})
                # Force pass-through friendly defaults (no buffering hints)
                preserved.setdefault("Cache-Control", "no-cache")
                preserved.setdefault("Connection", "keep-alive")
                preserved["Access-Control-Allow-Origin"] = "*"
                # Attach headers object outside by closure trick
                response_iter.preserved_headers = preserved  # type: ignore[attr-defined]
                response_iter.status_code = status  # type: ignore[attr-defined]
                async for chunk in resp.aiter_raw():
                    if chunk:
                        metrics.bytes_down_post += len(chunk)
                        yield chunk
        except (anyio.ClosedResourceError, asyncio.CancelledError, ConnectionResetError):  # type: ignore[name-defined]
            logger.info("mcp POST: downstream client disconnected")
            metrics.aborted_post += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("mcp POST: response stream error: %s", e)
            metrics.aborted_post += 1
        finally:
            await client.aclose()
            metrics.active_post -= 1
            metrics.completed_post += 1

    # Prime an async generator wrapper to capture headers & status lazily
    gen = response_iter()
    # Headers/status set inside generator before first body chunk; FastAPI sends defaults until then.
    return StreamingResponse(gen, media_type="application/octet-stream")

# NOTE: Recommended Uvicorn launch for streaming stability:
#   uvicorn echo_bridge.main:app --host 127.0.0.1 --port 3333 --http h11 --workers 1
        


def _build_dynamic_openapi_spec() -> dict[str, Any]:
    """Attempt to build a minimal OpenAPI spec from the FastMCP server tools.

    Returns a dict shaped like an OpenAPI 3 minimal document. Types are broad (Any) to
    keep implementation flexible while avoiding Pylance 'Unknown' noise.
    """
    tools: list[str] = []
    for attr in ("tools", "_tools", "registered_tools", "_registry"):
        candidate: Any = getattr(mcp_server, attr, None)
        if candidate:
            if isinstance(candidate, dict):
                tools = [str(k) for k in candidate.keys()]
            elif isinstance(candidate, (list, tuple)):
                names: list[str] = []
                for it in candidate:
                    n = getattr(it, "name", None) or getattr(it, "__name__", None)
                    if isinstance(n, str):
                        names.append(n)
                tools = names
            break

    spec: dict[str, Any] = {
        "openapi": "3.0.1",
        "info": {"title": "ECHO Bridge MCP (dynamic)", "version": "0.1.0"},
        "paths": {},
    }

    public = _get_public_base_url()
    if public:
        spec["servers"] = [{"url": public}]

    spec_paths: dict[str, Any] = spec["paths"]  # narrow local ref

    spec_paths["/generate"] = {
        "post": {
            "summary": "Generate text (internal)",
            "requestBody": {"content": {"application/json": {"schema": {"type": "object"}}}},
            "responses": {"200": {"description": "OK"}},
        }
    }

    spec_paths["/bridge/link_echo_generate/echo_generate"] = {
        "post": {
            "summary": "Bridge proxy for echo_generate tool",
            "requestBody": {"content": {"application/json": {"schema": {"type": "object"}}}},
            "responses": {"200": {"description": "OK"}},
        }
    }

    if tools:
        spec["x-mcp-tools"] = tools

    return spec


# On startup: ensure public/openapi.json and public/chatgpt_tool_manifest.json
def _ensure_public_specs_written() -> None:
    public_dir = Path(__file__).resolve().parent.parent / "public"
    public_dir.mkdir(parents=True, exist_ok=True)
    openapi_path = public_dir / "openapi.json"
    manifest_path = public_dir / "chatgpt_tool_manifest.json"

    # Load existing openapi.json or build a dynamic spec
    try:
        if openapi_path.exists():
            current = _load_json_file(openapi_path)
        else:
            current = _build_dynamic_openapi_spec()
    except Exception:
        current = _build_dynamic_openapi_spec()

    # Ensure servers entry if PUBLIC_BASE_URL set
    public = _get_public_base_url()
    if public:
        current.setdefault("servers", [{"url": public}])

    # Ensure resource paths exist (don't overwrite existing definitions)
    paths = current.setdefault("paths", {})
    if "/resources" not in paths:
        paths["/resources"] = {
            "get": {
                "summary": "List resources (search or recent chunks)",
                "parameters": [
                    {"name": "q", "in": "query", "schema": {"type": "string"}, "required": False},
                    {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 20}}
                ],
                "responses": {"200": {"description": "OK"}}
            }
        }
    if "/resources/{id}" not in paths:
        paths["/resources/{id}"] = {
            "get": {
                "summary": "Open resource by id",
                "parameters": [{"name": "id", "in": "path", "schema": {"type": "integer"}, "required": True}],
                "responses": {"200": {"description": "OK"}, "404": {"description": "Not Found"}}
            }
        }

    # Write openapi.json only if changed (preserve manual edits when possible)
    try:
        new_text = json.dumps(current, ensure_ascii=False, indent=2)
        orig_text = openapi_path.read_text(encoding="utf-8") if openapi_path.exists() else None
        if orig_text is None or orig_text.strip() != new_text.strip():
            openapi_path.write_text(new_text, encoding="utf-8")
            logger.info("wrote public/openapi.json")
    except Exception as e:
        logger.warning(f"failed to write openapi.json: {e}")

    # Manifest: load existing manifest and only update api.url server reference if PUBLIC_BASE_URL set
    try:
        manifest = None
        if manifest_path.exists():
            manifest = _load_json_file(manifest_path)
        else:
            # Create a minimal manifest skeleton if none exists
            manifest = {
                "schema_version": "v1",
                "name_for_human": "ECHO Bridge",
                "name_for_model": "echo_bridge",
                "description_for_human": "ECHO Bridge",
                "description_for_model": "Tools: /ingest, /search, /fetch, /generate",
                "auth": {"type": "none"},
                "api": {"type": "openapi", "url": "./public/openapi.json", "is_user_authenticated": False},
            }

        if public:
            # Ensure absolute URL to the public openapi
            manifest.setdefault("api", {})
            manifest["api"]["url"] = f"{public}/public/openapi.json"

        # Ensure manifest has a brief mention of resources in model description
        desc = manifest.get("description_for_model", "")
        if "resources" not in desc:
            manifest["description_for_model"] = desc + " Use /resources to list or open stored chunks."

        new_manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2)
        orig_manifest_text = manifest_path.read_text(encoding="utf-8") if manifest_path.exists() else None
        if orig_manifest_text is None or orig_manifest_text.strip() != new_manifest_text.strip():
            manifest_path.write_text(new_manifest_text, encoding="utf-8")
            logger.info("wrote public/chatgpt_tool_manifest.json")
    except Exception as e:
        logger.warning(f"failed to write manifest: {e}")


def _on_startup_write_public_specs() -> None:
    try:
        _ensure_public_specs_written()
    except Exception as e:
        logger.warning("_ensure_public_specs_written failed: %s", e)


def generate_public_specs_on_startup() -> None:
    """Generate or update `public/openapi.json` and ensure the chatgpt manifest is present.

    This writes a minimal OpenAPI file into the `public/` directory so external tools
    (or tunnels serving static files) see the latest paths (including /resources).
    The files are also still rewritten at request-time to reflect PUBLIC_BASE_URL.
    """
    try:
        pubdir = Path(__file__).resolve().parent.parent / "public"
        pubdir.mkdir(parents=True, exist_ok=True)

        # Build dynamic spec (includes /generate and bridge proxy currently)
        spec = _build_dynamic_openapi_spec()

        # Add resources endpoints if not already present
        spec_paths = spec.setdefault("paths", {})
        spec_paths.setdefault("/resources", {
            "get": {
                "summary": "List resources (search or recent chunks)",
                "parameters": [
                    {"name": "q", "in": "query", "schema": {"type": "string"}, "required": False},
                    {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 20}},
                ],
                "responses": {"200": {"description": "OK"}},
            }
        })
        spec_paths.setdefault("/resources/{id}", {
            "get": {
                "summary": "Open resource by id",
                "parameters": [{"name": "id", "in": "path", "schema": {"type": "integer"}, "required": True}],
                "responses": {"200": {"description": "OK"}, "404": {"description": "Not Found"}},
            }
        })

        openapi_path = pubdir / "openapi.json"
        with open(openapi_path, "w", encoding="utf-8") as f:
            json.dump(spec, f, ensure_ascii=False, indent=2)

        # Ensure a chatgpt manifest exists; if present, try to augment tool list
        manifest_path = pubdir / "chatgpt_tool_manifest.json"
        if manifest_path.exists():
            try:
                mf = _load_json_file(manifest_path)
                # If the manifest contains a `tools` or `endpoints` area, add a note
                # We avoid overwriting user fields; just ensure the file exists and is valid JSON.
                with open(manifest_path, "w", encoding="utf-8") as f:
                    json.dump(mf, f, ensure_ascii=False, indent=2)
            except Exception:
                # if the manifest is invalid, rewrite a minimal placeholder
                mf = {
                    "schema_version": "v1",
                    "name_for_human": "ECHO Bridge (generated)",
                    "description_for_human": "ECHO bridge exposing generate and resources endpoints.",
                    "auth": {"type": "none"},
                    "endpoints": ["/generate", "/resources", "/resources/{id}"]
                }
                with open(manifest_path, "w", encoding="utf-8") as f:
                    json.dump(mf, f, ensure_ascii=False, indent=2)
        else:
            # write a minimal manifest so dev tooling can see something
            mf = {
                "schema_version": "v1",
                "name_for_human": "ECHO Bridge (generated)",
                "description_for_human": "ECHO bridge exposing generate and resources endpoints.",
                "auth": {"type": "none"},
                "endpoints": ["/generate", "/resources", "/resources/{id}"]
            }
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(mf, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"generate_public_specs_on_startup: failed to write public specs: {e}")


@app.get("/debug/manifest_url")
def debug_manifest_url() -> JSONResponse:
    """Return the public base URL that will be used to rewrite manifests (if any)."""
    return JSONResponse(content={"public_base_url": _get_public_base_url()})


@app.get("/debug/info")
def debug_info() -> JSONResponse:
    """Return runtime debug info: whether API_KEY is set (masked) and bridge key status."""
    env_key = os.getenv("API_KEY")
    bridge_key = settings.bridge_key
    return JSONResponse(content={
        "api_key_set": bool(env_key),
        "api_key_masked": (None if not env_key else (env_key[:2] + "..." + env_key[-2:] if len(env_key) > 4 else "****")),
        "bridge_key": (bridge_key[:2] + "..." + bridge_key[-2:] if bridge_key else None),
    })


@app.get("/debug/tools")
def debug_tools() -> JSONResponse:
    """Return a list of registered MCP tool names discovered from the FastMCP instance."""
    try:
        tools = []
        for attr in ("tools", "_tools", "registered_tools", "_registry"):
            candidate = getattr(mcp_server, attr, None)
            if candidate:
                if isinstance(candidate, dict):
                    tools = list(candidate.keys())
                elif isinstance(candidate, (list, tuple)):
                    names = []
                    for it in candidate:
                        n = getattr(it, "name", None) or getattr(it, "__name__", None)
                        if n:
                            names.append(n)
                    tools = names
                break
        return JSONResponse(content={"tools": tools})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/debug/backend_openapi")
def debug_backend_openapi() -> JSONResponse:
    """Proxy the backend FastMCP openapi.json (127.0.0.1:3339) so callers can inspect registered tools.
    This avoids introspecting the in-process object which may be empty when the backend runs in a separate process.
    """
    import urllib.request
    import json as _json

    # Try several likely backend OpenAPI locations in order of preference.
    candidates = [
        "http://127.0.0.1:3339/mcp/openapi.json",
        "http://127.0.0.1:3339/openapi.json",
        "http://127.0.0.1:3339/mcp",
    ]
    for backend_url in candidates:
        try:
            req = urllib.request.Request(backend_url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = resp.read()
                # If the response looks like JSON, decode and return it
                try:
                    j = _json.loads(data)
                    return JSONResponse(content={"url": backend_url, "json": j})
                except Exception:
                    # If it's not JSON, return raw text for inspection
                    return JSONResponse(content={"url": backend_url, "raw": data.decode("utf-8", errors="replace")})
        except Exception:
            # Try next candidate
            continue
    return JSONResponse(status_code=502, content={"error": "backend openapi unreachable (tried candidates)", "candidates": candidates})


@app.get("/debug/backend_health")
def debug_backend_health() -> JSONResponse:
    """Probe backend /mcp with Accept: text/event-stream and fall back to backend openapi.json.
    Returns a small snippet or the openapi paths for inspection.
    """
    import urllib.request
    import json as _json

    backend_mcp = "http://127.0.0.1:3339/mcp"
    backend_openapi_candidates = [
        "http://127.0.0.1:3339/mcp/openapi.json",
        "http://127.0.0.1:3339/openapi.json",
    ]
    try:
        # First try SSE probe at /mcp
        req = urllib.request.Request(backend_mcp, headers={"Accept": "text/event-stream"})
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                ct = resp.headers.get("Content-Type", "")
                if "text/event-stream" in ct:
                    chunk = resp.read(512)
                    snippet = chunk.decode("utf-8", errors="replace")
                    return JSONResponse(content={"ok": True, "sse": True, "snippet": snippet})
        except Exception:
            # fallthrough to openapi candidates
            pass

        # Fallback: try known openapi locations
        for backend_openapi in backend_openapi_candidates:
            try:
                req2 = urllib.request.Request(backend_openapi, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req2, timeout=3) as resp2:
                    data = resp2.read()
                    try:
                        j = _json.loads(data)
                        paths = sorted(list(j.get("paths", {}).keys()))
                        return JSONResponse(content={"ok": True, "sse": False, "url": backend_openapi, "paths": paths})
                    except Exception:
                        return JSONResponse(content={"ok": True, "sse": False, "url": backend_openapi, "raw": data.decode("utf-8", errors="replace")})
            except Exception:
                continue

        return JSONResponse({"ok": False, "error": "backend unreachable or no usable endpoint found"}, status_code=502)
    except Exception as e:
        return JSONResponse(status_code=502, content={"ok": False, "error": str(e)})


@app.get("/action_ready")
async def action_ready() -> JSONResponse:
    """Aggregate readiness info for ChatGPT/Actions style integration.

    Returns JSON with:
      - public_base_url
      - manifest_ok / openapi_ok (HTTP 200 fetch test)
      - backend_sse (was able to open short SSE probe to /mcp with Accept header)
      - fallback_enabled (MCP_ALLOW_FALLBACK_GET)
      - timestamp
    """
    import httpx, time
    base = _get_public_base_url()
    pubs: dict[str, object] = {
        "public_base_url": base,
        "fallback_enabled": os.environ.get("MCP_ALLOW_FALLBACK_GET", "").lower() in ("1", "true", "yes"),
        "manifest_ok": False,
        "openapi_ok": False,
        "backend_sse": False,
        "timestamp": int(time.time()),
    }
    try:
        if base:
            async with httpx.AsyncClient(timeout=4) as client:
                # Manifest
                try:
                    r = await client.get(f"{base}/chatgpt_tool_manifest.json")
                    if r.status_code == 200:
                        pubs["manifest_ok"] = True
                except Exception:
                    pass
                # OpenAPI
                try:
                    r2 = await client.get(f"{base}/openapi.json")
                    if r2.status_code == 200:
                        pubs["openapi_ok"] = True
                except Exception:
                    pass
                # SSE probe (short)
                try:
                    r3 = await client.get(f"{base}/mcp", headers={"Accept": "text/event-stream"}, timeout=4)
                    if r3.status_code == 200:
                        pubs["backend_sse"] = True
                except Exception:
                    pass
    except Exception:
        pass
    return JSONResponse(content=pubs)


@app.get("/panel", response_class=HTMLResponse)
async def panel() -> HTMLResponse:
    """Minimal HTML control/readiness panel (static) with JS polling /action_ready."""
    html = """
<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <title>MCP Bridge Panel</title>
    <style>
            :root { color-scheme: dark light; }
            body { font-family: system-ui, Arial, sans-serif; margin: 1.5rem; background:#111; color:#eee; transition: background .3s, color .3s; }
            body.light { background:#fafafa; color:#111; }
        h1 { font-size:1.2rem; margin:0 0 .75rem; }
        .grid { display:grid; gap:.75rem; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); }
        .card { background:#1f1f1f; padding:1rem; border-radius:8px; box-shadow:0 0 0 1px #333; }
            body.light .card { background:#ffffff; box-shadow:0 0 0 1px #ddd; }
        .status { font-weight:600; }
        .ok { color:#4ade80; }
        .bad { color:#f87171; }
        a { color:#60a5fa; text-decoration:none; }
        a:hover { text-decoration:underline; }
        code { background:#222; padding:2px 4px; border-radius:4px; }
            body.light code { background:#eee; }
        button { background:#2563eb; color:#fff; border:none; padding:.4rem .8rem; border-radius:4px; cursor:pointer; }
        button:hover { background:#1d4ed8; }
        #raw { white-space:pre; font-size:.75rem; max-height:320px; overflow:auto; background:#0d0d0d; padding:.5rem; border:1px solid #333; border-radius:6px; }
            body.light #raw { background:#f0f0f0; border-color:#ccc; }
            table.metrics { width:100%; border-collapse:collapse; font-size:.7rem; }
            table.metrics th, table.metrics td { padding:2px 4px; text-align:left; border-bottom:1px solid #333; }
            body.light table.metrics th, body.light table.metrics td { border-color:#ddd; }
            .logbox { font-size:.65rem; white-space:pre-wrap; max-height:180px; overflow:auto; background:#0d0d0d; border:1px solid #333; padding:.5rem; border-radius:6px; }
            body.light .logbox { background:#f0f0f0; border-color:#ccc; }
        footer { margin-top:1.5rem; font-size:.7rem; opacity:.6; }
            .row { display:flex; gap:.5rem; flex-wrap:wrap; align-items:center; }
    </style>
</head>
<body>
    <h1>MCP Bridge Control Panel</h1>
        <div class=\"row\">
            <div id=\"links\" style=\"flex:1;\"></div>
            <button onclick=\"toggleTheme()\" id=\"themeBtn\">Light Mode</button>
        </div>
    <div class=\"grid\">
        <div class=\"card\">
            <div>Public Base URL:</div>
            <div id=\"base\"><em>loading...</em></div>
            <div style=\"margin-top:.5rem;\">
                <button onclick=\"copyUrl()\">Copy /mcp URL</button>
                    <button onclick=\"copyManifest()\">Copy Manifest URL</button>
            </div>
        </div>
        <div class=\"card\">
            <div class=\"status\">Manifest: <span id=\"manifest\">?</span></div>
            <div class=\"status\">OpenAPI: <span id=\"openapi\">?</span></div>
            <div class=\"status\">Backend SSE: <span id=\"sse\">?</span></div>
            <div class=\"status\">Fallback Enabled: <span id=\"fallback\">?</span></div>
            <div class=\"status\">Updated: <span id=\"updated\">—</span></div>
        </div>
        <div class=\"card\">
            <strong>Instructions</strong>
            <ol style=\"padding-left:1.1rem; font-size:.8rem; line-height:1.25rem;\">
                <li>Ensure all three (Manifest/OpenAPI/SSE) show OK.</li>
                <li>Click Copy /mcp URL.</li>
                <li>Register in ChatGPT (Custom Connector or Actions).</li>
            </ol>
            <button onclick=\"refreshNow()\">Refresh Now</button>
        </div>
            <div class=\"card\">
                <strong>Metrics Snapshot</strong>
                <div id=\"metrics_empty\"><em>loading...</em></div>
                <table class=\"metrics\" id=\"metrics_table\" style=\"display:none;\">
                    <thead><tr><th>Group</th><th>Key</th><th>Value</th></tr></thead>
                    <tbody id=\"metrics_body\"></tbody>
                </table>
            </div>
            <div class=\"card\">
                <strong>Cloudflared Log Tail</strong>
                <div id=\"logtail\" class=\"logbox\">(loading)</div>
                <button onclick=\"refreshLogs()\">Refresh Logs</button>
            </div>
        <div class=\"card\" style=\"grid-column:1/-1;\">
            <details open>
                <summary style=\"cursor:pointer;\">Raw /action_ready payload</summary>
                <div id=\"raw\">(loading)</div>
            </details>
        </div>
    </div>
    <footer>Panel auto-refreshes every 5s. /panel endpoint.</footer>
    <script>
            async function fetchReady(){
                try {
                    const r = await fetch('/panel_data',{cache:'no-store'});
                    const j = await r.json();
                    const rd = j.readiness || {};
                    document.getElementById('raw').textContent = JSON.stringify(rd,null,2);
                    const ok = (v,id)=>{const el=document.getElementById(id); if(!el) return; el.textContent=v? 'OK':'FAIL'; el.className=v? 'ok':'bad';};
                    document.getElementById('base').textContent = rd.public_base_url || '(none)';
                    ok(rd.manifest_ok,'manifest');
                    ok(rd.openapi_ok,'openapi');
                    ok(rd.backend_sse,'sse');
                    const f = document.getElementById('fallback'); f.textContent = rd.fallback_enabled?'YES':'NO'; f.className = rd.fallback_enabled?'ok':'bad';
                    document.getElementById('updated').textContent = new Date().toLocaleTimeString();
                    renderLinks(rd.public_base_url);
                    renderMetrics(j.metrics || {});
                } catch(e){ console.error(e); }
            }
        function renderLinks(base){
            const c = document.getElementById('links');
            if(!base){ c.innerHTML = '<em>No base URL set (tunnel not detected yet)</em>'; return; }
            const esc = base.replace(/"/g,'');
            c.innerHTML = `<p><a href="${esc}/openapi.json" target="_blank">OpenAPI</a> · <a href="${esc}/chatgpt_tool_manifest.json" target="_blank">Manifest</a> · <a href="${esc}/mcp" target="_blank">/mcp (SSE)</a></p>`;
        }
        function copyUrl(){
            const base = document.getElementById('base').textContent.trim();
            if(!base || base === '(none)'){ alert('No public base URL yet.'); return; }
            const full = base.replace(/\/$/,'') + '/mcp';
            navigator.clipboard.writeText(full).then(()=>{ 
                const btns = document.getElementsByTagName('button');
                [...btns].forEach(b=>{ if(b.innerText.startsWith('Copy')) { b.innerText='Copied!'; setTimeout(()=>b.innerText='Copy /mcp URL',1200); }});
            });
        }
            function copyManifest(){
                const base = document.getElementById('base').textContent.trim();
                if(!base || base === '(none)'){ alert('No public base URL yet.'); return; }
                const full = base.replace(/\/$/,'') + '/chatgpt_tool_manifest.json';
                navigator.clipboard.writeText(full).then(()=>{ 
                    const btns = document.getElementsByTagName('button');
                    [...btns].forEach(b=>{ if(b.innerText.startsWith('Copy Manifest')) { b.innerText='Copied!'; setTimeout(()=>b.innerText='Copy Manifest URL',1200); }});
                });
            }
            function renderMetrics(m){
                const table = document.getElementById('metrics_table');
                const body = document.getElementById('metrics_body');
                const empty = document.getElementById('metrics_empty');
                body.innerHTML='';
                const rows=[];
                for(const group of Object.keys(m)){
                    const obj = m[group];
                    if(typeof obj === 'object'){
                        for(const k of Object.keys(obj)){
                            rows.push(`<tr><td>${group}</td><td>${k}</td><td>${obj[k]}</td></tr>`);
                        }
                    }
                }
                if(rows.length){
                    empty.style.display='none';
                    table.style.display='table';
                    body.innerHTML = rows.join('');
                } else {
                    empty.style.display='block';
                    table.style.display='none';
                }
            }
            async function refreshLogs(){
                try { const r = await fetch('/logs/cloudflared?limit=160'); const j = await r.json(); document.getElementById('logtail').textContent = j.lines ? j.lines.join('') : '(no lines)'; } catch(e){ console.error(e); }
            }
            function toggleTheme(){
                document.body.classList.toggle('light');
                const btn = document.getElementById('themeBtn');
                btn.textContent = document.body.classList.contains('light') ? 'Dark Mode' : 'Light Mode';
            }
        function refreshNow(){ fetchReady(); }
        fetchReady();
        setInterval(fetchReady,5000);
            refreshLogs();
            setInterval(refreshLogs,10000);
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html)

@app.get("/panel_data")
async def panel_data() -> JSONResponse:
    """Return combined readiness + metrics for richer panel polling."""
    ready_resp = await action_ready()
    try:
        ready_json = json.loads(ready_resp.body.decode("utf-8"))
    except Exception:
        ready_json = {"error": "parse_ready_failed"}
    metrics_snapshot = metrics.snapshot()
    payload = {"readiness": ready_json, "metrics": metrics_snapshot}
    return JSONResponse(content=payload)

@app.get("/logs/cloudflared")
async def cloudflared_logs(limit: int = 120) -> JSONResponse:
    """Return tail of cloudflared_control.log if present (used by /panel)."""
    log_path = os.path.join(os.path.dirname(__file__), "..", "cloudflared_control.log")
    log_path = os.path.abspath(log_path)
    lines: list[str] = []
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                all_lines = f.readlines()
                lines = all_lines[-limit:]
        except Exception as e:
            return JSONResponse(content={"error": str(e), "path": log_path})
    return JSONResponse(content={"path": log_path, "lines": lines})


@app.get("/mcp_openapi_dynamic.json")
def mcp_openapi_dynamic() -> JSONResponse:
    try:
        spec = _build_dynamic_openapi_spec()
        return JSONResponse(content=spec)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build dynamic openapi spec: {e}")


# DUPLICATES REMOVED - third definitions commented out (canonical versions exist at line ~360 and ~540)
# @app.get("/public/chatgpt_tool_manifest.json")
# def serve_chatgpt_manifest(request: Request) -> JSONResponse:
#     ...
#
# @app.get("/public/openapi.json")
# def serve_openapi(request: Request) -> JSONResponse:
#     ...
