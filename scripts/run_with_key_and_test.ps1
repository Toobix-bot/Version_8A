$ErrorActionPreference = 'Stop'
Write-Host 'Stopping uvicorn and ngrok if running...'
Get-Process -Name uvicorn -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
Get-Process -Name ngrok -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1

Write-Host 'Starting bridge with API_KEY via batch wrapper...'
Start-Process -FilePath 'C:\GPT\Version_8\scripts\start_bridge_with_key.bat' -WindowStyle Hidden
Start-Sleep -Seconds 3

if (-not (Get-Process -Name ngrok -ErrorAction SilentlyContinue)) {
    Write-Host 'Starting ngrok...'
    Start-Process -FilePath 'ngrok' -ArgumentList 'http','http://127.0.0.1:3333','--host-header=rewrite' -WindowStyle Hidden
    Start-Sleep -Seconds 3
} else {
    Write-Host 'ngrok already running.'
}

# Print ngrok public URL if inspector available
try {
    $t = Invoke-RestMethod 'http://127.0.0.1:4040/api/tunnels' -ErrorAction Stop
    $t.tunnels | ForEach-Object { Write-Host "ngrok public_url: $($_.public_url)" }
} catch {
    Write-Host 'Could not read ngrok inspector:' $_.Exception.Message
}

Write-Host 'Running smoke checks (check_pages.ps1)...'
& 'C:\GPT\Version_8\check_pages.ps1'
