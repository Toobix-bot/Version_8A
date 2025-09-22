param(
    [string]$Url = "http://127.0.0.1:3336/mcp",
    [int]$TimeoutSec = 3
)
$ErrorActionPreference = 'SilentlyContinue'

try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec $TimeoutSec
    Write-Host "Status:" $r.StatusCode
    if ($r.Headers.ContainsKey('Content-Type')) {
        Write-Host "Content-Type:" $r.Headers['Content-Type']
    }
    if ($r.Content) {
        $snippet = if ($r.Content.Length -gt 400) { $r.Content.Substring(0,400) } else { $r.Content }
        Write-Host "Body:" $snippet
    }
}
catch {
    if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
        Write-Host "Status:" $_.Exception.Response.StatusCode.Value__
    } else {
        Write-Host "ERR:" $_.Exception.Message
    }
}
