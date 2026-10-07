# OPTIONAL - only if other devices on your home network should use this server.
# Run ONCE, as Administrator (right-click -> Run with PowerShell as admin). Safe to re-run.
#
# What it changes (both are Windows system settings - read before running):
#   1. marks your current internet-connected network as "Private" (if it is "Public");
#   2. adds an inbound firewall rule for TCP <port>, Private networks only, local subnet only.
# The server must also be configured to listen on the network (onboarding's LAN option sets
# HOST=0.0.0.0 in config\machine.cmd). Undo: Remove-NetFirewallRule -DisplayName "Local LLM server (8080)"
param([int]$Port = 8080)
$RuleName = "Local LLM server ($Port)"

Write-Host "=== Current networks ===" -ForegroundColor Cyan
Get-NetConnectionProfile | Select-Object Name, InterfaceAlias, NetworkCategory, IPv4Connectivity | Format-Table -AutoSize

$p = Get-NetConnectionProfile | Where-Object { $_.IPv4Connectivity -eq 'Internet' } | Select-Object -First 1
if (-not $p) { Write-Host "No internet-connected profile found." -ForegroundColor Red; Read-Host "Enter to exit"; exit 1 }

if ($p.NetworkCategory -ne 'Private') {
    Write-Host "Setting '$($p.Name)' from $($p.NetworkCategory) to Private..." -ForegroundColor Yellow
    Write-Host "Only do this on a network you trust (your home), never on public Wi-Fi." -ForegroundColor Yellow
    $ok = Read-Host "Continue? [y/N]"
    if ($ok -ne 'y') { exit 1 }
    Set-NetConnectionProfile -InterfaceIndex $p.InterfaceIndex -NetworkCategory Private
} else {
    Write-Host "'$($p.Name)' is already Private." -ForegroundColor Green
}

$existing = Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue
if ($existing) { Remove-NetFirewallRule -DisplayName $RuleName }
New-NetFirewallRule -DisplayName $RuleName -Direction Inbound -Action Allow `
    -Protocol TCP -LocalPort $Port -Profile Private -RemoteAddress LocalSubnet | Out-Null
Write-Host "Firewall rule created: TCP $Port inbound, Private profile, LocalSubnet only." -ForegroundColor Green

Write-Host ""
Write-Host "Done. Start the server with Start-Local-LLM-Server.bat." -ForegroundColor Cyan
Read-Host "Press Enter to close"
