$ErrorActionPreference = 'Stop'
$cwd = 'C:\GPT\Version_8\echo-bridge'
$python = Join-Path $cwd '.venv\Scripts\python.exe'
$uvicorn = Join-Path $cwd '.venv\Scripts\uvicorn.exe'
$outLog = 'C:\GPT\Version_8\uvicorn.out.log'
$errLog = 'C:\GPT\Version_8\uvicorn.err.log'

Write-Host "Starting Bridge (uvicorn) from $cwd using $uvicorn -> out: $outLog err: $errLog"
Start-Process -FilePath $uvicorn -ArgumentList 'echo_bridge.main:app','--host','127.0.0.1','--port','3333' -WorkingDirectory $cwd -RedirectStandardOutput $outLog -RedirectStandardError $errLog -NoNewWindow | Out-Null
Start-Sleep -Seconds 1
Write-Host 'Bridge process started. Check uvicorn logs for output.'
