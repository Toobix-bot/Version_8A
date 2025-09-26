ECHO-Bridge: Generate API (Groq)

Quickstart

1. Copy `.env.example` to `.env` and set `GROQ_API_KEY`.
2. Create a venv and install requirements:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate    # Windows
   pip install -r requirements.txt
   ```

3. Start the API:

   ```bash
   uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 3333
   ```

4. Smoke test:

   ```bash
   curl -s http://127.0.0.1:3333/generate -H "Content-Type: application/json" -d '{"prompt":"Schreibe kurz","contextIds":["1"]}'
   ```

Notes

- The `apps.api.main` uses the `groq` SDK if installed; otherwise it falls back to an echo response to simplify local dev without keys.
- For production, set `GROQ_API_KEY` as environment variable in your deployment platform (Render, Vercel, etc.).

---

# Quickstart (Edit Pack 01 additions)

## Setup

- Copy `.env.example` to `.env` and set `GROQ_API_KEY` (optional) and `API_KEY` if you want protected routes.

```bash
python -m venv .venv
.venv\Scripts\activate    # Windows
pip install -r requirements.txt
uvicorn echo_bridge.main:app --reload --host 127.0.0.1 --port 3333
```

## Endpoints

* `GET /healthz` → `{ ok: true }`
* `POST /ingest { source, title?, text?, tags?[] }` → `{ id }`
* `POST /search { query, k? }` → `{ results: [{ id, title, snippet, tags[] }] }`
* `POST /fetch { id }` → `{ id, title, content: [{type:"text", text}], metadata }`
* `POST /generate { prompt, contextIds[], ... }` → `{ text, sources }` (Dummy when no GROQ_API_KEY)

> For protected routes: send header `X-API-Key: <API_KEY>` when `API_KEY` is set in `.env`.
