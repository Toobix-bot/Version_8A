$lines = Get-Content ..\logs\cloudflared.log -ErrorAction SilentlyContinue
$matches = $lines | Select-String -Pattern 'https://.*trycloudflare.com' -AllMatches
if ($matches) { $m = $matches[-1].Matches[0].Value; Write-Output $m } else { Write-Output '' }