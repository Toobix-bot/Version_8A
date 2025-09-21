# ECHO-BRIDGE (MVP)

Local bridge for context and controlled actions. FastAPI + SQLite FTS5. Binds 127.0.0.1 only.

## Quickstart

- Python 3.11+
- Create venv and install deps:

```
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
```

Start server:

```
uvicorn echo_bridge.main:app --host 127.0.0.1 --port 3333
```

Example requests in docs and tests. See `config.yaml` for settings.

## Security

- Write routes require `X-Bridge-Key` header.
- File system routes are read-only and sandboxed to `workspace/`.
- No external network writes; all actions audited.

## License

MIT (project scaffold)