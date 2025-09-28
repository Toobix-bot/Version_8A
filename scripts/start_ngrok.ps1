$ErrorActionPreference = 'Stop'
Write-Host 'Starting ngrok http 127.0.0.1:3333 with host-header rewrite'
Start-Process -FilePath 'ngrok' -ArgumentList 'http','http://127.0.0.1:3333','--host-header=rewrite' -NoNewWindow | Out-Null
Start-Sleep -Seconds 2
Write-Host 'Ngrok process started.'
