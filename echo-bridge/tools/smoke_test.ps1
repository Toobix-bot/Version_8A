# Smoke test for ECHO-Bridge manifest/OpenAPI (free, PowerShell)
# Usage: Open PowerShell in repo root and run: .\echo-bridge\tools\smoke_test.ps1

$public = $env:PUBLIC_BASE_URL
if (-not $public) {
    Write-Host "PUBLIC_BASE_URL not set; using default trycloudflare domain sample"
    $public = 'https://delete-organised-gsm-posing.trycloudflare.com'
}

$hdr = @{ Origin = 'https://chat.openai.com' }
$endpoints = @(
    "$public/openapi.json",
    "$public/chatgpt_tool_manifest.json",
    "$public/public/chatgpt_tool_manifest.json",
    "http://127.0.0.1:3333/openapi.json",
    "http://127.0.0.1:3333/chatgpt_tool_manifest.json",
    "http://127.0.0.1:3333/public/chatgpt_tool_manifest.json"
)

foreach ($u in $endpoints) {
    Write-Host "\nChecking: $u"
    try {
        $r = Invoke-WebRequest -Uri $u -Method GET -Headers $hdr -UseBasicParsing -TimeoutSec 15 -ErrorAction Stop
        $status = $r.StatusCode
        $ctype = $r.Headers['Content-Type']
        $acao = $r.Headers['Access-Control-Allow-Origin']
        if ($acao) {
            Write-Host "  Status: $status  Content-Type: $ctype  ACAO: $acao"
        } else {
            Write-Host "  Status: $status  Content-Type: $ctype  ACAO: <missing>"
        }
    } catch {
        Write-Host "  ERROR: $($_.Exception.Message)"
    }
}

Write-Host "\nSmoke test finished. If all endpoints return 200 and ACAO: *, the manifest is importable from ChatGPT."