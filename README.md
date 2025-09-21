# Version_8A Workspace

See `echo-bridge/` for ECHO-BRIDGE project (FastAPI + SQLite FTS5).

Quick start on Windows PowerShell:

```
cd echo-bridge
python -m venv .venv; .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn echo_bridge.main:app --host 127.0.0.1 --port 3333
```

