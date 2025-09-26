"""
Run from repo root: python echo-bridge\scripts\echo_generate_smoke.py
This script calls the local MCP endpoint and the Bridge. It accepts a --bridge-key
CLI flag or BRIDGE_KEY/API_KEY environment variable to pass as X-API-Key when calling the Bridge.
"""

from __future__ import annotations

import argparse
import json
import os

import httpx

ROOT = os.path.abspath(os.path.dirname(__file__))
MCP_URL = "http://127.0.0.1:3337/mcp"
BRIDGE_URL = "http://127.0.0.1:3333/bridge/link_echo_generate/echo_generate"


# Call MCP via FastMCP HTTP endpoint (SSE stream of events)
def call_mcp(prompt: str) -> None:
    payload = {"jsonrpc": "2.0", "id": "g1", "method": "tools/call", "params": {"name": "echo_generate", "arguments": {"prompt": prompt}}}
    print("Calling MCP...")
    with httpx.stream("POST", MCP_URL, json=payload, headers={"Content-Type": "application/json", "Accept": "text/event-stream"}, timeout=15.0) as r:
        print("MCP STATUS", r.status_code)
        for line in r.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8", errors="ignore").strip()
            print(text)


def call_bridge(prompt: str, bridge_key: str | None) -> None:
    headers = {}
    if bridge_key:
        headers["X-API-Key"] = bridge_key
    print("\nCalling Bridge...")
    try:
        r = httpx.post(BRIDGE_URL, json={"prompt": prompt}, headers=headers, timeout=10.0)
        print("BRIDGE STATUS", r.status_code)
        try:
            print(json.dumps(r.json(), indent=2, ensure_ascii=False))
        except Exception:
            print(r.text)
    except Exception as e:
        print("Bridge error:", e)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Echo-bridge smoke test")
    p.add_argument("--bridge-key", help="API key to send to the Bridge (X-API-Key). If omitted, BRIDGE_KEY or API_KEY env var will be used.")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    prompt = "Eine kurze Szene über einen Regen."
    call_mcp(prompt)
    bridge_key = args.bridge_key or os.environ.get("BRIDGE_KEY") or os.environ.get("API_KEY")
    call_bridge(prompt, bridge_key)
