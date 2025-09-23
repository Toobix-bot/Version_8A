import httpx
import json

url='http://127.0.0.1:3337/mcp'
payload={"jsonrpc":"2.0","id":"test-1","method":"search","params":{"query":"test","k":3}}
with httpx.Client(timeout=10.0) as c:
    r=c.post(url,json=payload)
    print(r.status_code)
    print(r.headers)
    print(r.text)
