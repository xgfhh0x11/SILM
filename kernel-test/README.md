# SILM kernel-test infrastructure

Scripts + runbook for dynamically testing the `InterruptLatencyMonitor`
kernel driver against a **disposable** Hyper-V guest ("WinKDbg" or
equivalent), with a live `kd.exe` (kdnet) debugger attached from the
host.

This directory is scripts and documentation only. Nothing here connects
to a VM, loads a driver, or executes anything by default -- every script
that touches the device or the service requires an explicit `-Arm` flag,
and dry-runs otherwise.

**PowerShell 5.1 compatible.** No `pwsh`-only syntax is used.

## What's here

| File               | Runs on | Purpose |
|--------------------|---------|---------|
| `build.ps1`        | Host    | `msbuild` Release\|x64 build of the driver. Prints the `.sys` path on success; prints real MSBuild errors and exits non-zero on failure. |
| `load.ps1`         | Guest   | `sc.exe create` + `sc.exe start` for the service. Dry-run unless `-Arm`. |
| `unload.ps1`       | Guest   | `sc.exe stop` + `sc.exe delete` for the service. |
| `smoke-test.ps1`   | Guest   | Opens the device, exercises the driver's real IOCTLs, checks sane responses / no hang. Dry-run unless `-Arm`. |
| `kd-triage.txt`    | Host    | `kd.exe` command reference: first break-in, `!analyze -v`, Driver Verifier, IOCTL-hang triage. |

## Driver identity (from the repo, not guessed)

- Service name: `InterruptLatencyMonitor`
- Driver binary: `InterruptLatencyMonitor.sys`
- Build output (host, from repo root): `x64\Release\InterruptLatencyMonitor.sys`
- Device path (opened by clients): `\\.\InterruptLatencyMonitor`
- KMDF version: 1.15 (`driver/InterruptLatencyMonitor.inf`)
- IOCTLs (`shared/InterruptLatencyMonitor_abi.h`, `IOCTL_BASE = 0x8000`):
  - `IOCTL_GET_EVENTS` (0x8001) -- **real**, drains a per-CPU ring buffer.
  - `IOCTL_GET_STATISTICS` (0x8002) -- **stub**. `driver/InterruptLatencyMonitor.c:527-533`
    unconditionally returns `STATUS_NOT_IMPLEMENTED`. Not wired to any
    real aggregation. `smoke-test.ps1` calls it and expects that failure.
  - `IOCTL_RESET_BUFFERS` (0x8003) -- **real**, zeroes all per-CPU rings.
  - `IOCTL_SET_CONFIG` (0x8004) -- **real**, toggles instrumentation and
    starts/stops the synthetic `KeSetTimerEx` timer harness.

## Honest status of the driver you're testing

Per the code review (see repo root review notes) and confirmed by reading
`driver/InterruptLatencyMonitor.c` directly:

- **There is no real interrupt source bound.** `EvtInterruptIsr` /
  `EvtInterruptDpc` are fully implemented but dead code -- nothing calls
  `WdfInterruptCreate`, so they never run. The only thing that ever
  generates events in this build is the synthetic 1kHz `KeSetTimerEx`
  timer harness (`SyntheticTimerDpc` / `SyntheticWorkDpc`). Any "dynamic
  test" against this driver today is exercising the synthetic path, not
  a real ISR/DPC latency chain.
- **`IOCTL_GET_STATISTICS` is a stub that always fails** (`STATUS_NOT_IMPLEMENTED`).
  Do not write a test that expects it to succeed, and do not treat its
  failure as a regression.
- **`QueryDpcQueueDepth()` is a hardcoded stub that always returns 0.**
  Every `IRQ_EVENT.QueueDepth` you read back from the real driver will be
  0. This is not evidence of a stuck DPC queue.
- **The "microarchitectural witness" (TSC/QPC ratio) result documented in
  the repo README is synthetic**, produced by
  `scripts/generate_microarch_demo.py` deliberately planting the exact
  ratio the detector recovers (`mad == 0.0` over 400+ samples is a
  degenerate/toy-data signature, not something real hardware telemetry
  would produce). Nothing in this `kernel-test/` directory tests, relies
  on, or reproduces that result, and nothing here should be built to
  make it look like a real hardware finding. If you want an actual
  empirical microarch result, it has to come from real TSC/QPC samples
  captured off this driver on real hardware -- out of scope for this
  harness.

## Prerequisites

**Host** (already set up per the task context):
- Visual Studio 2022 + WDK 10.0.26100 + KMDF 1.15 (for `build.ps1`).
- `kd.exe` / `kdnet.exe` (WinDbg / Debugging Tools for Windows).
- Hyper-V, with the "WinKDbg" guest already created.

**Guest ("WinKDbg", disposable)**:
- Windows, with an admin account you can run `load.ps1` / `unload.ps1` /
  `smoke-test.ps1` from.
- Test-signing enabled (see step 2 below) if the `.sys` isn't otherwise
  signed. Without it, `sc start` fails with `0xC0000428`
  (`STATUS_INVALID_IMAGE_HASH`).
- kdnet debug settings configured (step 3 below) so the host's `kd.exe`
  can attach.

## Runbook

### 1. Build on the host

```powershell
cd C:\Users\tylersec\Desktop\gh-review\SILM\kernel-test
.\build.ps1
```

On success this prints the absolute path to `InterruptLatencyMonitor.sys`
(normally `<repo>\x64\Release\InterruptLatencyMonitor.sys`). On failure
it prints the actual MSBuild error lines and exits non-zero -- it does
not print a fake success message. Copy the `.sys` to the guest (shared
folder, `Copy-VMFile`, or a mapped drive) once it builds.

### 2. Guest: enable test-signing, then reboot

