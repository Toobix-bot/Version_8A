Write-Host '=== ECHO-BRIDGE DIAGNOSTIC ==='
Write-Host "Time: $(Get-Date)"

Write-Host "\n-- Python/uvicorn processes --"
Get-Process -Name python -ErrorAction SilentlyContinue | Select-Object Id, ProcessName, Path -Unique | Format-List
# Uvicorn might be a python process; show python commandlines via wmic if possible
try {
    Get-CimInstance Win32_Process | Where-Object { ($_.Name -like '*python*') -or ($_.CommandLine -match 'uvicorn') } | Select-Object ProcessId, Name, CommandLine | Format-List
} catch {
    Write-Host "Could not query Win32_Process: $_"
}

Write-Host "\n-- ngrok process --"
Get-Process -Name ngrok -ErrorAction SilentlyContinue | Select-Object Id, ProcessName, Path | Format-List
try {
    Get-CimInstance Win32_Process | Where-Object { ($_.Name -like '*ngrok*') -or ($_.CommandLine -match 'ngrok') } | Select-Object ProcessId, Name, CommandLine | Format-List
} catch {
    Write-Host "Could not query Win32_Process for ngrok: $_"
}

Write-Host "\n-- netstat for :3333 --"
netstat -ano | findstr ":3333" | ForEach-Object { Write-Host $_ }

Write-Host "\n-- ngrok local API (/api/tunnels) --"
try {
    $t = Invoke-RestMethod -Uri http://127.0.0.1:4040/api/tunnels -TimeoutSec 3 -ErrorAction Stop
    if ($t -and $t.tunnels) {
        $t.tunnels | ForEach-Object { Write-Host "public_url: $($_.public_url) -> proto: $($_.proto) -> config: $($_.config|ConvertTo-Json -Depth 3)" }
    } else {
        Write-Host "No tunnels returned or ngrok API returned empty response"
    }
} catch {
    Write-Host "NGROK API ERROR: $($_.Exception.Message)"
}

Write-Host "\n-- Tail bridge.log (last 200 lines) --"
$logPath = Join-Path $PSScriptRoot '..\bridge.log'
if (Test-Path $logPath) {
    Get-Content $logPath -Tail 200 | ForEach-Object { Write-Host $_ }
} else {
    Write-Host "bridge.log not found at $logPath"
}
