<#
Start ngrok (official binary) with host-header rewrite and probe public endpoints

Usage:
  - Place the official ngrok.exe in the repository root or ensure it's in PATH.
  - Optionally run: .\scripts\start_ngrok_official.ps1 -Authtoken 'YOUR_TOKEN'

This script will:
  - locate ngrok.exe
  - optionally configure authtoken
  - start ngrok http 3333 --host-header=127.0.0.1
  - poll http://127.0.0.1:4040/api/tunnels and probe /public/openapi.json and /mcp
#>

param(
    [string]$Authtoken
)

$ErrorActionPreference = 'Stop'
Write-Host "start_ngrok_official.ps1 — looking for ngrok.exe"

# try local repo copy first
$candidates = @(
    Join-Path $PSScriptRoot '..\ngrok.exe' | Resolve-Path -ErrorAction SilentlyContinue,
    'ngrok.exe'
)

$ngrokPath = $null
foreach ($p in $candidates) {
    if ($p -and (Test-Path $p)) { $ngrokPath = (Resolve-Path $p).ProviderPath; break }
}
if (-not $ngrokPath) {
    try { $ngrokPath = (where.exe ngrok.exe 2>$null | Select-Object -First 1) } catch {}
}

if (-not $ngrokPath) {
    Write-Error "ngrok.exe not found. Download the official binary from https://ngrok.com/download and place it in the repo root or in PATH."
    exit 2
}

Write-Host "Using ngrok: $ngrokPath"

if ($Authtoken) {
    Write-Host 'Configuring authtoken (if necessary)'
    & $ngrokPath authtoken $Authtoken
}

Write-Host 'Starting ngrok: http 3333 --host-header=127.0.0.1'
$proc = Start-Process -FilePath $ngrokPath -ArgumentList 'http','3333','--host-header=127.0.0.1' -PassThru
Start-Sleep -Seconds 2

Write-Host 'Polling ngrok API and probing endpoints... (timeout after 60s)'
$timeout = [DateTime]::UtcNow.AddSeconds(60)
$success = $false
while ([DateTime]::UtcNow -lt $timeout) {
    try {
        $tunnels = Invoke-RestMethod 'http://127.0.0.1:4040/api/tunnels' -TimeoutSec 3
    } catch {
        Start-Sleep -Seconds 1; continue
    }
    if (-not $tunnels.tunnels -or $tunnels.tunnels.Count -eq 0) { Start-Sleep -Seconds 1; continue }
    $pub = $tunnels.tunnels[0].public_url
    Write-Host "Public URL: $pub"
    $openapiCT = $null; $mcpCT = $null
    try {
        $r = Invoke-WebRequest -Uri ($pub + '/public/openapi.json') -UseBasicParsing -TimeoutSec 4
        $openapiCT = $r.Headers['Content-Type']
        Write-Host "openapi -> $($r.StatusCode) $openapiCT"
    } catch { Write-Host "openapi probe failed: $($_.Exception.Message)" }
    try {
        $r2 = Invoke-WebRequest -Uri ($pub + '/mcp') -Headers @{ 'Accept'='text/event-stream' } -UseBasicParsing -TimeoutSec 4
        $mcpCT = $r2.Headers['Content-Type']
        Write-Host "/mcp -> $($r2.StatusCode) $mcpCT"
    } catch { Write-Host "/mcp probe failed: $($_.Exception.Message)" }

    if ($openapiCT -and $openapiCT -match 'application/json' -and $mcpCT -and $mcpCT -match 'text/event-stream') {
        Write-Host 'SUCCESS: ngrok forwarding looks correct.'; $success = $true; break
    }
    Start-Sleep -Seconds 2
}

if (-not $success) {
    Write-Warning 'Timed out without seeing expected Content-Types. Check that you are using the official ngrok binary and that --host-header is correct.'
    if ($proc -and -not $proc.HasExited) { Write-Host "ngrok PID: $($proc.Id)" }
}

Write-Host 'Done.'
