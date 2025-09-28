<#
One-step helper: start cloudflared ephemeral tunnel, discover the trycloudflare URL,
write `echo-bridge/.env` with PUBLIC_BASE_URL, then start the uvicorn bridge.

Usage:
  powershell -ExecutionPolicy Bypass -File .\echo-bridge\tools\start_tunnel_and_bridge.ps1

Notes:
 - Requires `cloudflared` in PATH and `python` in PATH.
 - This script runs cloudflared in background via cmd.exe and tails the logfile to
   discover the ephemeral trycloudflare URL (if any). If it cannot find a URL,
   it leaves cloudflared running and prints the logfile location for inspection.
#>

param(
    [int]$Port = 3333,
    [int]$WaitSeconds = 30
)

function ExitWithMessage($msg, $code=1) {
    Write-Host $msg
    exit $code
}

try {
    Get-Command cloudflared -ErrorAction Stop | Out-Null
} catch {
    ExitWithMessage "cloudflared not found in PATH. Install and authenticate (cloudflared login)."
}

try {
    Get-Command python -ErrorAction Stop | Out-Null
} catch {
    ExitWithMessage "python not found in PATH. Ensure python is installed and available."
}

$repo = (Get-Location)
$working = Join-Path $repo 'echo-bridge'
if (-not (Test-Path $working)) { ExitWithMessage "echo-bridge folder not found at $working" }

$log = Join-Path $working 'cloudflared.log'
if (Test-Path $log) { Remove-Item $log -Force }

Write-Host "Starting cloudflared tunnel for local port $Port (output -> $log)"

# Start cloudflared in background by launching cmd.exe to redirect stdout/stderr to a logfile.
# Build the cmd.exe argument list to avoid nested quoting problems
$cloudCmd = "cloudflared tunnel --url http://127.0.0.1:$Port run"
$arg = "/c `"$cloudCmd`" ^> `"$log`" 2^>^&1"
Start-Process -FilePath cmd.exe -ArgumentList $arg -WorkingDirectory $working -WindowStyle Hidden -PassThru | Out-Null

# Wait for the trycloudflare URL to appear in the logfile
$deadline = (Get-Date).AddSeconds($WaitSeconds)
$public = $null
Write-Host "Waiting up to $WaitSeconds seconds for cloudflared to publish a public URL..."
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 700
    if (Test-Path $log) {
        try {
            $txt = Get-Content $log -Raw -ErrorAction SilentlyContinue
            if ($txt) {
                # Look for a trycloudflare URL or a https:// URL in the log
                $m = Select-String -InputObject $txt -Pattern "https://[\w\.-]*trycloudflare\.com[\w\./-]*" -AllMatches
                if ($m.Matches.Count -gt 0) {
                    $public = $m.Matches[0].Value
                    break
                }
                # Fallback: any https://... printed by cloudflared
                $m2 = Select-String -InputObject $txt -Pattern "https://[\w\.-]+[\w\./-]*" -AllMatches
                if ($m2.Matches.Count -gt 0) {
                    $public = $m2.Matches[0].Value
                    break
                }
            }
        } catch {}
    }
}

if ($null -eq $public) {
    Write-Host "Could not discover a public URL within $WaitSeconds seconds. Cloudflared is running; check the log at $log to find the URL."
    Write-Host "You can also run 'cloudflared tunnel list' or inspect the process output."
    Exit 0
}

Write-Host "Discovered public URL: $public"

# Write .env for convenience
$envpath = Join-Path $working '.env'
"PUBLIC_BASE_URL=$public" | Out-File -FilePath $envpath -Encoding UTF8
Write-Host "Wrote $envpath"

# Start the bridge (uvicorn)
Write-Host "Starting uvicorn bridge (background) with PUBLIC_BASE_URL=$public"
$startInfo = @('-m','uvicorn','echo_bridge.main:app','--host','0.0.0.0','--port','3333')
Start-Process -FilePath python -ArgumentList $startInfo -WorkingDirectory $working -NoNewWindow -PassThru | Out-Null

Write-Host "Bridge started. Verify at: $public/openapi.json and $public/chatgpt_tool_manifest.json"
Write-Host "Local endpoints: http://127.0.0.1:3333/openapi.json and /chatgpt_tool_manifest.json"
