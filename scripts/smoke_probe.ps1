param(
    [string]$LocalBase = "http://127.0.0.1:3333",
    [string]$PublicBase = "",
    [int]$TimeoutSec = 5
)
$ErrorActionPreference = 'Continue'
function Probe($method, $url, $headers, $body) {
    try {
        if ($method -eq 'GET') {
            $r = Invoke-WebRequest -Uri $url -Method GET -Headers $headers -UseBasicParsing -TimeoutSec $TimeoutSec
        } else {
            $r = Invoke-WebRequest -Uri $url -Method POST -Headers $headers -Body $body -UseBasicParsing -TimeoutSec $TimeoutSec
        }
        Write-Host "URL: $url METHOD: $method STATUS: $($r.StatusCode)"
        if ($r.Headers['Content-Type']) { Write-Host "  Content-Type: $($r.Headers['Content-Type'])" }
        if ($r.Content) { $snippet = $r.Content.Substring(0,[Math]::Min(400,$r.Content.Length)); Write-Host '  BODY SNIPPET:'; Write-Host $snippet }
    } catch {
        Write-Host "URL: $url METHOD: $method FAILED: $($_.Exception.Message)"
    }
}

Write-Host '--- Probing local endpoints ---'
Probe 'GET' "$LocalBase/public/openapi.json" @{ 'Accept'='application/json' } $null
Probe 'GET' "$LocalBase/mcp" @{ 'Accept'='text/event-stream' } $null
Probe 'POST' "$LocalBase/bridge/link_echo_generate/echo_generate" @{ 'Content-Type'='application/json' } '{"prompt":"hello","contextIds":null}'

if ($PublicBase -and $PublicBase.Length -gt 0) {
    Write-Host '--- Probing public endpoints ---'
    Probe 'GET' "$PublicBase/public/openapi.json" @{ 'Accept'='application/json' } $null
    Probe 'GET' "$PublicBase/mcp" @{ 'Accept'='text/event-stream' } $null
    Probe 'POST' "$PublicBase/bridge/link_echo_generate/echo_generate" @{ 'Content-Type'='application/json' } '{"prompt":"public","contextIds":null}'
}
