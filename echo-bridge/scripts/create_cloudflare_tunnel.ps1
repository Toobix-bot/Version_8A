<#
Interactive helper to create a persistent Cloudflare Tunnel (named tunnel)
and optionally install it as a Windows service. Requires a Cloudflare account
and a zone where you control DNS.

Usage (run in PowerShell as Admin):
  .\scripts\create_cloudflare_tunnel.ps1 -TunnelName my-echo-bridge -Hostname "mcp.example.com"

What it does (interactive):
  - Ensures cloudflared exists (downloads if missing when -DownloadIfMissing is passed)
  - Runs `cloudflared tunnel login` (opens browser to authorize)
  - Runs `cloudflared tunnel create <name>` to create the tunnel and writes the credential file
  - Attempts `cloudflared tunnel route dns` if a hostname is provided (may fail without proper account permissions)
  - Writes a sample config file under ./cloudflared/<tunnel>.yml and prints the recommended service install command

Notes:
  - You must own a domain in Cloudflare (zone) to map a stable hostname like mcp.example.com.
  - If automatic DNS routing fails, create a CNAME in Cloudflare that points your hostname to the target shown by `cloudflared tunnel create`.
  - Running this script does not change your repository files; it only helps you create and run a persistent tunnel locally.
#>

param(
    [string]$TunnelName = "echo-bridge",
    [string]$Hostname = "",
    [switch]$DownloadIfMissing = $false
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-Cloudflared {
    # Approved verb "Get" used instead of custom verb.
    $candidate = Join-Path $PSScriptRoot '..\\cloudflared.exe'
    $resolved = Resolve-Path -Path $candidate -ErrorAction SilentlyContinue
    if ($resolved) {
        $path = $resolved.Path
        if (Test-Path $path) {
            Write-Host "cloudflared found at $path"
            return $path
        }
    }
    if (-not $DownloadIfMissing) {
        throw 'cloudflared.exe not found in the repo root. Re-run with -DownloadIfMissing to allow download.'
    }
    Write-Host 'Downloading cloudflared (latest)...'
    $out = Join-Path $PSScriptRoot '..\\cloudflared.exe'
    Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile $out
    Write-Host "Downloaded cloudflared to $out"
    $resolvedOut = Resolve-Path -Path $out -ErrorAction SilentlyContinue
    return $resolvedOut.Path
}

$cloudflared = Get-Cloudflared

Write-Host "Step 1/4 — Log in to Cloudflare and authorize this machine (a browser window will open)."
& $cloudflared tunnel login

Write-Host "Step 2/4 — Creating the named tunnel: $TunnelName"
& $cloudflared tunnel create $TunnelName

if ($Hostname -ne '') {
    Write-Host "Step 3/4 — Attempting to create DNS route for $Hostname"
    try {
        & $cloudflared tunnel route dns $TunnelName $Hostname
        Write-Host "DNS route created for $Hostname"
    } catch {
        Write-Warning "Automatic DNS route failed: $($_.Exception.Message)"
        Write-Host "If automatic DNS routing failed, create a CNAME record in your Cloudflare zone:"
        Write-Host "  Name: $Hostname"
        Write-Host "  Type: CNAME"
        Write-Host "  Content: <the target shown by 'cloudflared tunnel create' output, e.g., <tunnel-id>.<region>.cfargotunnel.com>"
    }
}

Write-Host "Step 4/4 — Writing an example config and showing how to run the tunnel as a service."
$cfgDir = Join-Path $PSScriptRoot '..\\cloudflared'
New-Item -ItemType Directory -Path $cfgDir -Force | Out-Null
$cfgPath = Join-Path $cfgDir "$TunnelName.yml"

$cfgLines = @()
$cfgLines += "tunnel: $TunnelName"
$cfgLines += "credentials-file: $HOME\\.cloudflared\\$TunnelName.json"
if ($Hostname -ne '') {
    $cfgLines += "ingress:" 
    $cfgLines += "  - hostname: $Hostname"
    $cfgLines += "    service: http://127.0.0.1:3333"
    $cfgLines += "  - service: http_status:404"
}
$cfgLines | Out-File -FilePath $cfgPath -Encoding utf8 -Force
Write-Host "Wrote config to $cfgPath"

Write-Host "To install the tunnel as a Windows service (requires Admin):"
Write-Host "  & $cloudflared service install --config $cfgPath"
Write-Host "If that fails, you can run the tunnel manually with:"
Write-Host "  & $cloudflared tunnel run $TunnelName --config $cfgPath"

Write-Host 'Done. If you created DNS for the hostname, allow a few minutes for propagation.'
