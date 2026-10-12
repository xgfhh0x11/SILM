<#
.SYNOPSIS
    Exercises the InterruptLatencyMonitor driver's real, working IOCTLs
    against an already-loaded service, inside the guest.

.DESCRIPTION
    Runs INSIDE the guest, against the \\.\InterruptLatencyMonitor device
    created by load.ps1 (this script does not load or unload the driver
    itself -- run load.ps1 -Arm first).

    Per shared/InterruptLatencyMonitor_abi.h and driver/InterruptLatencyMonitor.c
    (EvtIoDeviceControl), the IOCTL surface is:

      IOCTL_SET_CONFIG      - REAL. Sets EnableInstrumentation/UseRdtsc/
                               SamplingRate; also starts/stops the synthetic
                               KeSetTimerEx timer harness. Exercised.
      IOCTL_GET_EVENTS       - REAL. Drains the per-CPU lock-free ring buffer.
                               Exercised, per logical CPU.
      IOCTL_RESET_BUFFERS    - REAL. Zeroes all per-CPU rings. Exercised.
      IOCTL_GET_STATISTICS   - STUB. InterruptLatencyMonitor.c:549-555
                               unconditionally returns STATUS_NOT_IMPLEMENTED.
                               This script calls it and EXPECTS that failure;
                               it is reported as SKIP (known stub), not a
                               test failure. If it ever succeeds, that is a
                               driver change worth investigating, and is
                               flagged loudly.

    QueryDpcQueueDepth() (InterruptLatencyMonitor.c:758-765) is a separate,
    unrelated stub (always returns 0) inside the real ISR/DPC path, which is
    itself dead code in this build (no WdfInterruptCreate binding -- see
    README). It has no IOCTL of its own; it just means QueueDepth in every
    IRQ_EVENT this script reads back will be 0. Not tested directly here,
    only noted so a 0 QueueDepth is not mistaken for a bug.

    Every DeviceIoControl call is wrapped with a client-side timeout
    (default 5s) using a .NET Task so a genuinely hung IOCTL is reported
    as TIMEOUT rather than hanging this script forever. Note this is a
    best-effort guard only: if the kernel-mode call truly never returns,
    the underlying OS thread stays blocked and the guest itself may need
    a hard reset from the host (Hyper-V "Turn Off" / revert checkpoint) --
    see kernel-test/README.md SAFETY.

.PARAMETER Arm
    Required to actually open the device and send IOCTLs. Without it, this
    script only prints the plan (device path, IOCTL codes, structs) and
    exits 0 without touching the device.

.PARAMETER TimeoutMs
    Per-IOCTL client-side timeout in milliseconds. Default 5000.

.EXAMPLE
    # Safe, does nothing:
    .\smoke-test.ps1

.EXAMPLE
    # Actually exercise the driver (guest only, after load.ps1 -Arm):
    .\smoke-test.ps1 -Arm
#>

[CmdletBinding()]
param(
    [switch]$Arm,
    [int]$TimeoutMs = 5000
)

$ErrorActionPreference = 'Stop'

# =========================================================================
# Win32 / IOCTL plumbing
# =========================================================================

$csSource = @'
using System;
using System.Runtime.InteropServices;

public static class SilmNative
{
    public const uint GENERIC_READ  = 0x80000000;
    public const uint GENERIC_WRITE = 0x40000000;
    public const uint OPEN_EXISTING = 3;
    public const uint FILE_ATTRIBUTE_NORMAL = 0x80;
    public static readonly IntPtr INVALID_HANDLE_VALUE = new IntPtr(-1);

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    public static extern IntPtr CreateFileW(
        string lpFileName,
        uint dwDesiredAccess,
        uint dwShareMode,
        IntPtr lpSecurityAttributes,
        uint dwCreationDisposition,
        uint dwFlagsAndAttributes,
        IntPtr hTemplateFile);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool CloseHandle(IntPtr hObject);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool DeviceIoControl(
        IntPtr hDevice,
        uint dwIoControlCode,
        byte[] lpInBuffer,
        uint nInBufferSize,
        byte[] lpOutBuffer,
        uint nOutBufferSize,
        out uint lpBytesReturned,
        IntPtr lpOverlapped);
}
'@

