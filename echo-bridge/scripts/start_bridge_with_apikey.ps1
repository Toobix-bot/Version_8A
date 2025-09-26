param(
    [string]$ApiKey = 'test-secret-123',
    [string]$BindHost = '127.0.0.1',
    [int]$Port = 3333
)

$env:API_KEY = $ApiKey
$env:PYTHONPATH = Join-Path $PSScriptRoot '..' # points to echo-bridge

$python = Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe'
$log = Join-Path $PSScriptRoot '..\bridge.log'
# Try removing old log but don't fail if it's locked by another process
if (Test-Path $log) {
    try {
        Remove-Item $log -Force -ErrorAction Stop
    } catch {
        Write-Host "Warning: could not remove existing log file (may be in use). Continuing."
    }
}

Write-Host "Starting bridge with API_KEY='$ApiKey' using $python"

# Stop any running python/uvicorn instances (best-effort)
Get-Process -Name python -ErrorAction SilentlyContinue | ForEach-Object { $_.CloseMainWindow(); Start-Sleep -Milliseconds 200 }
Start-Sleep -Seconds 1

# Start uvicorn using Start-Process so it continues after this script exits.
# On some PowerShell versions RedirectStandardOutput/RedirectStandardError
# combinations cause errors; to keep compatibility we do not redirect here.
$argList = '-m','uvicorn','echo_bridge.main:app','--host',$BindHost,'--port',$Port
Start-Process -FilePath $python -ArgumentList $argList -WorkingDirectory (Join-Path $PSScriptRoot '..') -NoNewWindow
Start-Sleep -Seconds 2

# Tail the log if present; without redirection uvicorn will write to the console
if (Test-Path $log) { Get-Content $log -Tail 200 } else { Write-Host 'No bridge.log present; check console output for server logs.' }

# Check port
if ((netstat -ano | findstr ":$Port") -ne $null) { Write-Host "Bridge running on $Port" } else { Write-Host "Bridge not running" }
