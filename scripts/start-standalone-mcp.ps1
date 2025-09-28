param(
    [string]$BindHost = "0.0.0.0",
    [int]$BindPort = 3337
)
$ErrorActionPreference = 'Stop'
$Env:PYTHONUNBUFFERED = '1'

Write-Host "[start-standalone-mcp] Using host=$BindHost port=$BindPort"
$venv = "C:\GPT\Version_8\echo-bridge\.venv\Scripts"
if (-not (Test-Path $venv)) { throw "Virtualenv not found at $venv" }

Push-Location "C:\GPT\Version_8\echo-bridge"
try {
    Write-Host "[start-standalone-mcp] Starting FastMCP HTTP server..."
    $args = @('run_mcp_http.py','--host',"$BindHost",'--port',"$BindPort")
    Start-Process -FilePath "$venv\python.exe" -ArgumentList $args -WindowStyle Normal | Out-Null
    Write-Host ("[start-standalone-mcp] Launched. URL: http://{0}:{1}/mcp" -f $BindHost,$BindPort)
}
finally {
    Pop-Location
}
