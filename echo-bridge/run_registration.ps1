# run_registration.ps1
# One-shot script to create a public Gist from ./public, validate the manifest raw URL,
# detect ngrok public URL, and run a smoke POST to the bridge endpoint.
# Run this in a new PowerShell window so you can enter the GitHub token interactively.

Write-Host "Run Registration: Create Gist -> Validate -> Smoke POST"

# Read GitHub token securely
$secure = Read-Host -AsSecureString "Enter your GitHub Personal Access Token (scope: gist)"
$token = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
)

# Optional: bridge API key for X-API-Key header
$apiKeyInput = Read-Host "If your bridge requires X-API-Key enter it (press Enter to use 'SECRET')"
if ([string]::IsNullOrWhiteSpace($apiKeyInput)) { $bridgeApiKey = 'SECRET' } else { $bridgeApiKey = $apiKeyInput }

# Paths
$base = Get-Location
$openapiPath = Join-Path $base 'public\openapi.json'
$manifestPath = Join-Path $base 'public\chatgpt_tool_manifest.json'

if (-not (Test-Path $openapiPath) -or -not (Test-Path $manifestPath)) {
    Write-Error "Required files not found. Ensure these exist:`n$openapiPath`n$manifestPath"
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
}
$bodyJson = $body | ConvertTo-Json -Depth 10

Write-Host "Creating Gist..."
try {
    $resp = Invoke-RestMethod -Uri "https://api.github.com/gists" -Method Post -Headers @{
        Authorization = "token $token"
        "User-Agent" = "PowerShell"
    } -Body $bodyJson -ContentType "application/json"
} catch {
    Write-Error "Gist creation failed: $($_.Exception.Message)"
    Remove-Variable token -ErrorAction SilentlyContinue
    Remove-Variable secure -ErrorAction SilentlyContinue
    exit 1
}

$openapi_raw  = $resp.files.'openapi.json'.raw_url
$manifest_raw = $resp.files.'chatgpt_tool_manifest.json'.raw_url

Write-Host "Gist created successfully!"
Write-Host "openapi raw URL: $openapi_raw"
Write-Host "manifest raw URL: $manifest_raw`
"

# Validate raw manifest URL
Write-Host "Validating manifest raw URL..."
try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri $manifest_raw -Method GET -TimeoutSec 15
    Write-Host "Manifest GET: Status $($r.StatusCode); Content-Type: $($r.Headers['Content-Type'])"
    Write-Host "Body snippet:`n$($r.Content.Substring(0,[Math]::Min(800,$r.Content.Length)))`n"
} catch {
    Write-Warning "Could not fetch raw manifest URL: $($_.Exception.Message)"
}

# Try to detect ngrok public URL from inspector
$pub = $null
try {
    $t = Invoke-RestMethod -Uri 'http://127.0.0.1:4040/api/tunnels' -UseBasicParsing -ErrorAction Stop
    if ($t -and $t.tunnels) {
        $https = $t.tunnels | Where-Object { $_.proto -eq 'https' } | Select-Object -First 1
        if ($https) { $pub = $https.public_url }
    }
} catch {
    Write-Warning "Could not read ngrok inspector: $($_.Exception.Message)"
}

if (-not $pub) {
    $pub = Read-Host "Enter your public HTTPS tunnel URL (e.g. https://abcd.ngrok-free.dev)"
}
Write-Host "Using public URL: $pub`
"

# Check the four endpoints
function showEndpoint($path) {
    $u = "$pub$path"
    try {
        $resp = Invoke-WebRequest -UseBasicParsing -Uri $u -Method GET -TimeoutSec 10
        Write-Host "GET $path -> Status: $($resp.StatusCode); CT: $($resp.Headers['Content-Type'])"
        $snip = $resp.Content.Substring(0,[Math]::Min(800,$resp.Content.Length))
        Write-Host "Body snippet:`n$snip`n"
    } catch {
        Write-Warning "GET $path failed: $($_.Exception.Message)`n"
    }
}

showEndpoint('/openapi.json')
showEndpoint('/public/openapi.json')
showEndpoint('/chatgpt_tool_manifest.json')
showEndpoint('/public/chatgpt_tool_manifest.json')

# Smoketest POST to bridge
Write-Host "Performing smoke POST to /bridge/link_echo_generate/echo_generate ..."
$hdr = @{ 'Content-Type' = 'application/json'; 'X-API-Key' = $bridgeApiKey }
$bodyPost = @{ prompt = 'smoke test from local' } | ConvertTo-Json
try {
    $p = Invoke-WebRequest -UseBasicParsing -Uri "$pub/bridge/link_echo_generate/echo_generate" -Method POST -Headers $hdr -Body $bodyPost -TimeoutSec 15
    Write-Host "POST Status: $($p.StatusCode); CT: $($p.Headers['Content-Type'])"
    Write-Host "Body snippet:`n$($p.Content.Substring(0,[Math]::Min(800,$p.Content.Length)))`n"
} catch {
    Write-Warning "POST failed: $($_.Exception.Message)"
}

# Cleanup sensitive variables
Remove-Variable token -ErrorAction SilentlyContinue
Remove-Variable secure -ErrorAction SilentlyContinue
Remove-Variable bridgeApiKey -ErrorAction SilentlyContinue

Write-Host "Done. Paste the manifest raw URL here in the chat if you want me to validate anything further or register the manifest."