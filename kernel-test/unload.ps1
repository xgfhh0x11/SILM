<#
.SYNOPSIS
    Stops and removes the InterruptLatencyMonitor kernel service.

.DESCRIPTION
    Runs INSIDE the guest. Always safe to run (stop+delete of a driver
    service does not require -Arm the way load.ps1's start does) -- but it
    is still printed as a plan first so you can see exactly what will run.
    Use -Force to skip the confirmation-free "just do it" path is already
    the default; -Force here only suppresses the "service not found"
    early-exit so the script still tries delete even if query looked odd.

.EXAMPLE
    .\unload.ps1
#>

[CmdletBinding()]
param(
    [string]$ServiceName = 'InterruptLatencyMonitor',
    [switch]$Force
)

$ErrorActionPreference = 'Continue'

Write-Host '=== SILM driver unload (guest-side) ===' -ForegroundColor Cyan
Write-Host "Service: $ServiceName"
Write-Host ''

$queryOutput = & sc.exe query $ServiceName 2>&1
$exists = $LASTEXITCODE -eq 0

if (-not $exists -and -not $Force) {
    Write-Host "Service '$ServiceName' not found (sc.exe query exit $LASTEXITCODE). Nothing to unload." -ForegroundColor Yellow
    Write-Host $queryOutput
    exit 0
}

Write-Host "Stopping '$ServiceName'..."
& sc.exe stop $ServiceName 2>&1 | Write-Host
Start-Sleep -Seconds 2

Write-Host "Deleting '$ServiceName'..."
& sc.exe delete $ServiceName 2>&1 | Write-Host
$deleteExit = $LASTEXITCODE

if ($deleteExit -ne 0) {
    Write-Host "sc.exe delete returned $deleteExit (service may already be gone, or a handle is still open -- reboot the guest if it won't go away)." -ForegroundColor Yellow
} else {
    Write-Host "Service '$ServiceName' removed." -ForegroundColor Green
}

Write-Host ''
Write-Host 'Verify: sc.exe query ' $ServiceName ' (should report 1060, service does not exist)'
exit 0
