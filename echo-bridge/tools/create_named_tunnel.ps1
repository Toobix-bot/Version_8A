<#
.SYNOPSIS
  Create and run a named Cloudflare Tunnel (cloudflared) and write PUBLIC_BASE_URL to a small .env file.

USAGE
  - Requires cloudflared to be installed and authenticated (run `cloudflared login` beforehand).
  - Run from repository root: `powershell -ExecutionPolicy Bypass -File .\echo-bridge\tools\create_named_tunnel.ps1 -Name my-echo-tunnel -Port 3333`

#>

param(
    [Parameter(Mandatory=$false)]
    [string]$Name = "echo-bridge-tunnel",

    [Parameter(Mandatory=$false)]
    [int]$Port = 3333,

    [Parameter(Mandatory=$false)]
    [string]$Hostname = "",

    [switch]$RunInBackground
)

function Write-EnvFile($path, $url) {
    $content = "PUBLIC_BASE_URL=$url`n"
    Set-Content -Path $path -Value $content -Encoding UTF8
}

try {
    # Ensure cloudflared exists on PATH
    $cf = Get-Command cloudflared -ErrorAction Stop
} catch {
    Write-Error "cloudflared not found. Install from https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/ and authenticate with 'cloudflared login'"
    exit 1
}

$working = Join-Path (Get-Location) 'echo-bridge'
Push-Location $working
try {
    if ($Hostname -ne "") {
        # Create a tunnel and route a hostname (requires Cloudflare account & DNS setup)
        Write-Host "Creating named tunnel '$Name' and routing hostname $Hostname (will attempt to run cloudflared tunnel route dns)"
        & cloudflared tunnel create $Name | Out-Null
        & cloudflared tunnel route dns $Name $Hostname
        $public = "https://$Hostname"
        Write-Host "Configured hostname: $public"
    } else {
        # Run a quick tunnel that exposes local port via a random trycloudflare URL
        Write-Host "Starting tunnel for local port $Port (ephemeral public URL via trycloudflare)"
        if ($RunInBackground) {
            Start-Process -FilePath cloudflared -ArgumentList "tunnel","--url","http://127.0.0.1:$Port","run","--name",$Name -NoNewWindow -PassThru | Out-Null
            Start-Sleep -Seconds 1
            # Try to discover the trycloudflare url via 'cloudflared tunnel info'
            $info = & cloudflared tunnel info $Name 2>$null
            $public = "(ephemeral trycloudflare URL — check cloudflared output)"
            Write-Host "Started cloudflared in background. Run 'cloudflared tunnel list' or check the process output to get the public URL."
        } else {
            Write-Host "Starting cloudflared in foreground (Ctrl+C to stop). The public URL will be printed in the cloudflared output."
            & cloudflared tunnel --url "http://127.0.0.1:$Port" run --name $Name
            Pop-Location
            exit 0
        }
    }

    # If we created a hostname-based mapping, write the `.env` file for convenience
    if ($public -and $public -ne "") {
        $envpath = Join-Path $working '.env'
        Write-EnvFile -path $envpath -url $public
        Write-Host "Wrote $envpath with PUBLIC_BASE_URL=$public"
    } else {
        Write-Host "No stable public URL was written. If you used a hostname route, re-run with -Hostname set or retrieve the trycloudflare URL from cloudflared output."
    }
} finally {
    Pop-Location
}

Write-Host "Done. To use the created PUBLIC_BASE_URL, set it in your environment and restart the bridge, e.g. in PowerShell:`n`$env:PUBLIC_BASE_URL='$public'; Start-Process -NoNewWindow -FilePath python -ArgumentList '-m','uvicorn','echo_bridge.main:app','--host','0.0.0.0','--port','3333' -WorkingDirectory 'echo-bridge' -PassThru"
