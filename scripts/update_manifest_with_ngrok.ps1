<#
Usage: .\scripts\update_manifest_with_ngrok.ps1
This script will:
 - check if ngrok is available in PATH
 - fetch the public_url from ngrok's local API
 - update echo-bridge/public/chatgpt_tool_manifest.json to point api.url -> <public_url>/mcp/openapi.json

You can also pass a public URL as the first argument to skip ngrok detection.
#>

param(
    [string]$PublicUrl
)

$manifestPath = Join-Path (Join-Path (Get-Location) 'echo-bridge') 'public\chatgpt_tool_manifest.json'
if (-not (Test-Path $manifestPath)) {
    Write-Host "Manifest not found at $manifestPath"
    exit 1
}

if (-not $PublicUrl) {
    # try to find ngrok
    $ng = Get-Command ngrok -ErrorAction SilentlyContinue
    if (-not $ng) {
        Write-Host 'ngrok not found in PATH. Either pass the public URL as argument or install ngrok and run it.'
        Write-Host 'Example: .\scripts\update_manifest_with_ngrok.ps1 https://abcd-1234.ngrok-free.app'
        exit 2
    }
    Write-Host "Found ngrok at $($ng.Path). Attempting to fetch public URL from local API..."
    try {
        Start-Sleep -Seconds 1
        $raw = (Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:4040/api/tunnels' -ErrorAction Stop).Content
        $json = $raw | ConvertFrom-Json
        if ($json.tunnels.Count -gt 0) {
            $PublicUrl = $json.tunnels[0].public_url
            Write-Host "ngrok public url: $PublicUrl"
        } else {
            Write-Host 'ngrok running but no tunnels found. Start ngrok with: ngrok http 3333' ; exit 3
        }
    } catch {
        Write-Host 'Error when querying ngrok API:' $_.Exception.Message
        exit 4
    }
}

# Normalize and update manifest
$PublicUrl = $PublicUrl.TrimEnd('/')
Write-Host "Updating manifest $manifestPath with public host $PublicUrl"

Copy-Item -Path $manifestPath -Destination ($manifestPath + '.bak') -Force

$txt = Get-Content $manifestPath -Raw -ErrorAction Stop
$m = $txt | ConvertFrom-Json
$m.api.url = ($PublicUrl + '/mcp/openapi.json')
$m.auth.type = 'none'

[System.Text.Encoding]::UTF8.GetString([System.Text.Encoding]::UTF8.GetBytes(($m | ConvertTo-Json -Depth 10))) | Out-File -Encoding utf8 $manifestPath

Write-Host "Manifest updated. New api.url: $($m.api.url)"
Write-Host "Backup saved at $manifestPath.bak"
exit 0
