param(
    [string]$BindHost = "127.0.0.1",
    [int]$BindPort = 3336
)
$ErrorActionPreference = 'Stop'
$Env:PYTHONUNBUFFERED = '1'

Write-Host "[start-minimal-mcp] Using host=$BindHost port=$BindPort"
$venv = "C:\GPT\Version_8\echo-bridge\.venv\Scripts"
if (-not (Test-Path $venv)) { throw "Virtualenv not found at $venv" }

& "$venv\pip.exe" install fastmcp fastapi uvicorn --disable-pip-version-check | Write-Host

Push-Location "C:\GPT\Version_8"
try {
    Write-Host "[start-minimal-mcp] Starting server_min.py in separate window..."
    Start-Process -FilePath "$venv\python.exe" -ArgumentList @('.\server_min.py') -WindowStyle Normal | Out-Null
    Write-Host ("[start-minimal-mcp] Launched. URL: http://{0}:{1}/mcp" -f $BindHost,$BindPort)
}
finally {
    Pop-Location
}