Add-Type -TypeDefinition $csSource -ErrorAction Stop

# CTL_CODE(DeviceType, Function, Method, Access) --
#   ((DeviceType) << 16) | ((Access) << 14) | ((Function) << 2) | (Method)
# Mirrors shared/InterruptLatencyMonitor_abi.h exactly (FILE_DEVICE_UNKNOWN=0x22,
# METHOD_BUFFERED=0, FILE_ANY_ACCESS=0, IOCTL_BASE=0x8000).
function Get-CtlCode([uint32]$DeviceType, [uint32]$Function, [uint32]$Method, [uint32]$Access) {
    return ([uint32]($DeviceType -shl 16) -bor [uint32]($Access -shl 14) -bor [uint32]($Function -shl 2) -bor $Method)
}

$FILE_DEVICE_UNKNOWN = 0x22
$METHOD_BUFFERED     = 0
$FILE_ANY_ACCESS     = 0
$IOCTL_BASE          = 0x8000

$IOCTL_GET_EVENTS     = Get-CtlCode $FILE_DEVICE_UNKNOWN ($IOCTL_BASE + 0x01) $METHOD_BUFFERED $FILE_ANY_ACCESS
$IOCTL_GET_STATISTICS = Get-CtlCode $FILE_DEVICE_UNKNOWN ($IOCTL_BASE + 0x02) $METHOD_BUFFERED $FILE_ANY_ACCESS
$IOCTL_RESET_BUFFERS  = Get-CtlCode $FILE_DEVICE_UNKNOWN ($IOCTL_BASE + 0x03) $METHOD_BUFFERED $FILE_ANY_ACCESS
$IOCTL_SET_CONFIG     = Get-CtlCode $FILE_DEVICE_UNKNOWN ($IOCTL_BASE + 0x04) $METHOD_BUFFERED $FILE_ANY_ACCESS

# Wire-format sizes (natural 8-byte-aligned layout matches the driver's
# unpacked C structs in shared/InterruptLatencyMonitor_abi.h -- there is no
# #pragma pack on IRQ_EVENT / IOCTL_GET_EVENTS_OUT):
#   IRQ_EVENT: USHORT Vector(2) + UCHAR Cpu(1) + UCHAR Phase(1) + ULONG QueueDepth(4)
#            + LARGE_INTEGER Timestamp(8, 8-aligned) + ULONG64 TscValue(8) + ULONG64 SequenceId(8)
#            = 32 bytes.
#   IOCTL_GET_EVENTS_OUT: ULONG EventCount(4) + 4 bytes padding (Events needs 8-byte
#            alignment) + IRQ_EVENT Events[1] -> FIELD_OFFSET(Events) = 8.
$IRQ_EVENT_SIZE            = 32
$GET_EVENTS_OUT_HEADER_OFF = 8   # FIELD_OFFSET(IOCTL_GET_EVENTS_OUT, Events)
$GET_EVENTS_IN_SIZE        = 12  # ULONG CpuNumber, MaxEvents, StartIndex
$SET_CONFIG_SIZE           = 8   # BOOLEAN + BOOLEAN + pad(2) + ULONG SamplingRate

$DevicePath = '\\.\InterruptLatencyMonitor'

# =========================================================================
# Test harness helpers
# =========================================================================

$script:Results = New-Object System.Collections.Generic.List[object]

function Add-Result([string]$Name, [string]$Status, [string]$Detail) {
    $script:Results.Add([pscustomobject]@{ Name = $Name; Status = $Status; Detail = $Detail })
    $color = switch ($Status) {
        'PASS'    { 'Green' }
        'SKIP'    { 'Yellow' }
        'FAIL'    { 'Red' }
        'TIMEOUT' { 'Red' }
        default   { 'Gray' }
    }
    Write-Host ("[{0,-7}] {1} - {2}" -f $Status, $Name, $Detail) -ForegroundColor $color
}

