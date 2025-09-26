try {
  $api = Invoke-RestMethod -Uri 'http://127.0.0.1:4040/api/tunnels' -ErrorAction Stop
  foreach ($t in $api.tunnels) {
    Write-Output ("public_url: $($t.public_url) -> proto: $($t.proto) -> addr: $($t.config.addr)")
  }
} catch {
  Write-Output "ngrok API not reachable: $($_.Exception.Message)"
}
