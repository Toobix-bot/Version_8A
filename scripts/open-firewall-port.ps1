param(
    [int]$Port = 3337,
    [string]$RuleName = "ECHO-BRIDGE MCP",
    [string]$Protocol = "TCP"
)
$ErrorActionPreference = 'Stop'

# Check if rule exists
$existing = & netsh advfirewall firewall show rule name="$RuleName" 2>$null | Select-String -Pattern "Rule Name"
if ($existing) {
    Write-Host "[open-firewall-port] Rule '$RuleName' already exists. Skipping add."
    return
}

Write-Host "[open-firewall-port] Adding inbound firewall rule for $Protocol/$Port"
& netsh advfirewall firewall add rule name="$RuleName" dir=in action=allow protocol=$Protocol localport=$Port | Out-Null
Write-Host "[open-firewall-port] Done."
