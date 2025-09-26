import httpx
url='http://127.0.0.1:3337/mcp'
payload={"jsonrpc":"2.0","id":"p2","method":"tools/call","params":{"tool":"search","arguments":{"query":"Hello","k":5}}}
headers={"Accept":"application/json, text/event-stream","Content-Type":"application/json"}
print(httpx.post(url, headers=headers, json=payload).text)