function Invoke-IoctlWithTimeout {
    param(
        [Parameter(Mandatory)][IntPtr]$Handle,
        [Parameter(Mandatory)][uint32]$Code,
        [byte[]]$InBuffer = [byte[]]@(),
        [Parameter(Mandatory)][int]$OutSize,
        [Parameter(Mandatory)][int]$TimeoutMs
    )

    $outBuf = New-Object byte[] $OutSize
    $task = [System.Threading.Tasks.Task]::Run([Func[object]]{
        [uint32]$bytesReturned = 0
        $ok = [SilmNative]::DeviceIoControl($Handle, $Code, $InBuffer, [uint32]$InBuffer.Length, $outBuf, [uint32]$OutSize, [ref]$bytesReturned, [IntPtr]::Zero)
        $err = [System.Runtime.InteropServices.Marshal]::GetLastWin32Error()
        return [pscustomobject]@{ Ok = $ok; BytesReturned = $bytesReturned; Win32Error = $err }
    })

    if (-not $task.Wait($TimeoutMs)) {
        return [pscustomobject]@{ TimedOut = $true; Ok = $false; BytesReturned = 0; Win32Error = -1; OutBuffer = $outBuf }
    }

    $r = $task.Result
    return [pscustomobject]@{ TimedOut = $false; Ok = $r.Ok; BytesReturned = $r.BytesReturned; Win32Error = $r.Win32Error; OutBuffer = $outBuf }
}

# =========================================================================
# Plan (always printed)
# =========================================================================

Write-Host '=== SILM driver smoke test (guest-side) ===' -ForegroundColor Cyan
Write-Host "Device            : $DevicePath"
Write-Host ("IOCTL_SET_CONFIG     = 0x{0:X8}  (real)" -f $IOCTL_SET_CONFIG)
Write-Host ("IOCTL_GET_EVENTS     = 0x{0:X8}  (real)" -f $IOCTL_GET_EVENTS)
Write-Host ("IOCTL_RESET_BUFFERS  = 0x{0:X8}  (real)" -f $IOCTL_RESET_BUFFERS)
Write-Host ("IOCTL_GET_STATISTICS = 0x{0:X8}  (STUB -- expect STATUS_NOT_IMPLEMENTED)" -f $IOCTL_GET_STATISTICS)
Write-Host "Per-IOCTL timeout : $TimeoutMs ms"
Write-Host ''

if (-not $Arm) {
    Write-Host 'DRY RUN ONLY -- device was not opened, no IOCTLs were sent. Re-run with -Arm to actually exercise the driver.' -ForegroundColor Yellow
    Write-Host 'Prerequisite: kernel-test/load.ps1 -Arm must have already created + started the service in this guest.' -ForegroundColor Yellow
    exit 0
}

Write-Host '-Arm passed. Opening device and sending IOCTLs for real.' -ForegroundColor Red
Write-Host ''

# =========================================================================
# Open device
# =========================================================================

$handle = [SilmNative]::CreateFileW($DevicePath, ([SilmNative]::GENERIC_READ -bor [SilmNative]::GENERIC_WRITE), 0, [IntPtr]::Zero, [SilmNative]::OPEN_EXISTING, [SilmNative]::FILE_ATTRIBUTE_NORMAL, [IntPtr]::Zero)

if ($handle -eq [IntPtr]::Zero -or $handle -eq (New-Object IntPtr(-1))) {
    $err = [System.Runtime.InteropServices.Marshal]::GetLastWin32Error()
    Write-Host "FAILED to open $DevicePath (Win32 error $err)." -ForegroundColor Red
    Write-Host 'Is the service loaded? Run kernel-test/load.ps1 -Arm first, then sc query InterruptLatencyMonitor.' -ForegroundColor Red
    exit 1
}

