try {
  $url = 'http://127.0.0.1:4040/api/requests/http?limit=20'
  $j = Invoke-RestMethod -Uri $url -ErrorAction Stop
  foreach ($r in $j.requests) {
    $method = $r.request.method
    $uri = $r.request.uri
    $status = $r.response.status
    $bodySnippet = ''
    if ($r.response.body) { $bodySnippet = $r.response.body.Substring(0,[Math]::Min(200,$r.response.body.Length)) }
    Write-Output "REQ: $method $uri -> $status"
    if ($bodySnippet) { Write-Output "  BODY_SNIPPET: $bodySnippet" }
  }
} catch {
  Write-Output "ngrok requests API error: $($_.Exception.Message)"
}
