import httpx
import json

URL = "http://127.0.0.1:3337/mcp"

payload = {
    "jsonrpc": "2.0",
    "id": "one",
    "method": "tools/call",
    "params": {
        "name": "echo_search",
        "arguments": {"q": "Hello", "limit": "5"}
    }
}

headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}

def main():
    with httpx.Client(timeout=10.0) as c:
        r = c.post(URL, headers=headers, json=payload)
        print('STATUS', r.status_code)
        print('HEADERS', r.headers)
        print('TEXT')
        print(r.text)
        try:
            # try to parse any JSON inside
            idx = r.text.find('{"jsonrpc')
            if idx != -1:
                js = r.text[idx:]
                print('\nPARSED JSON:')
                print(json.dumps(json.loads(js), indent=2, ensure_ascii=False))
        except Exception as e:
            print('parse error', e)

if __name__ == '__main__':
    main()
