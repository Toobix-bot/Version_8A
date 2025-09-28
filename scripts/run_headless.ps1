<#
Run all services headless (no new windows). Starts MCP backend, bridge and cloudflared as PowerShell background jobs,
logs output to files, and prints a live status + tail view in the current console.

Usage (from repo root):
  powershell -ExecutionPolicy Bypass -File .\scripts\run_headless.ps1

Controls:
  - After start the script will show job statuses and tail logs.
  - To stop services: press Ctrl+C in this console or run the Stop command prompted at the end.
#>

Set-StrictMode -Version Latest

$scriptDir = $PSScriptRoot
<#
Run all services headless (no new windows). Starts MCP backend, bridge and cloudflared as PowerShell background jobs,
logs output to files, and prints a live status + tail view in the current console.

Usage (from repo root):
  powershell -ExecutionPolicy Bypass -File .\scripts\run_headless.ps1

Controls:
  - After start the script will show job statuses and tail logs.
  - To stop services: press Ctrl+C in this console or run the Stop command prompted at the end.
#>

Set-StrictMode -Version Latest

$scriptDir = $PSScriptRoot
$repoRoot = Split-Path -Parent $scriptDir
$bridgeDir = Join-Path $repoRoot 'echo-bridge'
$logsDir = Join-Path $bridgeDir 'logs'

if (-not (Test-Path $logsDir)) { New-Item -ItemType Directory -Path $logsDir -Force | Out-Null }
if (-not (Test-Path (Join-Path $repoRoot 'logs'))) { New-Item -ItemType Directory -Path (Join-Path $repoRoot 'logs') -Force | Out-Null }

Write-Host "Repo root: $repoRoot"
Write-Host "Bridge dir: $bridgeDir"
Write-Host "Logs dir: $logsDir"

function Start-IfNotRunning($name, [scriptblock]$sb, $arglist) {
    $existing = Get-Job -Name $name -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "Job '$name' already exists (State=$($existing.State)). Skipping start." -ForegroundColor Yellow
        return
    }
    Start-Job -Name $name -ScriptBlock $sb -ArgumentList $arglist | Out-Null
    Write-Host "Started job: $name"
}

# 1) MCP
$mcpSb = {
    param($bridgeDir, $logsDir)
    Set-Location $bridgeDir
    if (Test-Path '.\.venv\Scripts\Activate.ps1') { . .\.venv\Scripts\Activate.ps1 }
    & python .\run_mcp_http.py --host 127.0.0.1 --port 3339 *>&1 | Out-File -FilePath (Join-Path $logsDir 'mcp.log') -Append
}
Start-IfNotRunning 'mcp' $mcpSb @($bridgeDir, $logsDir)

# 2) bridge
$bridgeSb = {
    param($bridgeDir, $logsDir, $publicUrl)
    Set-Location $bridgeDir
    if (Test-Path '.\.venv\Scripts\Activate.ps1') { . .\.venv\Scripts\Activate.ps1 }
    if ($publicUrl) { $env:PUBLIC_BASE_URL = $publicUrl }
    & python -m uvicorn echo_bridge.main:app --host 0.0.0.0 --port 3333 *>&1 | Out-File -FilePath (Join-Path $logsDir 'bridge.log') -Append
}
Start-IfNotRunning 'bridge' $bridgeSb @($bridgeDir, $logsDir, $null)

# 3) cloudflared (optional)
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

function Get-LogTail([string]$path, [int]$lines=20) {
    if (Test-Path $path) { Get-Content $path -Tail $lines -ErrorAction SilentlyContinue } else { Write-Host "(no $([IO.Path]::GetFileName($path)))" }
}

Write-Host "Waiting a few seconds for jobs to initialize..."
Start-Sleep -Seconds 2

try {
    while ($true) {
        Clear-Host
        Write-Host "Service status (jobs):" -ForegroundColor Cyan
        Get-Job | Where-Object { $_.Name -in @('mcp','bridge','cloudflared') } | Format-Table Id, Name, State, HasMoreData -AutoSize
        Write-Host "`n--- Logs (tail) ---`n" -ForegroundColor Cyan
        Write-Host "mcp.log:`n" -NoNewline
        Get-LogTail (Join-Path $logsDir 'mcp.log') 10
        Write-Host "`nbridge.log:`n" -NoNewline
        Get-LogTail (Join-Path $logsDir 'bridge.log') 20
        if (Test-Path (Join-Path $repoRoot 'logs\cloudflared.log')) {
            Write-Host "`ncloudflared.log:`n" -NoNewline
            Get-LogTail (Join-Path $repoRoot 'logs\cloudflared.log') 30
        }

        Write-Host "`nPress Ctrl+C to exit monitoring. To stop jobs run: .\scripts\run_headless.ps1 -StopAll" -ForegroundColor Yellow
        Start-Sleep -Seconds 4
    }
} catch [System.Management.Automation.PipelineStoppedException] {
    Write-Host "Monitoring interrupted (Ctrl+C)." -ForegroundColor Yellow
}

<# Stop logic: if run with -StopAll parameter, stop jobs and exit. #>
param(
    [switch] $StopAll
)

if ($StopAll) {
    Write-Host "Stopping jobs mcp, bridge, cloudflared..."
    Get-Job | Where-Object { $_.Name -in @('mcp','bridge','cloudflared') } | Stop-Job -Force -ErrorAction SilentlyContinue
    Get-Job | Where-Object { $_.Name -in @('mcp','bridge','cloudflared') } | Remove-Job -Force -ErrorAction SilentlyContinue
    Write-Host "Jobs stopped. Logs remain in $logsDir and $repoRoot\logs."
}
