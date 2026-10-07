# Prints the machine's LAN IPv4 address (the adapter holding the default route).
# Skips VPN and virtual adapters so the printed address is the one other devices can reach.
$ErrorActionPreference = 'SilentlyContinue'
foreach ($c in Get-NetIPConfiguration) {
    if ($c.IPv4DefaultGateway -and
        $c.NetAdapter.Status -eq 'Up' -and
        $c.InterfaceAlias -notmatch 'VPN|Tailscale|WireGuard|Loopback|vEthernet') {
        Write-Output $c.IPv4Address.IPAddress
        break
    }
}
