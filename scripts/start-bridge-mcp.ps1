param(
    [string]$BindHost = "127.0.0.1",
    [int]$BindPort = 3336
)
$ErrorActionPreference = 'Stop'
$Env:PYTHONUNBUFFERED = '1'

Write-Host "[start-bridge-mcp] Using host=$BindHost port=$BindPort"
$venv = "C:\GPT\Version_8\echo-bridge\.venv\Scripts"
if (-not (Test-Path $venv)) { throw "Virtualenv not found at $venv" }

Push-Location "C:\GPT\Version_8\echo-bridge"
try {
    Write-Host "[start-bridge-mcp] Starting uvicorn in separate window..."
    $args = @('-m','uvicorn','echo_bridge.main:app','--host',"$BindHost","--port","$BindPort","--log-level","info")
    Start-Process -FilePath "$venv\python.exe" -ArgumentList $args -WindowStyle Normal | Out-Null
    Write-Host ("[start-bridge-mcp] Uvicorn launched. URL: http://{0}:{1}" -f $BindHost,$BindPort)
}
finally {
    Pop-Location
}
