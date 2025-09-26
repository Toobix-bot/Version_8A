# One-shot helper: stop duplicate processes, start uvicorn & ngrok, patch manifest/openapi, run probes

# 1) Stop any python / ngrok processes
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
taskkill /F /IM ngrok.exe 2>$null
Start-Sleep -Seconds 1

# 2) Start uvicorn (background) using project venv (ensure WorkingDirectory)
$python = 'C:\GPT\Version_8\echo-bridge\.venv\Scripts\python.exe'
$cwd = 'C:\GPT\Version_8\echo-bridge'
Write-Output "Starting uvicorn via $python (cwd=$cwd)"
Start-Process -FilePath $python -WorkingDirectory $cwd -ArgumentList '-m','uvicorn','echo_bridge.main:app','--host','0.0.0.0','--port','3333','--proxy-headers' -WindowStyle Hidden -RedirectStandardOutput 'C:\GPT\Version_8\echo-bridge\uvicorn.log' -RedirectStandardError 'C:\GPT\Version_8\echo-bridge\uvicorn.err'
Start-Sleep -Seconds 2

# 3) Start ngrok
$ngrok = 'C:\Users\micha\AppData\Local\Microsoft\WindowsApps\ngrok.exe'
Write-Output "Starting ngrok ($ngrok)"
Start-Process -FilePath $ngrok -ArgumentList 'http','127.0.0.1:3333','--host-header=rewrite' -WindowStyle Hidden
Start-Sleep -Seconds 2

# 4) Query ngrok API for public URL
try {
  $api = Invoke-RestMethod -Uri 'http://127.0.0.1:4040/api/tunnels' -ErrorAction Stop
  $pub = $api.tunnels | Where-Object { $_.proto -eq 'https' } | Select-Object -First 1 -ExpandProperty public_url
  Write-Output "PUB=$pub"
} catch {
  Write-Output "NGROK_API_ERR: $($_.Exception.Message)"
  exit 2
}

# 5) Patch manifest + openapi (in echo-bridge folder)
Set-Location -Path $cwd
$manifestPath = 'public\chatgpt_tool_manifest.json'
$openapiPath = 'public\openapi.json'

if (Test-Path $manifestPath) {
  $manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
  $manifest.api.url = "$pub/public/openapi.json"
  $manifest | ConvertTo-Json -Depth 32 | Set-Content -Encoding UTF8 $manifestPath
  Write-Output "Patched manifest.api.url -> $($manifest.api.url)"
} else {
  Write-Output "Manifest not found: $manifestPath"
}

if (Test-Path $openapiPath) {
  $openapi = Get-Content $openapiPath -Raw | ConvertFrom-Json
  if (-not $openapi.servers) { $openapi | Add-Member servers @() }
  if ($openapi.servers.Count -eq 0) { $openapi.servers += @{ url = "$pub" } } else { $openapi.servers[0].url = "$pub" }
  $openapi | ConvertTo-Json -Depth 32 | Set-Content -Encoding UTF8 $openapiPath
  Write-Output "Patched openapi.servers[0].url -> $($openapi.servers[0].url)"
} else {
  Write-Output "OpenAPI not found: $openapiPath"
}

# 6) Reachability checks
Write-Output "-- Reachability checks --"
try { Invoke-WebRequest -UseBasicParsing "$pub/public/chatgpt_tool_manifest.json" -TimeoutSec 8 | Select-Object StatusCode,@{N='CT';E={$_.Headers['Content-Type']}} | ForEach-Object { Write-Output ("MANIFEST: " + $_.StatusCode + " " + ($_.CT)) } } catch { Write-Output "MANIFEST: ERR $($_.Exception.Message)" }
try { Invoke-WebRequest -UseBasicParsing "$pub/public/openapi.json" -TimeoutSec 8 | Select-Object StatusCode,@{N='CT';E={$_.Headers['Content-Type']}} | ForEach-Object { Write-Output ("OPENAPI : " + $_.StatusCode + " " + ($_.CT)) } } catch { Write-Output "OPENAPI : ERR $($_.Exception.Message)" }

# 7) Quick smoke
Write-Output "-- Smoke: health/generate --"
try { $h = Invoke-WebRequest -UseBasicParsing "$pub/healthz" -TimeoutSec 6; Write-Output ("HEALTH : " + $h.StatusCode) } catch { Write-Output ("HEALTH : ERR " + $_.Exception.Message) }

try {
  $g = Invoke-WebRequest -UseBasicParsing "$pub/generate" -Method POST -ContentType 'application/json' -Body (@{prompt='Kurze Szene im Stil von ECHO.'} | ConvertTo-Json) -TimeoutSec 8 -ErrorAction Stop
  Write-Output ("GENERATE STATUS: " + $g.StatusCode)
  $c = $g.Content
  if ($c.Length -gt 400) { $c = $c.Substring(0,400) }
  Write-Output "GENERATE BODY (preview):`n$c"
} catch {
  Write-Output "GENERATE: ERR $($_.Exception.Message)"
}

Write-Output "-- DONE --"
