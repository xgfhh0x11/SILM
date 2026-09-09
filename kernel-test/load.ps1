<#
.SYNOPSIS
    Installs (sc create) and starts the InterruptLatencyMonitor kernel
    service INSIDE the disposable test guest.

.DESCRIPTION
    THIS SCRIPT RUNS INSIDE THE GUEST VM ("WinKDbg" or equivalent), never
    on the host. It never connects to anything itself -- it only shells out
    to sc.exe locally.

    By default this is a DRY RUN: it prints exactly what it would do
    (the sc.exe commands, with real argument values) and does nothing.
    Loading an unfinished/unsigned kernel driver can bugcheck the machine,
    so nothing is armed unless you pass -Arm explicitly.

    Before running with -Arm:
      1. Take a Hyper-V checkpoint of the guest (see kernel-test/README.md).
      2. Confirm test-signing is enabled (bcdedit /enum | findstr testsigning)
         and the guest has rebooted since it was enabled.
      3. Have the host's kd.exe already attached over the kdnet link, or be
         ready to attach immediately, since a bad load can bugcheck before
         you get a prompt back.

.PARAMETER SysPath
    Path (inside the guest) to InterruptLatencyMonitor.sys. Defaults to
    .\InterruptLatencyMonitor.sys next to this script -- copy the .sys
    built by build.ps1 (on the host) into the guest alongside this script,
    or pass an explicit path.

.PARAMETER Arm
    Required to actually run sc.exe. Without it, this script only prints
    the plan.

.EXAMPLE
    # See what would happen (safe, does nothing):
    .\load.ps1

.EXAMPLE
    # Actually create + start the service (guest only, after checkpoint):
    .\load.ps1 -Arm -SysPath C:\test\InterruptLatencyMonitor.sys
#>

[CmdletBinding()]
param(
    [string]$SysPath = (Join-Path $PSScriptRoot 'InterruptLatencyMonitor.sys'),
    [string]$ServiceName = 'InterruptLatencyMonitor',
    [switch]$Arm
)

$ErrorActionPreference = 'Stop'

function Assert-InGuestSanityCheck {
    # Best-effort guard against accidentally running this against the host.
    # Not foolproof -- the real safety boundary is the -Arm gate plus the
    # operator's own checkpoint discipline (see README.md SAFETY section).
    $cs = Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction SilentlyContinue
    if ($cs -and $cs.Model -notmatch 'Virtual Machine|VMware|KVM|Hyper-V') {
        Write-Host "WARNING: this machine does not report as a VM (Model='$($cs.Model)')." -ForegroundColor Yellow
        Write-Host 'load.ps1 is meant to run INSIDE the disposable guest, never on the host.' -ForegroundColor Yellow
        if ($Arm) {
            Write-Host 'Refusing to -Arm on a machine that does not look like a VM.' -ForegroundColor Red
            exit 1
        }
    }
}

Write-Host '=== SILM driver load (guest-side) ===' -ForegroundColor Cyan
Assert-InGuestSanityCheck

if (-not (Test-Path $SysPath)) {
    Write-Host "NOTE: $SysPath does not exist yet on this machine." -ForegroundColor Yellow
    Write-Host 'Copy the .sys built by kernel-test/build.ps1 (on the host) into the guest first.'
    if ($Arm) {
        Write-Host 'Refusing to -Arm without a real .sys on disk.' -ForegroundColor Red
        exit 1
    }
}

$binPath = if (Test-Path $SysPath) { (Resolve-Path $SysPath).Path } else { $SysPath }

$planSteps = @(
    "sc.exe query $ServiceName                                              # check for a pre-existing service"
    "sc.exe stop $ServiceName                                               # (only if already running)"
    "sc.exe delete $ServiceName                                             # (only if already present)"
    "sc.exe create $ServiceName type= kernel binPath= `"$binPath`" start= demand"
    "sc.exe start $ServiceName                                              # <-- THIS LINE CAN BUGCHECK THE GUEST"
)

Write-Host ''
Write-Host 'Service name : ' $ServiceName
Write-Host 'Driver path  : ' $binPath
Write-Host ''
Write-Host 'Plan:'
$planSteps | ForEach-Object { Write-Host "  $_" }
Write-Host ''

if (-not $Arm) {
    Write-Host 'DRY RUN ONLY -- no sc.exe command was executed. Re-run with -Arm to actually load the driver.' -ForegroundColor Yellow
    Write-Host 'Before -Arm: take a Hyper-V checkpoint of this guest from the HOST. See kernel-test/README.md SAFETY.' -ForegroundColor Yellow
    exit 0
}

Write-Host '-Arm passed. Proceeding for real.' -ForegroundColor Red
Write-Host 'If this guest was not just checkpointed, Ctrl+C now.' -ForegroundColor Red

# Stop/remove any pre-existing service instance first (idempotent reload).
$existing = & sc.exe query $ServiceName 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "Existing service '$ServiceName' found -- stopping and deleting it first."
    & sc.exe stop $ServiceName 2>&1 | Write-Host
    Start-Sleep -Seconds 2
    & sc.exe delete $ServiceName 2>&1 | Write-Host
}

Write-Host "Creating service '$ServiceName'..."
& sc.exe create $ServiceName type= kernel binPath= "$binPath" start= demand 2>&1 | Write-Host
if ($LASTEXITCODE -ne 0) {
    Write-Host "sc.exe create failed (exit $LASTEXITCODE)." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "Starting service '$ServiceName' -- if the machine bugchecks, that is expected-possible per README SAFETY." -ForegroundColor Red
& sc.exe start $ServiceName 2>&1 | Write-Host
$startExit = $LASTEXITCODE

if ($startExit -ne 0) {
    Write-Host "sc.exe start failed (exit $startExit)." -ForegroundColor Red
    Write-Host 'If this is 0xC0000428 (STATUS_INVALID_IMAGE_HASH), the driver is unsigned -- enable test-signing and reboot, or sign it.' -ForegroundColor Yellow
    exit $startExit
}

Write-Host ''
Write-Host 'Service started. Verify with: sc.exe query ' $ServiceName
Write-Host 'Next: run kernel-test/smoke-test.ps1 -Arm inside this guest, and watch the host kd session.'
exit 0