Inside the guest, elevated:

```cmd
bcdedit /set testsigning on
shutdown /r /t 0
```

Test-signing is a persistent boot-configuration change to the guest.
That's fine here because the guest is disposable and you're about to
checkpoint it anyway -- just do this **before** the checkpoint in the
next step, not after, so the checkpoint you revert to already has
test-signing on and doesn't need a second reboot mid-iteration.

### 3. Checkpoint the guest FIRST (before any driver load)

From the **host**, once the guest has rebooted with test-signing on and
is otherwise in the clean state you want to iterate from:

```powershell
Checkpoint-VM -Name 'WinKDbg' -SnapshotName 'pre-driver-load'
```

Do this before every session where you're about to load a new/changed
build of the driver, not just once. A kernel driver in active
development can bugcheck the guest; the checkpoint is your recovery
path (see SAFETY below), and it's cheap -- there's no reason to skip it
because "this build is probably fine."

### 4. Configure kdnet on the guest, get PORT and KEY

Inside the guest, elevated (first time only -- picks a NIC and prints
the key):

```cmd
bcdedit /dbgsettings net hostip:<HOST_IP> port:50000 key:1.2.3.4
bcdedit /debug on
shutdown /r /t 0
```

`hostip` is the IP the guest can reach the host at on your Hyper-V
virtual switch (not the guest's own IP). After it reboots, confirm the
active settings and read back the actual PORT/KEY kdnet is using:

```cmd
bcdedit /dbgsettings
```

This prints the debug type (`NET`), the negotiated port, and the key --
use exactly what it reports, not what you guessed above, since kdnet can
normalize/regenerate the key.

### 5. Attach kd.exe from the host

```powershell
kd -k net:port=<PORT>,key=<KEY>
```

Wait for the initial connect. See `kd-triage.txt` for what to do once
you're at a kernel prompt (`.reload`, `!analyze -v`, Driver Verifier
setup, hang triage).

### 6. Load the driver in the guest (dry-run first)

```powershell
# From the guest, in the directory where you copied the .sys +
# kernel-test\load.ps1:
.\load.ps1
# Review the printed plan, then:
.\load.ps1 -Arm -SysPath C:\test\InterruptLatencyMonitor.sys
```

`load.ps1` never runs `sc.exe` without `-Arm`. With kd.exe already
attached from step 5, a bugcheck on `sc start` will break into the
debugger rather than just resetting the guest silently.

### 7. Smoke-test the real IOCTLs

```powershell
.\smoke-test.ps1        # dry-run: prints the plan, touches nothing
.\smoke-test.ps1 -Arm   # actually opens \\.\InterruptLatencyMonitor and sends IOCTLs
```

Exercises `IOCTL_SET_CONFIG`, `IOCTL_GET_EVENTS` (per logical CPU), and
`IOCTL_RESET_BUFFERS`, checking for a clean response within a
client-side timeout (default 5s, `-TimeoutMs` to change). Calls
`IOCTL_GET_STATISTICS` too, but reports its expected
`STATUS_NOT_IMPLEMENTED` failure as `SKIP`, not `FAIL` -- see "Honest
status" above.

### 8. Unload

```powershell
.\unload.ps1
```

### 9. Revert the checkpoint before the next iteration

From the host:

```powershell
Restore-VMCheckpoint -Name 'pre-driver-load' -VMName 'WinKDbg' -Confirm:$false
```

Do this routinely, not just after a crash -- it's the cheapest way to
guarantee the next test run starts from a known-clean state (no stray
service registration, no half-unloaded driver object, no Driver
Verifier settings left on from a previous experiment).

## SAFETY

- **Loading a kernel driver under active development can bugcheck the
  guest.** This is expected, not a script bug. That's the entire reason
  for the checkpoint-first discipline above.
- **Checkpoint before every load, every time**, including "this is just
  a smoke test, nothing changed" runs. It's cheap; a bad guest state
  silently corrupting your next test's results is not.
- **`load.ps1` and `smoke-test.ps1` never act without `-Arm`.** If you
  see either script actually calling `sc.exe` or opening the device
  without you having passed `-Arm`, stop and treat that as a bug in the
  script, not intended behavior.
- **If the guest bugchecks or hangs:** don't try to nurse it back —
  capture `!analyze -v` from the attached `kd.exe` session (see
  `kd-triage.txt`), then revert the checkpoint from the host
  (`Restore-VMCheckpoint`, or "Revert" in Hyper-V Manager). If `kd.exe`
  itself is wedged, a hard guest power-off (`Stop-VM -TurnOff -Force`)
  followed by the checkpoint revert is fine -- the guest is disposable.
- **`smoke-test.ps1`'s per-IOCTL timeout is a client-side guard, not a
  cancellation.** If a kernel-mode call genuinely never returns, the
  blocked OS thread stays blocked; the guest may need the same
  revert-from-host treatment as a bugcheck, not further troubleshooting
  from inside the guest.
- **`load.ps1` refuses to `-Arm` on a machine that doesn't report as a
  VM** (best-effort `Win32_ComputerSystem` model check). This is a
  guard-rail, not a guarantee -- know which machine you're on before you
  pass `-Arm`.
- **Driver Verifier changes are a guest-wide, persistent, reboot-required
  setting** (`kd-triage.txt` section 3). Enable it on a fresh checkpoint,
  and revert back out of it when you're done, rather than leaving a
  Verifier-enabled guest as your new "clean" baseline by accident.
- Nothing in this directory was executed against any VM as part of
  producing it. `build.ps1` was not run against the host WDK toolchain
  either -- it was written directly from the `.vcxproj`/`build_vs.bat`/
  `BUILD_AND_VERIFY.md` build configuration in this repo, not verified
  by an actual build in this session.
