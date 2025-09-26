import httpx, json

URL = "http://127.0.0.1:3337/mcp"
payload = {"jsonrpc": "2.0", "id": "list1", "method": "tools/list", "params": {}}
headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
with httpx.Client(timeout=10.0) as c:
    r = c.post(URL, headers=headers, json=payload)
    print('STATUS', r.status_code)
    print(r.text[:8000])
    idx = r.text.find('{"jsonrpc')
    if idx!=-1:
        try:
            obj = json.loads(r.text[idx:])
            print('\nPARSED:')
            print(json.dumps(obj, indent=2, ensure_ascii=False)[:8000])
        except Exception as e:
            print('parse err', e)
