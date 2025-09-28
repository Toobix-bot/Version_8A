<#
Start all local services for the echo-bridge project (MCP backend, bridge, cloudflared)

Usage:
  # From repository root (C:\GPT\Version_8)
  .\scripts\start_services.ps1

Optional environment variables (passed as parameters):
  -ApiKey <string>               # sets API_KEY for the bridge (if omitted, API_KEY is not set)
  -AllowUnauthBridge <switch>    # set to allow unauthenticated bridge calls for testing

The script:
  - ensures the logs directory exists
  - stops any running cloudflared/python processes that may conflict
  - starts each service in a new PowerShell window and writes logs under echo-bridge\logs
  - prints a short status summary and (if available) tails the cloudflared log so you can copy the public URL
#>

param(
    [string] $ApiKey = $null,
    [switch] $AllowUnauthBridge
)

Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$bridgeDir = Join-Path $repoRoot 'echo-bridge'
$logsDir = Join-Path $bridgeDir 'logs'

# Ensure logs directory exists
if (-not (Test-Path $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
}

Write-Host "Repository root: $repoRoot"
Write-Host "Bridge dir: $bridgeDir"
Write-Host "Logs dir: $logsDir"

function Stop-IfRunning([string]$name) {
    $procs = Get-Process -Name $name -ErrorAction SilentlyContinue
    if ($procs) {
        Write-Host "Stopping existing process(es) named $name"
        $procs | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 300
    }
}

# Stop likely conflicting processes
Stop-IfRunning -name 'cloudflared'
Stop-IfRunning -name 'python'

Start-Sleep -Milliseconds 300

function Start-Window($title, $command, $workingDir) {
    # Build argument list for Start-Process. We include -NoExit so the new window stays open.
    $startArgs = @('-NoExit', '-Command', "Set-Location '$workingDir'; $command")
    Start-Process -FilePath 'powershell' -ArgumentList $startArgs -WorkingDirectory $workingDir
    Write-Host "Started: $title"
}

# Start MCP backend (echo-bridge/run_mcp_http.py)
$mcpCmd = ". .\.venv\Scripts\Activate.ps1; python .\run_mcp_http.py --host 127.0.0.1 --port 3339 2>&1 | Tee-Object -FilePath .\logs\mcp.log"
Start-Window -title 'MCP Backend' -command $mcpCmd -workingDir $bridgeDir

# Prepare bridge start command with optional env vars
$envCmdParts = @()
if ($ApiKey) {
    # create a literal assignment like: $env:API_KEY='value'
    $envCmdParts += ("`$env:API_KEY='" + $ApiKey + "'")
}
if ($AllowUnauthBridge) {
    $envCmdParts += "`$env:ALLOW_UNAUTH_BRIDGE='true'"
}
$envCmd = ''
if ($envCmdParts.Count -gt 0) { $envCmd = ($envCmdParts -join "; ") + "; " }

$bridgeCmd = ($envCmd + ". .\\.venv\\Scripts\\Activate.ps1; python -m uvicorn echo_bridge.main:app --host 0.0.0.0 --port 3333 2>&1 | Tee-Object -FilePath .\\logs\\bridge.log")
Start-Window -title 'Bridge (uvicorn)' -command $bridgeCmd -workingDir $bridgeDir

# Start cloudflared (expects cloudflared.exe in repo root)
$cloudflaredPath = Join-Path $repoRoot 'cloudflared.exe'
if (-Not (Test-Path $cloudflaredPath)) {
    Write-Warning "cloudflared.exe not found at $cloudflaredPath. Skipping cloudflared start. If you want public exposure, place cloudflared.exe in the repo root."
} else {
    $cloudCmd = ".\cloudflared.exe tunnel --url http://127.0.0.1:3333 2>&1 | Tee-Object -FilePath .\logs\cloudflared.log"
    Start-Window -title 'cloudflared' -command $cloudCmd -workingDir $repoRoot
}

Write-Host "Started services. Waiting 2s for logs to populate..."
Start-Sleep -Seconds 2

Write-Host "--- Short log previews ---"
if (Test-Path (Join-Path $logsDir 'mcp.log')) { Get-Content (Join-Path $logsDir 'mcp.log') -Tail 10 | ForEach-Object { Write-Host $_ } }
if (Test-Path (Join-Path $logsDir 'bridge.log')) { Get-Content (Join-Path $logsDir 'bridge.log') -Tail 20 | ForEach-Object { Write-Host $_ } }
if (Test-Path (Join-Path $repoRoot 'logs\cloudflared.log')) { Write-Host "(cloudflared log follows)"; Get-Content (Join-Path $repoRoot 'logs\cloudflared.log') -Tail 40 | ForEach-Object { Write-Host $_ } }

Write-Host "If cloudflared started, copy the public trycloudflare URL from cloudflared.log (look for .trycloudflare.com)."
Write-Host "If bridge rejects POSTs with 401, either run this script with -ApiKey 'your_key' or use -AllowUnauthBridge to bypass auth for local testing."
