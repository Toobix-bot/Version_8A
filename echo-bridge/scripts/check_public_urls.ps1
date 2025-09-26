$urls = @(
  'http://127.0.0.1:3333/public/chatgpt_tool_manifest.json',
  'http://127.0.0.1:3333/public/openapi.json',
  'https://multiplicative-unapprehendably-marisha.ngrok-free.dev/public/chatgpt_tool_manifest.json',
  'https://multiplicative-unapprehendably-marisha.ngrok-free.dev/public/openapi.json'
)

foreach ($u in $urls) {
  try {
    $r = Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 8
    Write-Host "URL: $u`nStatus: $($r.StatusCode)`n--- Body (truncated) ---"
    $c = $r.Content
    if ($c.Length -gt 400) { $c = $c.Substring(0,400) }
    Write-Host $c
    Write-Host "---------------------------`n"
  } catch {
    Write-Host "URL: $u`nERROR: $($_.Exception.Message)`n---------------------------`n"
  }
}
