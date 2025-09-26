import sys
import json
import httpx

url = "http://127.0.0.1:3337/mcp"

def call_tool(tool_name: str, arguments: dict):
    safe_args = {k: (str(v) if isinstance(v, (int, float)) else v) for k, v in (arguments or {}).items()}
    payload = {"jsonrpc": "2.0", "id": "probe1", "method": "tools/call", "params": {"name": tool_name, "arguments": safe_args}}
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    r = httpx.post(url, headers=headers, json=payload, timeout=20.0)
    print(r.status_code)
    try:
        print(r.text)
    except Exception:
        print(r.content)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("usage: call_mcp_local.py <tool> [json-args]")
        raise SystemExit(1)
    tool = sys.argv[1]
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    call_tool(tool, args)
