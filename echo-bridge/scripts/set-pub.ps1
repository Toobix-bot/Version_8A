param(
  [Parameter(Mandatory=$true)][string]$Pub
)

$manifestPath = "public\chatgpt_tool_manifest.json"
$openapiPath  = "public\openapi.json"

# 1) Manifest laden + api.url setzen
$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
$manifest.api.url = "$Pub/public/openapi.json"
$manifest | ConvertTo-Json -Depth 32 | Set-Content -Encoding UTF8 $manifestPath

# 2) OpenAPI laden + servers[0].url setzen (oder anlegen)
$openapi = Get-Content $openapiPath -Raw | ConvertFrom-Json
if (-not $openapi.servers) { $openapi | Add-Member -MemberType NoteProperty -Name servers -Value @() }
if ($openapi.servers.Count -eq 0) { $openapi.servers += @{ url = "$Pub" } } else { $openapi.servers[0].url = "$Pub" }
$openapi | ConvertTo-Json -Depth 32 | Set-Content -Encoding UTF8 $openapiPath

Write-Host "Patched:"
Write-Host "  manifest.api.url  =" $manifest.api.url
Write-Host "  openapi.servers[0].url =" $openapi.servers[0].url

# 3) Reachability-Checks
function Probe($label, $url) {
  try {
    $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8
    $body = $r.Content
    if ($body.Length -gt 220) { $body = $body.Substring(0,220) }
    Write-Host "$label $($r.StatusCode) $((($r.Headers).'Content-Type'))"
    Write-Host $body
  } catch {
    Write-Host "$label ERR $($_.Exception.Message)"
  }
}

Probe "MANIFEST" "$Pub/public/chatgpt_tool_manifest.json"
Probe "OPENAPI " "$Pub/public/openapi.json"
