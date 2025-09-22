from __future__ import annotations

import json
import logging
from pathlib import Path
from time import perf_counter
from typing import Any, Optional, cast, Awaitable, Callable

import yaml
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi import Request
from starlette.responses import Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
try:
    # FastMCP FastAPI integration (optional)
    from fastmcp.fastapi import mount_mcp  # type: ignore
except Exception:
    mount_mcp = None  # type: ignore
from pydantic import BaseModel

from .db import init_db
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
    if not x_bridge_key or x_bridge_key != settings.bridge_key:
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

app = FastAPI(title="ECHO-BRIDGE")
app.mount(
    "/public",
    StaticFiles(directory=str(Path(__file__).resolve().parent.parent / "public"), html=True),
    name="public",
)

# Mount MCP under /mcp
if mount_mcp:
    # Preferred helper if available
    try:
        mount_mcp(app, mcp_server, path="/mcp")
    except Exception:
        pass
else:
    # Fallback: create FastMCP ASGI app and mount directly (stateless for embedding)
    try:
        sub_app = mcp_server.http_app(path="/", stateless_http=True)
        app.mount("/mcp", sub_app, name="mcp")
    except Exception:
        pass


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


@app.post("/ingest/text", response_model=IngestResponse, dependencies=[Depends(get_api_key)])
def ingest_text(req: IngestRequest) -> IngestResponse:
    added = add_chunks(req.source, req.title, req.texts, req.meta)
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
