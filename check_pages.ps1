$ErrorActionPreference = 'Stop'

function Check-UrlHead { param($url) 
    Write-Host "HEAD $url"; 
    try { $r = Invoke-WebRequest -Uri $url -Method Head -UseBasicParsing -TimeoutSec 15; Write-Host $r.StatusCode $r.Headers['Content-Type'] } catch { Write-Host "HEAD ERROR:" $_.Exception.Message }
}

function Get-Snippet { param($url) 
    Write-Host "GET snippet $url";
    try { $g = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 15; $s = $g.Content; Write-Host $s.Substring(0,[Math]::Min(800,$s.Length)) } catch { Write-Host "GET ERROR:" $_.Exception.Message }
}

$manifest = 'https://toobix-bot.github.io/Version_8A/public/chatgpt_tool_manifest.json'
$openapi = 'https://toobix-bot.github.io/Version_8A/public/openapi.json'

Check-UrlHead $manifest
Check-UrlHead $openapi
Get-Snippet $openapi

Write-Host "\nRunning POST smoke tests via temp_post_test.ps1"
.\temp_post_test.ps1
