import httpx, json

url='http://127.0.0.1:3337/mcp'

p={"jsonrpc":"2.0","id":"t1","method":"tools.invoke","params":{"name":"list_resources","input":{}}}
with httpx.Client(headers={'Accept':'application/json, text/event-stream'},timeout=10.0) as c:
    r=c.post(url,json=p)
    print(r.status_code)
    try:
        print(json.dumps(r.json(),indent=2,ensure_ascii=False))
    except Exception:
        print('raw:', r.text[:800])
