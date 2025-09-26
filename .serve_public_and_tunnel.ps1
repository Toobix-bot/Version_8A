# Serve public/ via a simple static http.server on port 3338, start ngrok to 3338, patch manifest/openapi and probe
$cwd = 'C:\GPT\Version_8\echo-bridge'
$pubdir = Join-Path $cwd 'public'
$py = 'C:\GPT\Version_8\echo-bridge\.venv\Scripts\python.exe'
$ngrok = 'C:\Users\micha\AppData\Local\Microsoft\WindowsApps\ngrok.exe'

# Stop existing ngrok
try { taskkill /F /IM ngrok.exe 2>$null } catch {}
Start-Sleep -Milliseconds 300

# Start static server in background
Write-Output "Starting static server (python -m http.server 3338) in $pubdir"
Start-Process -FilePath $py -WorkingDirectory $pubdir -ArgumentList '-m','http.server','3338' -WindowStyle Hidden
Start-Sleep -Seconds 1

# Start ngrok to forward to 3338
Write-Output "Starting ngrok -> 127.0.0.1:3338"
Start-Process -FilePath $ngrok -ArgumentList 'http','127.0.0.1:3338','--host-header=rewrite' -WindowStyle Hidden
Start-Sleep -Seconds 2

# Query ngrok API for public URL
try {
  $api = Invoke-RestMethod -Uri 'http://127.0.0.1:4040/api/tunnels' -ErrorAction Stop
  $pub = $api.tunnels | Where-Object { $_.proto -eq 'https' } | Select-Object -First 1 -ExpandProperty public_url
  Write-Output "PUB=$pub"
} catch {
  Write-Output "NGROK_API_ERR: $($_.Exception.Message)"
  exit 2
}

# Patch manifest/openapi to point to the new $pub
Set-Location -Path $cwd
$manifestPath = 'public\chatgpt_tool_manifest.json'
$openapiPath = 'public\openapi.json'
if (Test-Path $manifestPath) {
  $manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
  $manifest.api.url = "$pub/public/openapi.json"
  $manifest | ConvertTo-Json -Depth 32 | Set-Content -Encoding UTF8 $manifestPath
  Write-Output "Patched manifest -> $($manifest.api.url)"
}
if (Test-Path $openapiPath) {
  $openapi = Get-Content $openapiPath -Raw | ConvertFrom-Json
  if (-not $openapi.servers) { $openapi | Add-Member servers @() }
  if ($openapi.servers.Count -eq 0) { $openapi.servers += @{ url = "$pub" } } else { $openapi.servers[0].url = "$pub" }
  $openapi | ConvertTo-Json -Depth 32 | Set-Content -Encoding UTF8 $openapiPath
  Write-Output "Patched openapi.servers[0].url -> $($openapi.servers[0].url)"
}

# Probe the public endpoints
Write-Output "-- Probe public endpoints --"
try { Invoke-WebRequest -UseBasicParsing "$pub/public/chatgpt_tool_manifest.json" -TimeoutSec 8 | Select-Object StatusCode,@{N='CT';E={$_.Headers['Content-Type']}} | ForEach-Object { Write-Output ("MANIFEST: " + $_.StatusCode + " " + $_.CT) } } catch { Write-Output "MANIFEST: ERR $($_.Exception.Message)" }
try { Invoke-WebRequest -UseBasicParsing "$pub/public/openapi.json" -TimeoutSec 8 | Select-Object StatusCode,@{N='CT';E={$_.Headers['Content-Type']}} | ForEach-Object { Write-Output ("OPENAPI : " + $_.StatusCode + " " + $_.CT) } } catch { Write-Output "OPENAPI : ERR $($_.Exception.Message)" }

Write-Output "-- Done --"
