from __future__ import annotations

import json
import os
import logging
from pathlib import Path
from time import perf_counter
from typing import Any, Optional, cast, Awaitable, Callable
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
settings.workspace_dir.mkdir(parents=True, exist_ok=True)
settings.db_path.parent.mkdir(parents=True, exist_ok=True)
init_db(settings.db_path)
try:
    soul_root = Path(__file__).resolve().parent.parent
    soul = load_soul(soul_root, timeline_path=Path("./echo-bridge/data/timeline.jsonl"))
    init_soul(soul)
except Exception:
    pass


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan handler: run startup tasks previously registered with
    @app.on_event("startup"). This centralizes startup logic and is
    the recommended modern FastAPI pattern.
    """
    # Run startup routines (they are defined further down in the module).
    try:
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
    except Exception:
        logger.exception("unexpected error during startup lifespan")
    # Yield to run the app; no shutdown cleanup required currently.
    yield


app = FastAPI(title="ECHO-BRIDGE", lifespan=lifespan)
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


@app.get("/openapi.json")
def serve_openapi_root() -> JSONResponse:
    """Fallback root OpenAPI JSON endpoint. Returns same content as /public/openapi.json."""
    p = public_dir / "openapi.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="openapi.json not found")
    try:
        data = _load_json_file(p)
        public = _get_public_base_url()
        if public:
            data = _recursive_replace_origins(data, public)
        return JSONResponse(content=data, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read openapi.json: {e}")


@app.get("/chatgpt_tool_manifest.json")
def serve_manifest_root() -> JSONResponse:
    """Fallback root manifest endpoint. Returns same content as /public/chatgpt_tool_manifest.json."""
    p = public_dir / "chatgpt_tool_manifest.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="chatgpt_tool_manifest.json not found")
    try:
        data = _load_json_file(p)
        public = _get_public_base_url()
        if public:
            data = _recursive_replace_origins(data, public)
        return JSONResponse(content=data, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read chatgpt manifest: {e}")


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


@app.get("/public/openapi.json")
def serve_public_openapi() -> JSONResponse:
    p = public_dir / "openapi.json"
    if not p.exists():
        p = public_dir / "openapi.generated.json"
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
            "Access-Control-Allow-Credentials": "true",
        }
        return JSONResponse(content=data, media_type="application/json", headers=headers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read public openapi: {e}")


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
def healthz() -> dict[str, str]:
    return {"status": "ok"}


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
def mcp_openapi() -> JSONResponse:
    public_dir = Path(__file__).resolve().parent.parent / "public"
    openapi_path = public_dir / "mcp_openapi.json"
    # Prefer an explicit static file for stability
    if openapi_path.exists():
        try:
            data = _load_json_file(openapi_path)
            return JSONResponse(content=data)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to load openapi spec: {e}")

    # Fallback: attempt to build a minimal OpenAPI spec dynamically from the FastMCP server
    try:
        tools = []
        # Try several common attribute names used by FastMCP to keep compatibility
        for attr in ("tools", "_tools", "registered_tools", "_registry"):
            candidate = getattr(mcp_server, attr, None)
            if candidate:
                if isinstance(candidate, dict):
                    tools = list(candidate.keys())
                elif isinstance(candidate, (list, tuple)):
                    # items may be objects with a 'name' attribute
                    names = []
                    for it in candidate:
                        n = getattr(it, "name", None) or getattr(it, "__name__", None)
                        if n:
                            names.append(n)
                    tools = names
                break

        # Build a simple OpenAPI spec exposing the internal /generate and the bridge proxy endpoints
        spec = {
            "openapi": "3.0.1",
            "info": {"title": "ECHO Bridge MCP (dynamic)", "version": "0.1.0"},
            "paths": {},
        }

        # Internal generate
        spec["paths"]["/generate"] = {
            "post": {
                "summary": "Generate text (internal)",
                "requestBody": {"content": {"application/json": {"schema": {"type": "object"}}}},
                "responses": {"200": {"description": "OK"}},
            }
        }

        # Bridge proxy for echo_generate
        spec["paths"]["/bridge/link_echo_generate/echo_generate"] = {
            "post": {
                "summary": "Bridge proxy for echo_generate tool",
                "requestBody": {"content": {"application/json": {"schema": {"type": "object"}}}},
                "responses": {"200": {"description": "OK"}},
            }
        }

        # Add discovered tools as an extension to help tooling discover capabilities
        if tools:
            spec["x-mcp-tools"] = tools

        return JSONResponse(content=spec)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build dynamic openapi spec: {e}")


# Proxy endpoints for MCP so the bridge can serve /mcp and /mcp/openapi.json on the
# same public origin. This helps ChatGPT Developer Tools register and connect.
def _backend_mcp_base() -> str:
    # Allow overriding via env var for tests; default to the run_mcp_http backend.
    return os.environ.get("MCP_BACKEND_URL", "http://127.0.0.1:3339")


@app.get("/mcp/openapi.json")
def proxy_mcp_openapi() -> Response:
    backend = _backend_mcp_base()
    candidates = [f"{backend}/mcp/openapi.json", f"{backend}/openapi.json", f"{backend}/mcp"]
    for url in candidates:
        try:
            r = httpx.get(url, timeout=3.0)
            if r.status_code == 200:
                ctype = r.headers.get("content-type", "")
                # If JSON, return it as application/json
                if "application/json" in ctype or url.endswith("openapi.json"):
                    return Response(content=r.content, media_type="application/json")
                # Otherwise return as text for inspection
                return Response(content=r.text, media_type="text/plain")
        except Exception:
            continue
    # Fallback to internal dynamic spec
    try:
        spec = _build_dynamic_openapi_spec()
        return JSONResponse(content=spec, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"failed to fetch backend openapi: {e}")


@app.api_route("/mcp", methods=["GET", "POST"])
@app.api_route("/mcp/", methods=["GET", "POST"])
async def proxy_mcp_stream(request: Request):
    backend = _backend_mcp_base()
    url = f"{backend}/mcp"
    # Copy most headers; ensure Host is backend host
    headers = {k: v for k, v in request.headers.items()}
    # Ensure Host header targets the backend host (keep port if present)
    try:
        from urllib.parse import urlparse

        parsed = urlparse(backend)
        host_hdr = parsed.netloc or parsed.hostname or "127.0.0.1"
        headers["host"] = host_hdr
    except Exception:
        headers["host"] = "127.0.0.1"
    method = request.method.upper()
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            # Use same method as incoming request (GET for SSE, POST for session creation)
            async with client.stream(method, url, headers=headers, data=await request.body()) as resp:
                status = resp.status_code
                content_type = resp.headers.get("content-type", "text/event-stream")
                async def event_generator():
                    try:
                        async for chunk in resp.aiter_bytes():
                            if chunk:
                                yield chunk
                    except httpx.StreamClosed:
                        # Backend closed the stream; end generator cleanly
                        logger.info("mcp proxy: backend stream closed")
                        return
                    except Exception as e:
                        logger.warning("mcp proxy: stream error: %s", e)
                        return
                    finally:
                        try:
                            await resp.aclose()
                        except Exception:
                            pass

                return StreamingResponse(event_generator(), status_code=status, media_type=content_type)
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"backend mcp proxy error: {e}")
        


def _build_dynamic_openapi_spec() -> dict:
    """Attempt to build a minimal OpenAPI spec from the FastMCP server tools."""
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

    spec = {
        "openapi": "3.0.1",
        "info": {"title": "ECHO Bridge MCP (dynamic)", "version": "0.1.0"},
        "paths": {},
    }

    public = _get_public_base_url()
    if public:
        # dynamic servers entry to help clients discover the public origin
        spec["servers"] = [{"url": public}]

    spec["paths"]["/generate"] = {
        "post": {
            "summary": "Generate text (internal)",
            "requestBody": {"content": {"application/json": {"schema": {"type": "object"}}}},
            "responses": {"200": {"description": "OK"}},
        }
    }

    spec["paths"]["/bridge/link_echo_generate/echo_generate"] = {
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


@app.get("/mcp_openapi_dynamic.json")
def mcp_openapi_dynamic() -> JSONResponse:
    try:
        spec = _build_dynamic_openapi_spec()
        return JSONResponse(content=spec)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build dynamic openapi spec: {e}")


# Explicitly serve manifest and openapi JSON files with application/json to
# ensure tunnels/proxies (ngrok) receive the correct Content-Type and body.
@app.get("/public/chatgpt_tool_manifest.json")
def serve_chatgpt_manifest(request: Request) -> JSONResponse:
    public_dir = Path(__file__).resolve().parent.parent / "public"
    manifest_path = public_dir / "chatgpt_tool_manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="Manifest not found")
    try:
        data = _load_json_file(manifest_path)
        # Log the client for debugging ngrok/proxy behavior
        client = request.client.host if request.client else "unknown"
        logger.info("serving_manifest", extra={"client": client, "path": "/public/chatgpt_tool_manifest.json"})
        return JSONResponse(content=data, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read manifest: {e}")


@app.get("/public/openapi.json")
def serve_openapi(request: Request) -> JSONResponse:
    public_dir = Path(__file__).resolve().parent.parent / "public"
    openapi_path = public_dir / "openapi.json"
    if not openapi_path.exists():
        raise HTTPException(status_code=404, detail="OpenAPI not found")
    try:
        data = _load_json_file(openapi_path)
        client = request.client.host if request.client else "unknown"
        logger.info("serving_openapi", extra={"client": client, "path": "/public/openapi.json"})
        return JSONResponse(content=data, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read openapi: {e}")
