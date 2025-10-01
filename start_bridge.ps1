Param(
  [string]$HostAddr = '127.0.0.1',
  [int]$Port = 3333
)
$env:MCP_ALLOW_FALLBACK_GET = '1'
$env:PYTHONPATH = "$PSScriptRoot\echo-bridge"
Write-Host ("Starting bridge with MCP_ALLOW_FALLBACK_GET=1 on {0}:{1}" -f $HostAddr,$Port) -ForegroundColor Cyan
Set-Location "$PSScriptRoot\echo-bridge"
python -m uvicorn echo_bridge.main:app --host $HostAddr --port $Port --http h11 --workers 1
