import httpx
base='http://127.0.0.1:3333'
for p in ['/public/chatgpt_tool_manifest.json','/public/openapi.json','/public/mcp_openapi.json']:
    try:
        r=httpx.get(base+p,timeout=5.0)
        print(p, r.status_code, len(r.text))
        print(r.text[:400])
    except Exception as e:
        print(p,'ERR',e)
