param(
  [string]$Url = 'https://multiplicative-unapprehendably-marisha.ngrok-free.dev/public/openapi.json'
)
try {
  $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
  Write-Output "URL: $Url"
  Write-Output "Status: $($r.StatusCode)"
  Write-Output "Headers:" 
  $r.Headers | Format-List
  $body = $r.Content
  Write-Output "BodyLength: $($body.Length)"
  if ($body.Length -gt 800) { $body = $body.Substring(0,800) }
  Write-Output "---BODY PREVIEW---" 
  Write-Output $body
} catch {
  Write-Output "ERROR: $($_.Exception.Message)"
}
