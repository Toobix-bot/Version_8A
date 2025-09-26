param(
  [string]$Local = 'http://127.0.0.1:3333/public/openapi.json',
  [string]$Public = 'https://multiplicative-unapprehendably-marisha.ngrok-free.dev/public/openapi.json'
)
function Probe($label,$url) {
  Write-Output ("== " + $label + ": " + $url + " ==")
  try {
    $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -ErrorAction Stop
    Write-Output ("Status: $($r.StatusCode)")
    Write-Output ("Content-Type: $($r.Headers['Content-Type'])")
    $c = $r.Content
    Write-Output ("Len: $($c.Length)")
    if ($c.Length -gt 600) { $c = $c.Substring(0,600) }
    Write-Output "---BODY PREVIEW---"
    Write-Output $c
  } catch {
    Write-Output ("ERROR: $($_.Exception.Message)")
  }
  Write-Output ""
}

Probe "LOCAL" $Local
Probe "PUBLIC" $Public

Write-Output "== uvicorn.err tail =="
if (Test-Path 'c:\GPT\Version_8\echo-bridge\uvicorn.err') { Get-Content -Path 'c:\GPT\Version_8\echo-bridge\uvicorn.err' -Tail 200 } else { Write-Output 'uvicorn.err not found' }

Write-Output "== bridge.log tail =="
if (Test-Path 'c:\GPT\Version_8\echo-bridge\bridge.log') { Get-Content -Path 'c:\GPT\Version_8\echo-bridge\bridge.log' -Tail 200 } else { Write-Output 'bridge.log not found' }
