param(
    [int]$Port = 3337
)
$ErrorActionPreference = 'Stop'

function Test-NgrokInstalled {
    try {
        $v = & ngrok version 2>$null
        return $true
    } catch {
        return $false
    }
}

if (-not (Test-NgrokInstalled)) {
    Write-Host "[start-ngrok-mcp] ngrok not found in PATH. Install from https://ngrok.com/download and sign in: 'ngrok config add-authtoken <token>'"
    exit 1
}

Write-Host "[start-ngrok-mcp] Starting tunnel to http://127.0.0.1:$Port"
Start-Process -FilePath "ngrok" -ArgumentList @('http','http://127.0.0.1:$Port') -WindowStyle Normal
Write-Host "[start-ngrok-mcp] Tunnel launched. Open ngrok dashboard http://127.0.0.1:4040 for the public HTTPS URL."
