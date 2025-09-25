import httpx
import json

url='http://127.0.0.1:3337/mcp'
payload={"jsonrpc":"2.0","id":"test-1","method":"search","params":{"query":"test","k":3}}
with httpx.Client(timeout=10.0) as c:
    headers={"Accept": "application/json, text/event-stream"}
    r=c.post(url,json=payload, headers=headers)
    print(r.status_code)
    print(r.headers)
    print(r.text)
