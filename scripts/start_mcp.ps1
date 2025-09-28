$ErrorActionPreference = 'Stop'
$cwd = 'C:\GPT\Version_8\echo-bridge'
$python = Join-Path $cwd '.venv\Scripts\python.exe'
$outLog = 'C:\GPT\Version_8\mcp_server.out.log'
$errLog = 'C:\GPT\Version_8\mcp_server.err.log'

Write-Host "Starting MCP server from $cwd using $python -> out: $outLog err: $errLog"
Start-Process -FilePath 'C:\GPT\Version_8\\echo-bridge\\.venv\\Scripts\\python.exe' -ArgumentList 'run_mcp_http.py','--host','127.0.0.1','--port','3337' -WorkingDirectory 'C:\GPT\Version_8\\echo-bridge' -RedirectStandardOutput $outLog -RedirectStandardError $errLog -NoNewWindow | Out-Null
Start-Sleep -Seconds 1
Write-Host 'MCP process started (check logs).' 
