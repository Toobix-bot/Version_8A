$ErrorActionPreference = 'Stop'
try {
    $body = '{"prompt":"smoke no-key"}'
    $r = Invoke-WebRequest -Uri 'https://tools-ready-surface-sur.trycloudflare.com/bridge/link_echo_generate/echo_generate' -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 60
    Write-Host 'OK no-key:'
    Write-Host $r.Content
} catch {
    Write-Host 'ERROR no-key:' $_.Exception.Message
}

try {
    $body2 = '{"prompt":"smoke with-key"}'
    $r2 = Invoke-WebRequest -Uri 'https://tools-ready-surface-sur.trycloudflare.com/bridge/link_echo_generate/echo_generate' -Method Post -Body $body2 -ContentType 'application/json' -TimeoutSec 60 -Headers @{ 'X-API-Key' = 'SECRET' }
    Write-Host 'OK with-key:'
    Write-Host $r2.Content
} catch {
    Write-Host 'ERROR with-key:' $_.Exception.Message
}
