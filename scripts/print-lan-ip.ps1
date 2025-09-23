$ErrorActionPreference = 'Stop'
$ifaces = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' }
foreach ($i in $ifaces) {
    Write-Host ("Interface {0} IP {1}" -f $i.InterfaceAlias, $i.IPAddress)
}
