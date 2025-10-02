param(
    [switch]$UseNgrok = $true
)

$Root = "C:\GPT\Version_8"
$BridgeDir = Join-Path $Root "echo-bridge"

Write-Host "[1/5] Starting MCP Backend..." -ForegroundColor Cyan
cd $BridgeDir
Start-Process -WindowStyle Minimized python -ArgumentList "run_mcp_http.py --host 127.0.0.1 --port 3339"
Start-Sleep 2

Write-Host "[2/5] Starting Bridge..." -ForegroundColor Cyan
$env:MCP_ALLOW_FALLBACK_GET = "1"
Start-Process -WindowStyle Minimized python -ArgumentList "-m uvicorn echo_bridge.main:app --host 127.0.0.1 --port 3333 --http h11 --workers 1"
Start-Sleep 3

if($UseNgrok) {
    Write-Host "[3/5] Starting ngrok..." -ForegroundColor Cyan
    Start-Process ngrok -ArgumentList "http 3333"
    Start-Sleep 4
    
    Write-Host "[4/5] Detecting public URL..." -ForegroundColor Cyan
    try {
        $api = Invoke-RestMethod http://127.0.0.1:4040/api/tunnels
        $url = $api.tunnels[0].public_url
        Write-Host "Public URL: $url" -ForegroundColor Green
        
        Write-Host "[5/5] Patching domain..." -ForegroundColor Cyan
        python scripts/update_public_domain.py $url
        
        Start-Process "$url/panel"
    } catch {
        Write-Host "Could not auto-detect ngrok URL" -ForegroundColor Yellow
        Start-Process "http://127.0.0.1:3333/panel"
    }
} else {
    Start-Process "http://127.0.0.1:3333/panel"
}

Write-Host "`nDONE! Panel opening..." -ForegroundColor Green
Write-Host "Local:  http://127.0.0.1:3333/panel"
Write-Host "MCP:    http://127.0.0.1:3333/mcp"
