import httpx
import json

URL = "http://127.0.0.1:3337/mcp"

def call(tool: str, arguments: dict):
    # FastMCP expects params.name and params.arguments
    # stringify simple numeric args for compatibility
    safe_args = {k: (str(v) if isinstance(v, (int, float)) else v) for k, v in (arguments or {}).items()}
    payload = {"jsonrpc": "2.0", "id": "probe1", "method": "tools/call", "params": {"name": tool, "arguments": safe_args}}
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    with httpx.Client(timeout=20.0) as c:
        r = c.post(URL, headers=headers, json=payload)
        print("STATUS:", r.status_code)
        # The adapter returns SSE; print the raw text then try to extract JSON blobs
        print(r.text[:4000])
        # attempt to find JSON substring
        try:
            # naive: find first '{"jsonrpc' occurrence
            idx = r.text.find('{"jsonrpc')
            if idx != -1:
                txt = r.text[idx:]
                obj = json.loads(txt)
                print(json.dumps(obj, indent=2, ensure_ascii=False))
        except Exception:
            pass


if __name__ == '__main__':
    print('call echo_search')
    call('echo_search', {'q': 'Hello', 'limit': 5})
    print('\ncall echo_ingest')
    call('echo_ingest', {'source': 'probe', 'title': 'probe', 'text': 'Probe ingest text', 'tags': ['probe']})
