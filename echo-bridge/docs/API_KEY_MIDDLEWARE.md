Snippet: add to the top of `echo_bridge/main.py` (or a small include module) to enable optional API key guarding for public endpoints.

```python
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os

API_KEY = os.getenv("ECHO_BRIDGE_API_KEY")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],            # set to your known origin in production
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"]
)

@app.middleware("http")
async def api_key_guard(request: Request, call_next):
    if API_KEY:
        if request.headers.get("x-api-key") != API_KEY:
            raise HTTPException(status_code=401, detail="invalid api key")
    return await call_next(request)

# ... Rest deiner Routen/Setup
```

Notes:
- Set `ECHO_BRIDGE_API_KEY` in your `.env` or environment. The existing code in the project prefers `ECHO_BRIDGE_API_KEY`, falling back to `API_KEY` or the configured `settings.bridge_key`.
- For ChatGPT Actions, set `REQUIRE_X_API_KEY_FOR_PUBLIC=true` to force the public manifest/openapi endpoints to require the header.
