import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx

# Optional: if `groq` lib is available, import it; otherwise we'll fallback to httpx calls
try:
    from groq import Groq
    _HAS_GROQ = True
except Exception:
    _HAS_GROQ = False

app = FastAPI(title="ECHO-Bridge API")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
BRIDGE_BASE_URL = os.getenv("BRIDGE_BASE_URL", "http://127.0.0.1:3333")

if not GROQ_API_KEY:
    # don't hard-fail on import — raise on call instead so devs can run tests without a key
    pass

if _HAS_GROQ and GROQ_API_KEY:
    groq_client = Groq(api_key=GROQ_API_KEY)
else:
    groq_client = None


class GenerateIn(BaseModel):
    prompt: str
    contextIds: Optional[List[str]] = None
    model: Optional[str] = "moonshotai/kimi-k2-instruct"
    temperature: Optional[float] = 0.6
    max_tokens: Optional[int] = 800


class GenerateOut(BaseModel):
    text: str
    sources: List[dict]


async def fetch_chunk(chunk_id: str) -> dict:
    url = f"{BRIDGE_BASE_URL}/fetch"
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(url, json={"id": chunk_id})
        r.raise_for_status()
        return r.json()


async def bridge_search(q: str, k: int = 5) -> list[dict]:
    """Call the Bridge HTTP /search endpoint and return the hits list.

    The Bridge exposes /search as a GET endpoint returning a JSON
    object matching SearchResponse (hits list). We normalize to a list
    of dicts with an 'id' field.
    """
    url = f"{BRIDGE_BASE_URL}/search"
    async with httpx.AsyncClient(timeout=20.0) as client:
        # Bridge search is a GET endpoint with q and k
        r = await client.get(url, params={"q": q, "k": k})
        r.raise_for_status()
        data = r.json()
        hits = data.get("hits") or data.get("results") or []
        # Normalize rows to dicts with string ids
        norm = []
        for h in hits:
            try:
                # hit may be a mapping or object
                hid = h.get("id") if isinstance(h, dict) else None
            except Exception:
                hid = None
            if hid is None:
                # try index-based access
                try:
                    hid = str(h["id"])
                except Exception:
                    hid = None
            if hid is not None:
                norm.append({"id": str(hid), **(h if isinstance(h, dict) else {})})
        return norm


def build_system_prompt() -> str:
    return (
        "Du bist der Erzähler/Assistent von ECHO-REALM. "
        "Halte Kanon und Widerspruchsfreiheit. Antworte prägnant, mit klaren Schritten. "
        "Wenn Kontext fehlt, sag es offen und schlage nächste Schritte vor."
    )


def build_user_prompt(user_prompt: str, contexts: List[dict]) -> List[dict]:
    parts = []
    for c in contexts:
        title = c.get("title") or ""
        text_items = c.get("content", [])
        body = ""
        for t in text_items:
            if isinstance(t, dict) and t.get("type") == "text":
                body += t.get("text", "")
        if body:
            parts.append(f"# {title}\n{body.strip()[:2000]}")
    ctx_block = "\n\n".join(parts)
    content = f"Benutzeranfrage:\n{user_prompt.strip()}\n\n---\nKontext:\n{ctx_block}" if parts else user_prompt
    return [
        {"role": "system", "content": build_system_prompt()},
        {"role": "user", "content": content},
    ]


@app.post("/generate", response_model=GenerateOut)
async def generate(body: GenerateIn):
    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not configured in environment")

    contexts = []
    if body.contextIds:
        fetched = []
        for cid in body.contextIds[:8]:
            try:
                fetched.append(await fetch_chunk(cid))
            except Exception:
                pass
        contexts = fetched
    else:
        # No explicit context IDs provided: use Bridge search as a fallback
        try:
            hits = await bridge_search(body.prompt, k=5)
            # fetch top-k chunk contents
            fetched = []
            for h in hits[:8]:
                cid = h.get("id")
                if cid:
                    try:
                        fetched.append(await fetch_chunk(cid))
                    except Exception:
                        pass
            contexts = fetched
        except Exception:
            contexts = []

    messages = build_user_prompt(body.prompt, contexts)

    # Call Groq
    try:
        if groq_client is not None:
            resp = groq_client.chat.completions.create(
                model=body.model,
                messages=messages,
                temperature=body.temperature,
                max_tokens=body.max_tokens,
            )
            text = resp.choices[0].message.content
        else:
            # Fallback: do a simple echo-ish response when Groq SDK isn't installed
            text = "(groq-sdk not installed) " + body.prompt[:1000]
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Groq error: {e}")

    sources = []
    for c in contexts:
        sources.append({"id": c.get("id"), "title": c.get("title")})

    return GenerateOut(text=text, sources=sources)
