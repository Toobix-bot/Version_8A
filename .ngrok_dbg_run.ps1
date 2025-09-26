# ngrok debug helper
Start-Sleep -Seconds 1
try {
  $api = Invoke-RestMethod -Uri 'http://127.0.0.1:4040/api/tunnels' -ErrorAction Stop
  $pub = $null
  foreach ($t in $api.tunnels) { if ($t.proto -eq 'https') { $pub = $t.public_url; break } }
  if (-not $pub) { Write-Output 'No HTTPS tunnel found'; exit 2 }
  Write-Output "PUB=$pub"
  # Probe public openapi.json
  try {
    $r = Invoke-WebRequest -Uri ("$pub/public/openapi.json") -UseBasicParsing -TimeoutSec 8 -ErrorAction Stop
    Write-Output "PROBE_STATUS: $($r.StatusCode)"
    Write-Output "PROBE_CT: $($r.Headers['Content-Type'])"
    $body = $r.Content
    if ($body.Length -gt 400) { $body = $body.Substring(0,400) }
    Write-Output "PROBE_BODY_PREVIEW:"; Write-Output $body
  } catch {
    Write-Output "PROBE_ERROR: $($_.Exception.Message)"
  }
  # Query ngrok requests (if available)
  try {
    $reqs = Invoke-RestMethod -Uri 'http://127.0.0.1:4040/api/requests/http?limit=20' -ErrorAction Stop
    if ($reqs.requests) {
      Write-Output "NGROK REQUESTS (last up to 20):"
      foreach ($it in $reqs.requests) {
        $m = $it.request.method; $u = $it.request.uri; $s = $it.response.status
        Write-Output "  $m $u -> $s"
        if ($it.response.body) { $b = $it.response.body; if ($b.Length -gt 200) { $b = $b.Substring(0,200) }; Write-Output "    BODY_PREVIEW: $b" }
      }
    } else {
      Write-Output "No requests data in ngrok API response"
    }
  } catch {
    Write-Output "NGROK REQUESTS API ERR: $($_.Exception.Message)"
  }
} catch {
  Write-Output "NGROK API ERR: $($_.Exception.Message)"
  exit 2
}
