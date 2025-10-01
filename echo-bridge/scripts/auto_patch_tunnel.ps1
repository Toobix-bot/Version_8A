Param(
  [string]$LogPath = "..\cloudflared.log",
  [int]$Retry = 20,
  [int]$DelayMs = 500
)
# Attempts to detect a trycloudflare.com URL in the running cloudflared log or stdout copy.
$pattern = 'https://[a-z0-9-]+\.trycloudflare\.com'
$found = $null
for ($i=0; $i -lt $Retry -and -not $found; $i++) {
  if (Test-Path $LogPath) {
    $text = Get-Content $LogPath -Raw -ErrorAction SilentlyContinue
    if ($text) {
      $m = [regex]::Matches($text, $pattern) | Select-Object -Last 1
      if ($m) { $found = $m.Value }
    }
  }
  if (-not $found) { Start-Sleep -Milliseconds $DelayMs }
}
if (-not $found) {
  Write-Host 'Tunnel URL not found.' -ForegroundColor Yellow
  exit 1
}
Write-Host "Detected tunnel: $found" -ForegroundColor Cyan
python scripts/update_public_domain.py $found
