"""Smoke test: call echo_generate via MCP tools/call and via bridge endpoint.

Run from repo root: python echo-bridge\scripts\echo_generate_smoke.py
"""
import json
import httpx

MCP_URL = "http://127.0.0.1:3337/mcp"
BRIDGE_URL = "http://127.0.0.1:3333/bridge/link_echo_generate/echo_generate"

def call_mcp_generate(prompt="Hallo Welt"):
    payload = {"jsonrpc":"2.0","id":"g1","method":"tools/call","params":{"name":"echo_generate","arguments":{"prompt":prompt}}}
    headers = {"Content-Type":"application/json","Accept":"application/json, text/event-stream"}
    with httpx.Client(timeout=10.0) as c:
        r = c.post(MCP_URL, json=payload, headers=headers)
        print('MCP STATUS', r.status_code)
        print(r.text[:4000])

def call_bridge_generate(prompt="Hallo Welt", key=None):
    headers = {"Content-Type":"application/json"}
    if key:
        headers["X-API-Key"] = key
    with httpx.Client(timeout=10.0) as c:
        r = c.post(BRIDGE_URL, json={"prompt":prompt}, headers=headers)
        print('BRIDGE STATUS', r.status_code)
        try:
            print(json.dumps(r.json(), indent=2, ensure_ascii=False))
        except Exception:
            print(r.text[:2000])

if __name__ == '__main__':
    print('Calling MCP...')
    call_mcp_generate('Eine kurze Szene über einen Regen.')
    print('\nCalling Bridge...')
    call_bridge_generate('Eine kurze Szene über einen Regen.')
