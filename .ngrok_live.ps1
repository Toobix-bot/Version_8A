# Start ngrok with stdout logging, probe public URL, then tail the ngrok log
$ngrokExe = 'C:\Users\micha\AppData\Local\Microsoft\WindowsApps\ngrok.exe'
$log = 'C:\GPT\Version_8\ngrok_live.log'

# Kill existing ngrok
try { taskkill /F /IM ngrok.exe 2>$null } catch {}
Start-Sleep -Milliseconds 300

# Start ngrok in background, redirect stdout to file
Start-Process -FilePath $ngrokExe -ArgumentList 'http','127.0.0.1:3333','--host-header=rewrite','--log=stdout' -WindowStyle Hidden -RedirectStandardOutput $log -RedirectStandardError $log
Write-Output "Started ngrok, log -> $log"
Start-Sleep -Seconds 2

# Query ngrok API to show public url
try {
  $api = Invoke-RestMethod -Uri 'http://127.0.0.1:4040/api/tunnels' -ErrorAction Stop
  $pub = $api.tunnels | Where-Object { $_.proto -eq 'https' } | Select-Object -First 1 -ExpandProperty public_url
  Write-Output "PUB=$pub"
} catch {
  Write-Output "Could not read ngrok API: $($_.Exception.Message)"
  exit 2
}

# Make a single probe to the public openapi.json
try {
  Write-Output "Probing $pub/public/openapi.json"
  $r = Invoke-WebRequest -Uri "$pub/public/openapi.json" -UseBasicParsing -TimeoutSec 8 -ErrorAction Stop
  Write-Output "Probe status: $($r.StatusCode)"
  Write-Output "Probe CT: $($r.Headers['Content-Type'])"
} catch {
  Write-Output "Probe error: $($_.Exception.Message)"
}

Start-Sleep -Seconds 1

# Tail the log
Write-Output "--- ngrok log tail ---"
if (Test-Path $log) { Get-Content -Path $log -Tail 200 -Raw } else { Write-Output "no log file found: $log" }
