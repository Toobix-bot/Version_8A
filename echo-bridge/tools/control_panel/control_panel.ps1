<#
Interactive control panel for echo-bridge environment.
Goals:
 - Start/stop MCP backend (run_mcp_http.py)
 - Start/stop bridge (uvicorn)
 - Start quick Cloudflare tunnel and auto-patch
 - Show readiness (/action_ready) and metrics (/metrics)
 - Tail logs

This is a first minimal version; extend as needed.
#>

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Global:STATE = [ordered]@{
  BackendPID = $null
  BridgePID  = $null
  TunnelPID  = $null
  PublicURL  = $null
  Root       = (Resolve-Path (Join-Path $PSScriptRoot '..' '..'))
  BridgeDir  = (Resolve-Path (Join-Path $PSScriptRoot '..' '..' 'echo-bridge'))
  PythonExe  = 'python'
  LastAction = ''
}

function Write-Info($msg){ Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Warn($msg){ Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err($msg){ Write-Host "[ERR ] $msg" -ForegroundColor Red }

function Check-Python {
  try { Get-Command $Global:STATE.PythonExe -ErrorAction Stop | Out-Null } catch { Write-Err 'python not found'; return $false }
  return $true
}

function Start-Backend {
  if ($Global:STATE.BackendPID) { Write-Warn 'Backend already running.'; return }
  if (-not (Check-Python)) { return }
  Push-Location $Global:STATE.BridgeDir
  $args = @('run_mcp_http.py','--host','127.0.0.1','--port','3339')
  $p = Start-Process $Global:STATE.PythonExe -ArgumentList $args -NoNewWindow -PassThru
  Pop-Location
  $Global:STATE.BackendPID = $p.Id
  Write-Info "Started MCP backend PID=$($p.Id) on 127.0.0.1:3339"
}

function Stop-Backend {
  if (-not $Global:STATE.BackendPID) { Write-Warn 'Backend not running.'; return }
  try { Stop-Process -Id $Global:STATE.BackendPID -Force -ErrorAction SilentlyContinue } catch {}
  Write-Info "Stopped backend PID=$($Global:STATE.BackendPID)"; $Global:STATE.BackendPID=$null
}

function Start-Bridge {
  if ($Global:STATE.BridgePID) { Write-Warn 'Bridge already running.'; return }
  if (-not (Check-Python)) { return }
  Push-Location $Global:STATE.BridgeDir
  $env:PUBLIC_BASE_URL = $Global:STATE.PublicURL
  $env:MCP_ALLOW_FALLBACK_GET = '1'
  $args = @('-m','uvicorn','echo_bridge.main:app','--host','0.0.0.0','--port','3333','--http','h11','--workers','1')
  $p = Start-Process $Global:STATE.PythonExe -ArgumentList $args -NoNewWindow -PassThru
  Pop-Location
  $Global:STATE.BridgePID = $p.Id
  Write-Info "Started bridge PID=$($p.Id) on 0.0.0.0:3333"
}

function Stop-Bridge {
  if (-not $Global:STATE.BridgePID) { Write-Warn 'Bridge not running.'; return }
  try { Stop-Process -Id $Global:STATE.BridgePID -Force -ErrorAction SilentlyContinue } catch {}
  Write-Info "Stopped bridge PID=$($Global:STATE.BridgePID)"; $Global:STATE.BridgePID=$null
}

function Start-TunnelQuick {
  if ($Global:STATE.TunnelPID) { Write-Warn 'Tunnel already running.'; return }
  try { Get-Command cloudflared -ErrorAction Stop | Out-Null } catch { Write-Err 'cloudflared not found'; return }
  $log = Join-Path $Global:STATE.BridgeDir 'cloudflared_control.log'
  if (Test-Path $log) { Remove-Item $log -Force }
  Push-Location $Global:STATE.BridgeDir
  $cloudCmd = "cloudflared tunnel --url http://127.0.0.1:3333 run"
  $arg = "/c `"$cloudCmd`" ^> `"$log`" 2^>^&1"
  $proc = Start-Process cmd.exe -ArgumentList $arg -WindowStyle Hidden -PassThru
  Pop-Location
  $Global:STATE.TunnelPID = $proc.Id
  Write-Info "Started quick tunnel PID=$($proc.Id); waiting for URL..."
  $deadline = (Get-Date).AddSeconds(40)
  while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 800
    if (Test-Path $log) {
      try {
        $txt = Get-Content $log -Raw -ErrorAction SilentlyContinue
        $m = Select-String -InputObject $txt -Pattern "https://[\w\.-]*trycloudflare\.com[\w\./-]*" -AllMatches
        if ($m.Matches.Count -gt 0) { $Global:STATE.PublicURL = $m.Matches[0].Value; break }
        $m2 = Select-String -InputObject $txt -Pattern "https://[\w\.-]+[\w\./-]*" -AllMatches
        if (-not $Global:STATE.PublicURL -and $m2.Matches.Count -gt 0) { $Global:STATE.PublicURL = $m2.Matches[0].Value; break }
      } catch {}
    }
  }
  if (-not $Global:STATE.PublicURL) { Write-Warn 'Did not discover public URL yet.' } else { Write-Info "Public URL: $($Global:STATE.PublicURL)"; Invoke-AutoPatch }
}

function Stop-Tunnel {
  if (-not $Global:STATE.TunnelPID) { Write-Warn 'Tunnel not running.'; return }
  try { Stop-Process -Id $Global:STATE.TunnelPID -Force -ErrorAction SilentlyContinue } catch {}
  Write-Info "Stopped tunnel PID=$($Global:STATE.TunnelPID)"; $Global:STATE.TunnelPID=$null; $Global:STATE.PublicURL=$null
}

function Invoke-AutoPatch {
  $script = Join-Path $Global:STATE.BridgeDir 'scripts' 'update_public_domain.py'
  if (-not (Test-Path $script)) { Write-Warn 'update_public_domain.py not found'; return }
  if (-not $Global:STATE.PublicURL) { Write-Warn 'No PublicURL to patch'; return }
  Push-Location $Global:STATE.BridgeDir
  Write-Info "Patching specs with $($Global:STATE.PublicURL)"
  & $Global:STATE.PythonExe $script $Global:STATE.PublicURL | Out-Null
  Pop-Location
  Write-Info 'Patch done.'
}

function Show-Readiness {
  if (-not $Global:STATE.PublicURL) { Write-Warn 'No PublicURL set'; return }
  try {
    $res = Invoke-WebRequest -Uri ("$($Global:STATE.PublicURL)/action_ready") -UseBasicParsing -TimeoutSec 6
    Write-Host $res.Content
  } catch { Write-Err "Readiness fetch failed: $_" }
}

function Show-Metrics {
  try {
    $res = Invoke-WebRequest -Uri 'http://127.0.0.1:3333/metrics' -UseBasicParsing -TimeoutSec 5
    Write-Host $res.Content
  } catch { Write-Err "Metrics fetch failed: $_" }
}

function Menu {
  Write-Host ""; Write-Host '=== Echo Bridge Control Panel ===' -ForegroundColor Green
  Write-Host "Backend:  $(if($Global:STATE.BackendPID){"RUN $($Global:STATE.BackendPID)"}else{'STOP'})  | Bridge: $(if($Global:STATE.BridgePID){"RUN $($Global:STATE.BridgePID)"}else{'STOP'})  | Tunnel: $(if($Global:STATE.TunnelPID){"RUN $($Global:STATE.TunnelPID)"}else{'STOP'})"
  Write-Host "Public URL: $($Global:STATE.PublicURL)"
  Write-Host "Last Action: $($Global:STATE.LastAction)"
  Write-Host '1) Start Backend'
  Write-Host '2) Stop Backend'
  Write-Host '3) Start Bridge'
  Write-Host '4) Stop Bridge'
  Write-Host '5) Start Quick Tunnel'
  Write-Host '6) Stop Tunnel'
  Write-Host '7) Auto-Patch Specs'
  Write-Host '8) Show Readiness (/action_ready)'
  Write-Host '9) Show Metrics (/metrics)'
  Write-Host 'q) Quit'
  Write-Host 'Select:' -NoNewline
}

function Loop {
  while ($true) {
    Menu
    $choice = Read-Host
    switch ($choice) {
      '1' { Start-Backend; $Global:STATE.LastAction='Start Backend' }
      '2' { Stop-Backend; $Global:STATE.LastAction='Stop Backend' }
      '3' { Start-Bridge; $Global:STATE.LastAction='Start Bridge' }
      '4' { Stop-Bridge; $Global:STATE.LastAction='Stop Bridge' }
      '5' { Start-TunnelQuick; $Global:STATE.LastAction='Start Tunnel' }
      '6' { Stop-Tunnel; $Global:STATE.LastAction='Stop Tunnel' }
      '7' { Invoke-AutoPatch; $Global:STATE.LastAction='Auto Patch' }
      '8' { Show-Readiness; $Global:STATE.LastAction='Readiness' }
      '9' { Show-Metrics; $Global:STATE.LastAction='Metrics' }
      'q' { break }
      default { Write-Warn 'Unknown option' }
    }
  }
  Write-Info 'Exiting control panel.'
  # Optional cleanup
}

Loop
