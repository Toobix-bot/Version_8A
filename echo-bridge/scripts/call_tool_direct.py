import httpx, json

URL = "http://127.0.0.1:3337/mcp"

tests = [
    {"method": "tools/call", "params": {"name": "list_resources", "arguments": {}}},
    {"method": "tools/call", "params": {"name": "list_resources", "arguments": {"q": "Hello"}}},
    {"method": "tools/call", "params": {"name": "echo_search", "arguments": {"q": "Hello", "limit": "5"}}},
    {"method": "tools/call", "params": {"name": "echo_search", "arguments": {"query": "Hello", "k": "5"}}},
    {"method": "tools/call", "params": {"name": "echo_ingest", "arguments": {"source": "probe", "title": "t", "text": "hi", "tags": ["p"]}}},
]

def do(payload):
    obj = {"jsonrpc": "2.0", "id": "t1", **payload}
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    with httpx.Client(timeout=10.0) as c:
        r = c.post(URL, headers=headers, json=obj)
        print('PAYLOAD:', json.dumps(obj))
        print('STATUS:', r.status_code)
        print(r.text)
        print('-' * 60)


if __name__ == '__main__':
    for p in tests:
        do(p)
