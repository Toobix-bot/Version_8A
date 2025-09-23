param(
    [int]$Port = 3337
)
$ErrorActionPreference = 'Stop'

# 1) Open firewall
& "$PSScriptRoot\open-firewall-port.ps1" -Port $Port -RuleName "ECHO-BRIDGE MCP $Port" | Out-Null

# 2) Print LAN IPs
& "$PSScriptRoot\print-lan-ip.ps1"

# 3) Start server on 0.0.0.0
& "$PSScriptRoot\start-standalone-mcp-public.ps1" -BindHost "0.0.0.0" -BindPort $Port
