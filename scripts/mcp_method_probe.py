import httpx

url='http://127.0.0.1:3337/mcp'
headers={"Accept":"application/json, text/event-stream"}
methods=[
    'tools.list','tools.get','tools.invoke','tools','tool.list','list_tools','mcp.list','list','rpc.discover','server.listMethods','jsonrpc.discover'
]

with httpx.Client(timeout=10.0) as c:
    for m in methods:
        payload={"jsonrpc":"2.0","id":m+"-id","method":m,"params":{}}
        try:
            r=c.post(url,json=payload,headers=headers)
            print('---',m,'status',r.status_code)
            txt=r.text
            if len(txt)>400:
                txt=txt[:400]+'...'
            print(txt)
        except Exception as e:
            print('---',m,'error',e)
