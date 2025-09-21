from fastapi import WebSocket, WebSocketDisconnect, APIRouter
from echo_bridge.services.memory_service import search, add_chunks
from echo_bridge.services.fs_service import list_dir, read_file
from echo_bridge.services.actions_service import dispatch

router = APIRouter()

@router.websocket("/mcp")
async def mcp_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            tool = data.get("tool")
            args = data.get("args", {})
            tier_mode = data.get("tier_mode")
            try:
                if tool == "memory.search":
                    result = search(args.get("query", ""), args.get("k", 5))
                elif tool == "memory.add":
                    result = {"inserted": add_chunks(args.get("source"), args.get("title"), args.get("texts", []), args.get("meta"))}
                elif tool == "fs.list":
                    result = list_dir(args.get("workspace_dir"), args.get("subdir"))
                elif tool == "fs.read":
                    result = read_file(args.get("workspace_dir"), args.get("path"))
                elif tool == "actions.run":
                    result = dispatch(args.get("command"), args.get("args", {}))
                else:
                    result = {"error": "Unknown tool"}
            except Exception as e:
                result = {"error": str(e)}
            await websocket.send_json(result)
    except WebSocketDisconnect:
        pass

import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .ai.brain import Policy
from .services.memory_service import search as mem_search, add_chunks
from .services.fs_service import list_dir, read_file, FSError
from .services.actions_service import dispatch, ActionError


def register_mcp(app, settings) -> None:
    router = APIRouter()

    @router.websocket("/mcp/ws")
    async def mcp_ws(ws: WebSocket):
        await ws.accept()
        authed = False
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                except Exception:
                    await ws.send_text(json.dumps({"id": None, "error": {"message": "invalid json"}}))
                    continue
                mid = msg.get("id")
                method = msg.get("method")
                params = msg.get("params") or {}
                try:
                    if method == "auth":
                        key = params.get("key")
                        authed = bool(key) and (key == settings.bridge_key)
                        await ws.send_text(json.dumps({"id": mid, "result": {"ok": authed}}))
                    elif method == "memory.search":
                        q = params.get("query", "")
                        k = int(params.get("k", 5))
                        hits = mem_search(q, k)
                        await ws.send_text(
                            json.dumps({"id": mid, "result": [h.model_dump() for h in hits]}, ensure_ascii=False)
                        )
                    elif method == "memory.add":
                        if not authed:
                            raise PermissionError("auth required")
                        source = params.get("source", "journal")
                        title = params.get("title")
                        texts = params.get("texts") or []
                        meta = params.get("meta")
                        n = add_chunks(source, title, texts, meta)
                        await ws.send_text(json.dumps({"id": mid, "result": {"inserted": n}}))
                    elif method == "fs.list":
                        subdir = params.get("subdir")
                        items = list_dir(settings.workspace_dir, subdir)
                        await ws.send_text(json.dumps({"id": mid, "result": {"items": items}}, ensure_ascii=False))
                    elif method == "fs.read":
                        path = params.get("path")
                        text = read_file(settings.workspace_dir, path)
                        await ws.send_text(json.dumps({"id": mid, "result": {"path": path, "text": text}}, ensure_ascii=False))
                    elif method == "actions.run":
                        # Write actions require auth; enforce minimally based on command name
                        cmd = params.get("command")
                        args = params.get("args") or {}
                        write_commands = {"memory.add", "memory.tag", "memory.group", "game.new", "game.choose"}
                        if cmd in write_commands and not authed:
                            raise PermissionError("auth required")
                        policy = Policy(s1=settings.ai_s1, s2=settings.ai_s2, s3=settings.ai_s3)
                        result = dispatch(cmd, args, policy)
                        await ws.send_text(json.dumps({"id": mid, "result": result}, ensure_ascii=False))
                    else:
                        await ws.send_text(json.dumps({"id": mid, "error": {"message": "unknown method"}}))
                except (ActionError, FSError, PermissionError) as e:
                    await ws.send_text(json.dumps({"id": mid, "error": {"message": str(e)}}))
                except Exception as e:
                    await ws.send_text(json.dumps({"id": mid, "error": {"message": "server error"}}))
        except WebSocketDisconnect:
            return

    app.include_router(router)
