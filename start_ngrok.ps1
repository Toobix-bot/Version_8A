# Start ngrok and print public URLs for the MCP and Bridge endpoints.
param(
  [string]$Port = '3337'
)

Write-Host "Starting ngrok for port $Port..."
Start-Process ngrok -ArgumentList "http $Port" -NoNewWindow
Start-Sleep -Seconds 2
try{
  $tunnels = (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:4040/api/tunnels -ErrorAction Stop).Content | ConvertFrom-Json
  $tunnels.tunnels | ForEach-Object { Write-Host "public url:" $_.public_url }
} catch {
  Write-Host 'Could not query local ngrok API at http://127.0.0.1:4040 yet.'
  Write-Host 'Try again in a few seconds or run:'
  Write-Host "(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:4040/api/tunnels).Content | ConvertFrom-Json | Select-Object -ExpandProperty tunnels | Select-Object -ExpandProperty public_url"
}
