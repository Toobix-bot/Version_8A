$ErrorActionPreference = 'Stop'
$ngrok = 'https://tools-ready-surface-sur.trycloudflare.com/bridge/link_echo_generate/echo_generate'
$body = @{ prompt = 'final debug payload'; model = 'gpt-4o-mini'; max_tokens = 5 } | ConvertTo-Json -Depth 5
$hdr = @{ 'X-API-Key' = 'SECRET' }
try {
    Write-Host "POSTing to $ngrok with key..."
    $r = Invoke-RestMethod -Uri $ngrok -Method Post -Body $body -ContentType 'application/json' -Headers $hdr -TimeoutSec 30
    Write-Host "Status: 200 OK"; Write-Host ($r | ConvertTo-Json -Depth 10)
} catch {
    Write-Host 'Exception:' $_.Exception.Message
    if ($_.Exception.Response) {
        $sr = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        $content = $sr.ReadToEnd()
        Write-Host 'Response body:'; Write-Host $content
    }
}

Write-Host '--- uvicorn.err.log (tail 80) ---'
if (Test-Path 'C:\GPT\Version_8\uvicorn.err.log') { Get-Content 'C:\GPT\Version_8\uvicorn.err.log' -Tail 80 } else { Write-Host 'uvicorn.err.log not found' }
