import httpx
import json

LOCAL = 'http://127.0.0.1:3337/mcp'
NGROK = 'https://multiplicative-unapprehendably-marisha.ngrok-free.dev/mcp'

# Candidate payload shapes to try
payloads = [
    {"jsonrpc": "2.0", "id": "p1", "method": "tools.invoke", "params": {"name": "list_resources", "input": {}}},
    {"jsonrpc": "2.0", "id": "p2", "method": "tools.invoke", "params": {"name": "list_resources", "args": {}}},
    {"jsonrpc": "2.0", "id": "p3", "method": "list_resources", "params": {}},
    {"jsonrpc": "2.0", "id": "p4", "method": "list_resources", "params": {"q": "test"}},
]

urls = [LOCAL, NGROK]

for url in urls:
    print('\n== URL:', url)
    for p in payloads:
        try:
            with httpx.Client(timeout=10.0) as c:
                r = c.post(url, json=p)
                print('\n->', p['id'], 'status=', r.status_code)
                try:
                    print(json.dumps(r.json(), indent=2, ensure_ascii=False))
                except Exception:
                    txt = r.text or ''
                    print('raw:', txt[:800])
        except Exception as e:
            print('\nERR', e)

