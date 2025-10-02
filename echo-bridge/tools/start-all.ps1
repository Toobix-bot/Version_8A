<#
.SYNOPSIS
  Start-All: Backend + Bridge + ngrok/cloudflared in one go

.DESCRIPTION
  Launches MCP backend (port 3339), FastAPI bridge (port 3333), 
  optional ngrok or cloudflare tunnel, auto-patches domain, opens /panel

.PARAMETER UseTunnel
  "ngrok", "cloudflare", or "none" (default: "ngrok")

.PARAMETER McpPort
  Port for MCP backend (default: 3339)

.PARAMETER BridgePort
  Port for FastAPI bridge (default: 3333)

.PARAMETER SkipDomainPatch
  If set, skips automatic domain patching after tunnel starts

.EXAMPLE
  .\start-all.ps1 -UseTunnel ngrok
  .\start-all.ps1 -UseTunnel cloudflare
  .\start-all.ps1 -UseTunnel none
#>

param(
    [ValidateSet("ngrok","cloudflare","none")]
    [string]$UseTunnel = "ngrok",
    [int]$McpPort = 3339,
    [int]$BridgePort = 3333,
    [switch]$SkipDomainPatch = $false
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$BridgeDir = Join-Path $Root "echo-bridge"
$VenvActivate = Join-Path $BridgeDir ".venv\Scripts\Activate.ps1"

function Write-Step($msg) { Write-Host "[STEP] $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err($msg) { Write-Host "[ERROR] $msg" -ForegroundColor Red }

Write-Step "Starting Toobix Bridge Stack..."

# 1. Check prerequisites
Write-Step "Checking prerequisites..."
try { Get-Command python -ErrorAction Stop | Out-Null } catch { Write-Err "python not found"; exit 1 }
if($UseTunnel -eq "ngrok") { try { Get-Command ngrok -ErrorAction Stop | Out-Null } catch { Write-Warn "ngrok not found (tunnel will be skipped)" } }
if($UseTunnel -eq "cloudflare") { try { Get-Command cloudflared -ErrorAction Stop | Out-Null } catch { Write-Warn "cloudflared not found (tunnel will be skipped)" } }

# 2. Ensure venv + dependencies
Write-Step "Ensuring virtual environment..."
if(-not (Test-Path $VenvActivate)) {
    Write-Step "Creating venv..."
    Push-Location $BridgeDir
    python -m venv .venv
    Pop-Location
}

Write-Step "Activating venv & installing dependencies..."
& $VenvActivate
pip install -q -r (Join-Path $BridgeDir "requirements.txt")
Write-Ok "Dependencies ready"

# 3. Start MCP Backend
Write-Step "Starting MCP Backend (port $McpPort)..."
Push-Location $BridgeDir
$mcpProcess = Start-Process -WindowStyle Minimized -FilePath python `
    -ArgumentList "run_mcp_http.py","--host","127.0.0.1","--port","$McpPort" `
    -PassThru -NoNewWindow
Pop-Location
Write-Ok "MCP Backend started (PID: $($mcpProcess.Id))"
Start-Sleep -Seconds 2

# 4. Start Bridge
Write-Step "Starting FastAPI Bridge (port $BridgePort)..."
$env:MCP_ALLOW_FALLBACK_GET = "1"
$env:PUBLIC_BASE_URL = "http://127.0.0.1:$BridgePort"

Push-Location $BridgeDir
$bridgeProcess = Start-Process -WindowStyle Minimized -FilePath python `
    -ArgumentList "-m","uvicorn","echo_bridge.main:app","--host","127.0.0.1","--port","$BridgePort","--http","h11","--workers","1" `
    -PassThru -NoNewWindow
Pop-Location
Write-Ok "Bridge started (PID: $($bridgeProcess.Id))"
Start-Sleep -Seconds 3

# 5. Start Tunnel (optional)
$PublicURL = $null
if($UseTunnel -eq "ngrok") {
    Write-Step "Starting ngrok tunnel..."
    try {
        Start-Process -WindowStyle Minimized -FilePath ngrok -ArgumentList "http","$BridgePort" -PassThru | Out-Null
        Start-Sleep -Seconds 4
        $ngrokApi = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -ErrorAction SilentlyContinue
        $PublicURL = $ngrokApi.tunnels | Where-Object { $_.proto -eq "https" } | Select-Object -First 1 -ExpandProperty public_url
        if($PublicURL) {
            Write-Ok "ngrok tunnel: $PublicURL"
        } else {
            Write-Warn "Could not detect ngrok URL (check http://127.0.0.1:4040)"
        }
    } catch {
        Write-Warn "ngrok start failed: $_"
    }
}

if($UseTunnel -eq "cloudflare") {
    Write-Step "Starting Cloudflare Quick Tunnel..."
    $cfLog = Join-Path $BridgeDir "cloudflared_control.log"
    if(Test-Path $cfLog) { Remove-Item $cfLog -Force }
    
    $cloudCmd = "cloudflared tunnel --url http://127.0.0.1:$BridgePort run"
    $arg = "/c `"$cloudCmd`" ^> `"$cfLog`" 2^>^&1"
    Start-Process cmd.exe -ArgumentList $arg -WindowStyle Hidden -PassThru | Out-Null
    
    Write-Step "Waiting for Cloudflare URL (max 40s)..."
    $deadline = (Get-Date).AddSeconds(40)
    while((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 800
        if(Test-Path $cfLog) {
            try {
                $txt = Get-Content $cfLog -Raw -ErrorAction SilentlyContinue
                $m = Select-String -InputObject $txt -Pattern "https://[\w\.-]*trycloudflare\.com[\w\./-]*" -AllMatches
                if($m.Matches.Count -gt 0) {
                    $PublicURL = $m.Matches[0].Value
                    break
                }
            } catch {}
        }
    }
    if($PublicURL) {
        Write-Ok "Cloudflare tunnel: $PublicURL"
    } else {
        Write-Warn "Could not detect Cloudflare URL (check $cfLog)"
    }
}

# 6. Patch domain (if tunnel found)
if($PublicURL -and -not $SkipDomainPatch) {
    Write-Step "Patching manifest & OpenAPI with public URL..."
    $patchScript = Join-Path $BridgeDir "scripts\update_public_domain.py"
    if(Test-Path $patchScript) {
        try {
            Push-Location $BridgeDir
            & python $patchScript $PublicURL | Out-Null
            Pop-Location
            Write-Ok "Domain patched: $PublicURL"
            $env:PUBLIC_BASE_URL = $PublicURL
        } catch {
            Write-Warn "Domain patch failed: $_"
        }
    } else {
        Write-Warn "update_public_domain.py not found at $patchScript"
    }
}

# 7. Quick health check
Write-Step "Running health check..."
Start-Sleep -Seconds 2
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$BridgePort/action_ready" -ErrorAction Stop
    $allOk = $health.manifest_ok -and $health.openapi_ok -and $health.backend_sse
    if($allOk) {
        Write-Ok "Health check: ALL GREEN ✓"
    } else {
        Write-Warn "Health check: PARTIAL (manifest=$($health.manifest_ok) openapi=$($health.openapi_ok) backend=$($health.backend_sse))"
    }
} catch {
    Write-Warn "Health check failed: $_"
}

# 8. Summary & URLs
Write-Host "`n========================================" -ForegroundColor Green
Write-Host "  🚀 Toobix Bridge Stack READY" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host "Local Panel:  http://127.0.0.1:$BridgePort/panel"
Write-Host "Local MCP:    http://127.0.0.1:$McpPort/mcp"
Write-Host "Local Bridge: http://127.0.0.1:$BridgePort/mcp"
if($PublicURL) {
    Write-Host "`nPublic URLs:"
    Write-Host "  Panel:    $PublicURL/panel"
    Write-Host "  MCP:      $PublicURL/mcp"
    Write-Host "  Manifest: $PublicURL/public/chatgpt_tool_manifest.json"
    Write-Host "  OpenAPI:  $PublicURL/public/openapi.json"
    Write-Host "`nFor ChatGPT/Claude, use: $PublicURL/mcp"
}
Write-Host "`nProcesses:"
Write-Host "  MCP Backend: PID $($mcpProcess.Id)"
Write-Host "  Bridge:      PID $($bridgeProcess.Id)"
Write-Host "`nTo stop all: taskkill /PID $($mcpProcess.Id) /F ; taskkill /PID $($bridgeProcess.Id) /F"
Write-Host "========================================`n" -ForegroundColor Green

# 9. Open panel in browser
Start-Sleep -Seconds 1
if($PublicURL) {
    Start-Process "$PublicURL/panel"
} else {
    Start-Process "http://127.0.0.1:$BridgePort/panel"
}

Write-Ok "Panel opened in browser. Press Ctrl+C to exit (processes will continue in background)."
