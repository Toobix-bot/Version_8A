import httpx

url_local = 'http://127.0.0.1:3337/mcp'
url_public = 'https://tools-ready-surface-sur.trycloudflare.com/mcp'
headers = {"Accept": "application/json, text/event-stream"}

payloads = [
    ("direct_named_params", {"jsonrpc":"2.0","id":"p1","method":"search","params":{"query":"test","k":3}}),
    ("tools_invoke_args", {"jsonrpc":"2.0","id":"p2","method":"tools.invoke","params":{"name":"search","args":{"query":"test","k":3}}}),
    ("tools_invoke_arguments", {"jsonrpc":"2.0","id":"p3","method":"tools.invoke","params":{"name":"search","arguments":{"query":"test","k":3}}}),
    ("tools_invoke_arguments_array", {"jsonrpc":"2.0","id":"p4","method":"tools.invoke","params":{"name":"search","arguments":[{"query":"test","k":3}]}}),
    ("tools_invoke_params_args_array", {"jsonrpc":"2.0","id":"p5","method":"tools.invoke","params":{"name":"search","args":[{"query":"test","k":3}]}}),
    ("invoke_name_args", {"jsonrpc":"2.0","id":"p6","method":"invoke","params":{"name":"search","args":{"query":"test","k":3}}}),
]

def try_url(url):
    print('\n== Testing', url)
    with httpx.Client(timeout=10.0) as c:
        for label, payload in payloads:
            try:
                r=c.post(url, json=payload, headers=headers)
                print('\n--', label, 'status', r.status_code)
                txt = r.text
                if len(txt)>400:
                    txt = txt[:400]+'...'
                print(txt)
            except Exception as e:
                print('\n--', label, 'exception', e)

if __name__=='__main__':
    try:
        try_url(url_local)
    except Exception as e:
        print('Local failed:', e)
    try:
        try_url(url_public)
    except Exception as e:
        print('Public failed:', e)
