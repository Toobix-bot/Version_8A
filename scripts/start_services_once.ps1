Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$bridgeDir = Join-Path $repoRoot 'echo-bridge'
$logsDir = Join-Path $bridgeDir 'logs'

if (-not (Test-Path $logsDir)) { New-Item -ItemType Directory -Path $logsDir -Force | Out-Null }
if (-not (Test-Path (Join-Path $repoRoot 'logs'))) { New-Item -ItemType Directory -Path (Join-Path $repoRoot 'logs') -Force | Out-Null }

function Start-IfNotRunning($name, [scriptblock]$sb, $args) {
    $existing = Get-Job -Name $name -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "Job '$name' already exists (State=$($existing.State)). Skipping start." -ForegroundColor Yellow
        return
    }
    Start-Job -Name $name -ScriptBlock $sb -ArgumentList $args | Out-Null
    Write-Host "Started job: $name"
}

# Start MCP backend
$mcpSb = {
    param($bridgeDir, $logsDir)
    Set-Location $bridgeDir
    if (Test-Path '.\.venv\Scripts\Activate.ps1') { . .\.venv\Scripts\Activate.ps1 }
    & python .\run_mcp_http.py --host 127.0.0.1 --port 3339 *>&1 | Out-File -FilePath (Join-Path $logsDir 'mcp.log') -Append
}
Start-IfNotRunning 'mcp' $mcpSb @($bridgeDir, $logsDir)

# Start cloudflared tunnel if binary exists
$cloudExe = Join-Path $repoRoot 'cloudflared.exe'
if (Test-Path $cloudExe) {
    $cloudSb = {
        param($repoRoot)
        Set-Location $repoRoot
        & .\cloudflared.exe tunnel --url http://127.0.0.1:3333 *>&1 | Out-File -FilePath (Join-Path $repoRoot 'logs\cloudflared.log') -Append
    }
    Start-IfNotRunning 'cloudflared' $cloudSb @($repoRoot)
} else {
    Write-Host "cloudflared.exe not found in repo root ($repoRoot) - tunnel will not be started." -ForegroundColor Yellow
}

Write-Host "Waiting for cloudflared to produce a trycloudflare URL..."
Start-Sleep -Seconds 6

$cloudLog = Join-Path $repoRoot 'logs\cloudflared.log'
$publicUrl = $null
if (Test-Path $cloudLog) {
    try {
        $text = Get-Content $cloudLog -ErrorAction SilentlyContinue | Out-String
        $m = [regex]::Matches($text, 'https://[\w\-\.]+\.trycloudflare\.com')
        if ($m.Count -gt 0) { $publicUrl = $m[$m.Count-1].Value }
    } catch {
        # ignore
    }
}

if ($publicUrl) { Write-Host "Found public tunnel URL: $publicUrl" } else { Write-Host "No public tunnel URL found yet." }

# Start bridge, pass PUBLIC_BASE_URL if available
if ($publicUrl) {
    $bridgeSb2 = {
        param($bridgeDir, $logsDir, $public)
        Set-Location $bridgeDir
        if (Test-Path '.\.venv\Scripts\Activate.ps1') { . .\.venv\Scripts\Activate.ps1 }
        $env:PUBLIC_BASE_URL = $public
        & python -m uvicorn echo_bridge.main:app --host 0.0.0.0 --port 3333 *>&1 | Out-File -FilePath (Join-Path $logsDir 'bridge.log') -Append
    }
    Start-IfNotRunning 'bridge' $bridgeSb2 @($bridgeDir, $logsDir, $publicUrl)
} else {
    $bridgeSb3 = {
        param($bridgeDir, $logsDir)
        Set-Location $bridgeDir
        if (Test-Path '.\.venv\Scripts\Activate.ps1') { . .\.venv\Scripts\Activate.ps1 }
        & python -m uvicorn echo_bridge.main:app --host 0.0.0.0 --port 3333 *>&1 | Out-File -FilePath (Join-Path $logsDir 'bridge.log') -Append
    }
    Start-IfNotRunning 'bridge' $bridgeSb3 @($bridgeDir, $logsDir)
}

Start-Sleep -Seconds 2

if ($publicUrl) {
    Write-Host "Probing public endpoints on $publicUrl"
    try { $m = Invoke-WebRequest -Uri "$publicUrl/public/chatgpt_tool_manifest.json" -UseBasicParsing -TimeoutSec 6 -ErrorAction Stop; Write-Host "Manifest: $($m.StatusCode) $($m.Headers['Content-Type'])" } catch { Write-Host "Manifest probe failed: $($_.Exception.Message)" }
    try { $o = Invoke-WebRequest -Uri "$publicUrl/public/openapi.json" -UseBasicParsing -TimeoutSec 6 -ErrorAction Stop; Write-Host "OpenAPI: $($o.StatusCode) $($o.Headers['Content-Type'])" } catch { Write-Host "OpenAPI probe failed: $($_.Exception.Message)" }
    try { $mo = Invoke-WebRequest -Uri "$publicUrl/mcp/openapi.json" -UseBasicParsing -TimeoutSec 6 -ErrorAction Stop; Write-Host "MCP OpenAPI: $($mo.StatusCode) $($mo.Headers['Content-Type'])" } catch { Write-Host "MCP OpenAPI probe failed: $($_.Exception.Message)" }
}

Write-Host "\n=== log tails ==="
if (Test-Path $cloudLog) { Write-Host "\ncloudflared.log:"; Get-Content $cloudLog -Tail 80 -ErrorAction SilentlyContinue }
Write-Host "\nbridge.log:"; Get-Content (Join-Path $logsDir 'bridge.log') -Tail 80 -ErrorAction SilentlyContinue
Write-Host "\nmcp.log:"; Get-Content (Join-Path $logsDir 'mcp.log') -Tail 80 -ErrorAction SilentlyContinue

if ($publicUrl) { Write-Host "\nPublic URL: $publicUrl" } else { Write-Host "\nPublic URL not available. Check cloudflared logs." }
