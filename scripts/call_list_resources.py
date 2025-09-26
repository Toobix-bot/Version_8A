import httpx, json
url='http://127.0.0.1:3337/mcp'
p={"jsonrpc":"2.0","id":"t2","method":"tools/call","params":{"name":"list_resources","arguments":{}}}
with httpx.Client(headers={'Accept':'application/json, text/event-stream'},timeout=10.0) as c:
    r=c.post(url,json=p)
    print('status', r.status_code)
    print(r.text[:4000])