try {
    # ---------------------------------------------------------------
    # 1. IOCTL_SET_CONFIG -- enable instrumentation (real; also starts
    #    the synthetic KeSetTimerEx timer harness so events accumulate).
    # ---------------------------------------------------------------
    # IOCTL_CONFIG: BOOLEAN EnableInstrumentation, BOOLEAN UseRdtsc,
    # ULONG SamplingRate (2-byte pad before the ULONG for 4-byte alignment).
    $configIn = New-Object byte[] $SET_CONFIG_SIZE
    $configIn[0] = 1   # EnableInstrumentation = TRUE
    $configIn[1] = 0   # UseRdtsc = FALSE (keep ISR-level behavior unmodified)
    [System.BitConverter]::GetBytes([uint32]1).CopyTo($configIn, 4)  # SamplingRate = 1

    $r = Invoke-IoctlWithTimeout -Handle $handle -Code $IOCTL_SET_CONFIG -InBuffer $configIn -OutSize 0 -TimeoutMs $TimeoutMs
    if ($r.TimedOut) {
        Add-Result 'IOCTL_SET_CONFIG (enable)' 'TIMEOUT' "no response within ${TimeoutMs}ms"
    } elseif ($r.Ok) {
        Add-Result 'IOCTL_SET_CONFIG (enable)' 'PASS' 'instrumentation enabled, sampling=1'
    } else {
        Add-Result 'IOCTL_SET_CONFIG (enable)' 'FAIL' "Win32 error $($r.Win32Error)"
    }

    # Let the 1kHz synthetic timer harness populate the ring buffers.
    Write-Host 'Waiting 750ms for the synthetic timer harness to generate events...'
    Start-Sleep -Milliseconds 750

    # ---------------------------------------------------------------
    # 2. IOCTL_GET_EVENTS -- drain each logical CPU's ring (real).
    #    Sanity check: call succeeds (or fails cleanly), EventCount is
    #    within [0, MaxEvents], no hang.
    # ---------------------------------------------------------------
    $cpuCount = [Environment]::ProcessorCount
    $maxEvents = 64
    $outSize = $GET_EVENTS_OUT_HEADER_OFF + ($maxEvents * $IRQ_EVENT_SIZE)
    $totalEventsSeen = 0

    for ($cpu = 0; $cpu -lt $cpuCount; $cpu++) {
        $inBuf = New-Object byte[] $GET_EVENTS_IN_SIZE
        [System.BitConverter]::GetBytes([uint32]$cpu).CopyTo($inBuf, 0)        # CpuNumber
        [System.BitConverter]::GetBytes([uint32]$maxEvents).CopyTo($inBuf, 4)  # MaxEvents
        [System.BitConverter]::GetBytes([uint32]0).CopyTo($inBuf, 8)           # StartIndex = 0 (from Tail)

        $r = Invoke-IoctlWithTimeout -Handle $handle -Code $IOCTL_GET_EVENTS -InBuffer $inBuf -OutSize $outSize -TimeoutMs $TimeoutMs

        if ($r.TimedOut) {
            Add-Result "IOCTL_GET_EVENTS (cpu $cpu)" 'TIMEOUT' "no response within ${TimeoutMs}ms"
            continue
        }
        if (-not $r.Ok) {
            Add-Result "IOCTL_GET_EVENTS (cpu $cpu)" 'FAIL' "Win32 error $($r.Win32Error)"
            continue
        }

        $eventCount = [System.BitConverter]::ToUInt32($r.OutBuffer, 0)
        if ($eventCount -gt $maxEvents) {
            Add-Result "IOCTL_GET_EVENTS (cpu $cpu)" 'FAIL' "EventCount=$eventCount exceeds requested MaxEvents=$maxEvents (bounds violation)"
            continue
        }
        $totalEventsSeen += $eventCount
        Add-Result "IOCTL_GET_EVENTS (cpu $cpu)" 'PASS' "EventCount=$eventCount (bytesReturned=$($r.BytesReturned))"
    }

    if ($totalEventsSeen -eq 0) {
        Write-Host 'NOTE: zero events observed across all CPUs. The synthetic timer harness may need more than 750ms, or instrumentation did not actually enable -- not necessarily a driver bug, but worth re-checking manually with a longer -TimeoutMs / sleep if this persists.' -ForegroundColor Yellow
    }

    # ---------------------------------------------------------------
    # 3. IOCTL_RESET_BUFFERS (real).
    # ---------------------------------------------------------------
    $r = Invoke-IoctlWithTimeout -Handle $handle -Code $IOCTL_RESET_BUFFERS -InBuffer @() -OutSize 0 -TimeoutMs $TimeoutMs
    if ($r.TimedOut) {
        Add-Result 'IOCTL_RESET_BUFFERS' 'TIMEOUT' "no response within ${TimeoutMs}ms"
    } elseif ($r.Ok) {
        Add-Result 'IOCTL_RESET_BUFFERS' 'PASS' 'rings reset'
    } else {
        Add-Result 'IOCTL_RESET_BUFFERS' 'FAIL' "Win32 error $($r.Win32Error)"
    }

    # ---------------------------------------------------------------
    # 4. IOCTL_GET_STATISTICS -- documented STUB. Expected to fail with
    #    STATUS_NOT_IMPLEMENTED (InterruptLatencyMonitor.c:549-555).
    #    Report as SKIP, not FAIL, unless it unexpectedly succeeds.
    # ---------------------------------------------------------------
    $statsOutSize = 4 + (8 * 8)  # generously sized; driver never writes to it today
    $r = Invoke-IoctlWithTimeout -Handle $handle -Code $IOCTL_GET_STATISTICS -InBuffer @() -OutSize $statsOutSize -TimeoutMs $TimeoutMs
    if ($r.TimedOut) {
        Add-Result 'IOCTL_GET_STATISTICS' 'TIMEOUT' "no response within ${TimeoutMs}ms (stub should fail fast -- investigate)"
    } elseif ($r.Ok) {
        Add-Result 'IOCTL_GET_STATISTICS' 'FAIL' 'UNEXPECTED SUCCESS -- source says this is STATUS_NOT_IMPLEMENTED (InterruptLatencyMonitor.c:549-555); driver behavior no longer matches this script''s assumption, re-check before trusting this IOCTL'
    } else {
        Add-Result 'IOCTL_GET_STATISTICS' 'SKIP' "not implemented in driver (Win32 error $($r.Win32Error)), as documented -- expected"
    }

    # ---------------------------------------------------------------
    # 5. Cleanup: disable instrumentation (stops the synthetic timer).
    # ---------------------------------------------------------------
    $configOff = New-Object byte[] $SET_CONFIG_SIZE
    $configOff[0] = 0
    [System.BitConverter]::GetBytes([uint32]1).CopyTo($configOff, 4)
    $r = Invoke-IoctlWithTimeout -Handle $handle -Code $IOCTL_SET_CONFIG -InBuffer $configOff -OutSize 0 -TimeoutMs $TimeoutMs
    if ($r.TimedOut) {
        Add-Result 'IOCTL_SET_CONFIG (disable)' 'TIMEOUT' "no response within ${TimeoutMs}ms"
    } elseif ($r.Ok) {
        Add-Result 'IOCTL_SET_CONFIG (disable)' 'PASS' 'instrumentation disabled, synthetic timer stopped'
    } else {
        Add-Result 'IOCTL_SET_CONFIG (disable)' 'FAIL' "Win32 error $($r.Win32Error)"
    }
}
finally {
    [SilmNative]::CloseHandle($handle) | Out-Null
}

# =========================================================================
# Summary
# =========================================================================

Write-Host ''
Write-Host '=== Summary ===' -ForegroundColor Cyan
$script:Results | Format-Table -AutoSize | Out-String | Write-Host

$fails = $script:Results | Where-Object { $_.Status -in @('FAIL', 'TIMEOUT') }
if ($fails.Count -gt 0) {
    Write-Host "$($fails.Count) check(s) FAILED/TIMED OUT." -ForegroundColor Red
    Write-Host 'If anything hung or the guest is unresponsive, do not troubleshoot live -- revert the Hyper-V checkpoint from the host. See kernel-test/README.md SAFETY.' -ForegroundColor Red
    exit 1
}

Write-Host 'All exercised IOCTLs behaved as expected (IOCTL_GET_STATISTICS correctly skipped as a documented stub).' -ForegroundColor Green
exit 0
