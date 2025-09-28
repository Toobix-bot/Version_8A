<#
Automatisches Start-Skript für MCP backend, cloudflared quick-tunnel und die Bridge.

Usage: Aus dem Repo-Root (C:\GPT\Version_8) ausführen:
  .\scripts\autostart_all.ps1

Das Skript:
 - legt logs-Verzeichnisse an
 - startet run_mcp_http.py als Hintergrund-Job (logs\mcp.log)
 - startet cloudflared quick-tunnel als Hintergrund-Job (logs\cloudflared.log) falls vorhanden
 - liest die trycloudflare URL aus dem cloudflared-Log
 - startet die Bridge mit PUBLIC_BASE_URL gesetzt (logs\bridge.log)
 - gibt am Ende die public URL und kurze Log-Ausschnitte aus

Hinweis: cloudflared erzeugt die URL erst zur Laufzeit; das Skript pollt bis zu ~60s auf die URL.
#>

Set-StrictMode -Version Latest

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$scriptDir = $PSScriptRoot
# repoRoot should be one level above the scripts directory (workspace root)
$repoRoot = Split-Path -Parent $scriptDir
$bridgeDir = Join-Path $repoRoot 'echo-bridge'
$logsDir = Join-Path $bridgeDir 'logs'

if (-not (Test-Path $logsDir)) { New-Item -ItemType Directory -Path $logsDir -Force | Out-Null }

Write-Host "Repo root: $repoRoot"
Write-Host "Bridge dir: $bridgeDir"
Write-Host "Logs dir: $logsDir"

function Start-Job-Logged([string]$name, [scriptblock]$sb, [array]$arglist) {
    Write-Host "Starting job: $name"
    Start-Job -Name $name -ScriptBlock $sb -ArgumentList $arglist | Out-Null
}

# 1) Start MCP backend
$mcpSb = {
    param($bridgeDir, $logsDir)
    Set-Location $bridgeDir
    if (Test-Path '.\.venv\Scripts\Activate.ps1') { . .\.venv\Scripts\Activate.ps1 }
    # run and append logs
    & python .\run_mcp_http.py --host 127.0.0.1 --port 3339 *>&1 | Out-File -FilePath (Join-Path $logsDir 'mcp.log') -Append
}
Start-Job-Logged 'mcp' $mcpSb @($bridgeDir, $logsDir)

# Wait for MCP to accept connections (timeout ~30s)
Write-Host "Waiting for MCP on 127.0.0.1:3339..."
$mcpReady = $false
for ($i=0; $i -lt 30; $i++) {
    try { if ((Test-NetConnection -ComputerName '127.0.0.1' -Port 3339 -WarningAction SilentlyContinue).TcpTestSucceeded) { $mcpReady = $true; break } } catch { }
    Start-Sleep -Seconds 1
}
if (-not $mcpReady) { Write-Warning "MCP didn't become ready within timeout. Check logs\mcp.log" }
else { Write-Host "MCP appears ready." }

# 2) Start cloudflared (if available)
$cloudExe = Join-Path $repoRoot 'cloudflared.exe'
$publicUrl = $null
if (Test-Path $cloudExe) {
    $cloudSb = {
        param($repoRoot)
        Set-Location $repoRoot
        & .\cloudflared.exe tunnel --url http://127.0.0.1:3333 *>&1 | Out-File -FilePath (Join-Path $repoRoot 'logs\cloudflared.log') -Append
    }
    Start-Job-Logged 'cloudflared' $cloudSb @($repoRoot)

    # Poll cloudflared log for trycloudflare URL
    $cloudLog = Join-Path $repoRoot 'logs\cloudflared.log'
    Write-Host "Waiting for cloudflared quick-tunnel URL (up to 60s)..."
    for ($i=0; $i -lt 60; $i++) {
        if (Test-Path $cloudLog) {
            try { $txt = Get-Content $cloudLog -Raw -ErrorAction SilentlyContinue } catch { $txt = '' }
            if ($txt -match 'https?://\S+?\.trycloudflare\.com') { $publicUrl = $matches[0]; break }
        }
        Start-Sleep -Seconds 1
    }
    if ($publicUrl) { Write-Host "Found public URL: $publicUrl" } else { Write-Warning "No quick-tunnel URL detected in cloudflared.log" }
} else {
    Write-Warning "cloudflared.exe not found in repo root ($repoRoot). Skipping quick-tunnel start."
}

# 3) Start Bridge with PUBLIC_BASE_URL if available
$bridgeSb = {
    param($bridgeDir, $logsDir, $publicUrl)
    Set-Location $bridgeDir
    if (Test-Path '.\.venv\Scripts\Activate.ps1') { . .\.venv\Scripts\Activate.ps1 }
    if ($publicUrl) { $env:PUBLIC_BASE_URL = $publicUrl }
    & python -m uvicorn echo_bridge.main:app --host 0.0.0.0 --port 3333 *>&1 | Out-File -FilePath (Join-Path $logsDir 'bridge.log') -Append
}
Start-Job-Logged 'bridge' $bridgeSb @($bridgeDir, $logsDir, $publicUrl)

# 4) Summary / Tail logs
Start-Sleep -Seconds 2
Write-Host "--- Summary ---"
if ($publicUrl) { Write-Host "Public URL: $publicUrl" }
Write-Host "MCP log (tail):"
if (Test-Path (Join-Path $logsDir 'mcp.log')) { Get-Content (Join-Path $logsDir 'mcp.log') -Tail 20 | ForEach-Object { Write-Host $_ } } else { Write-Host "(no mcp.log yet)" }
Write-Host "Bridge log (tail):"
if (Test-Path (Join-Path $logsDir 'bridge.log')) { Get-Content (Join-Path $logsDir 'bridge.log') -Tail 40 | ForEach-Object { Write-Host $_ } } else { Write-Host "(no bridge.log yet)" }
if (Test-Path (Join-Path $repoRoot 'logs\cloudflared.log')) { Write-Host "cloudflared log (tail):"; Get-Content (Join-Path $repoRoot 'logs\cloudflared.log') -Tail 80 | ForEach-Object { Write-Host $_ } }

Write-Host "Done. If the quick-tunnel URL was found, use it as PUBLIC_BASE_URL for ChatGPT registration. Use .\scripts\manage_pwsh_windows.ps1 to inspect background jobs or stop them if needed."
