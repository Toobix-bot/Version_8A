import httpx, json

URL = "http://127.0.0.1:3337/mcp"
payload = {"jsonrpc": "2.0", "id": "call1", "method": "tools/call", "params": {"name": "echo_search", "arguments": {"query": "Hello", "k": 3}}}
headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
with httpx.Client(timeout=30.0) as c:
    r = c.post(URL, headers=headers, json=payload)
    print('STATUS', r.status_code)
    print(r.text[:20000])
    idx = r.text.find('{"jsonrpc')
    if idx!=-1:
        try:
            obj = json.loads(r.text[idx:])
            print('\nPARSED:')
            print(json.dumps(obj, indent=2, ensure_ascii=False)[:20000])
        except Exception as e:
            print('parse err', e)
