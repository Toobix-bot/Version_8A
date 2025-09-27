# create_gist.ps1
# Creates a public GitHub Gist from the local public/openapi.json and public/chatgpt_tool_manifest.json
# Usage: Run this file in PowerShell from the echo-bridge directory.

param()

Write-Host "This script will create a public Gist containing openapi.json and chatgpt_tool_manifest.json from ./public"

# Securely read token
$secure = Read-Host -AsSecureString "Enter your GitHub Personal Access Token (scope: gist)"
$token = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
)

$openapiPath = Join-Path (Get-Location) 'public\openapi.json'
$manifestPath = Join-Path (Get-Location) 'public\chatgpt_tool_manifest.json'

if (-not (Test-Path $openapiPath) -or -not (Test-Path $manifestPath)) {
    Write-Error "Could not find the required files. Check that these exist:`n$openapiPath`n$manifestPath"
    exit 1
}

$openapi = Get-Content -Path $openapiPath -Raw
$manifest = Get-Content -Path $manifestPath -Raw

$body = @{
    description = "ECHO Bridge: openapi + manifest (created via local PowerShell script)"
    public = $true
    files = @{
        "openapi.json" = @{ content = $openapi }
        "chatgpt_tool_manifest.json" = @{ content = $manifest }
    }
} | ConvertTo-Json -Depth 10

try {
    $resp = Invoke-RestMethod -Uri "https://api.github.com/gists" -Method Post -Headers {
        @{ Authorization = "token $token"; "User-Agent" = "PowerShell" }
    } -Body $body -ContentType "application/json"
} catch {
    Write-Error "Gist creation failed: $($_.Exception.Message)"
    exit 1
}

$openapi_raw = $resp.files.'openapi.json'.raw_url
$manifest_raw = $resp.files.'chatgpt_tool_manifest.json'.raw_url

Write-Host "Gist created successfully!"
Write-Host "openapi raw URL: $openapi_raw"
Write-Host "manifest raw URL: $manifest_raw"

# Test fetch the manifest raw URL
try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri $manifest_raw -Method GET -TimeoutSec 10
    Write-Host "\nManifest raw fetch: Status $($r.StatusCode); Content-Type: $($r.Headers['Content-Type'])"
} catch {
    Write-Warning "Could not fetch raw manifest URL: $($_.Exception.Message)"
}

# Cleanup
Remove-Variable token -ErrorAction SilentlyContinue
Remove-Variable secure -ErrorAction SilentlyContinue

Write-Host "Finished."