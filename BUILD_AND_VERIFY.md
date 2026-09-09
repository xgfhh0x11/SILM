# SILM (Per-CPU Interrupt Latency Monitor) — Build & Verification

> *Last updated: 2026-05-14 — post P0–P3 fix pass.*

> *Quality gate for the HBO NL portfolio. This file answers:
> "Is this project buildable, runnable, and behaving as documented?"*

SILM is a four-stack research framework:

1. **KMDF kernel driver** (`driver/`, C, ~792 LOC) — per-CPU lock-free ring
   buffers, ISR/DPC event capture, IOCTL surface.
2. **C++17 userspace daemon** (`userspace/`, ~279 LOC) — trace recorder, drains
   the driver's IOCTL channel and writes binary `.silm-trace` files.
3. **Python analysis layer** (`gui/`) — `trace_parser.py`,
   `statistics_processor.py` (EWMA / CUSUM / percentiles), `policy_engine.py`,
   `microarch_witness.py` (TSC/QPC ratio anomaly detector), `GUI.py`
   (matplotlib panels).
4. **Trace generators & sample data** (`scripts/`, `examples/`) — deterministic
   trace synthesisers, two checked-in demo traces.

Each component is built and verified independently. The Python stack is the
only one with automated tests.

---

## 1. Build

### 1.1 Primary build path

- **Platform**: Windows 10/11 x64 (driver + daemon are Windows-only;
  Python tests run cross-platform and are exercised on Ubuntu by CI).
- **Toolchain**:
  - **Driver**: Visual Studio 2022 + Windows Driver Kit (WDK) 10.0.26100,
    Spectre-mitigated x64 libs, KMDF 1.15.
    Toolset `WindowsKernelModeDriver10.0`, `ConfigurationType=Driver`,
    `DriverType=WDM`.
  - **Daemon**: MSVC (cl.exe, /W4) via CMake >= 3.15, C++17.
  - **Python**: CPython 3.10 / 3.11 / 3.12; matplotlib >= 3.5, numpy >= 1.21,
    pytest >= 7, hypothesis >= 6.
- **Command** (run from repo root in a Developer PowerShell with WDK + VS 2022
  installed):

  ```powershell
  # 1. Driver  → x64\Release\InterruptLatencyMonitor.sys
  .\build_vs.bat

  # 2. Userspace daemon  → userspace\build\Release\daemon.exe
  cmake -S userspace -B userspace\build -A x64
  cmake --build userspace\build --config Release

  # 3. Python analysis + GUI
  python -m pip install -r gui\requirements.txt
  python -m pip install -r tests\requirements.txt
  ```

- **Output artifacts** (all canonical paths):
  - `x64\Release\InterruptLatencyMonitor.sys` — kernel-mode driver image
    (Spectre-mitigated, KMDF 1.15) — emitted by `build_vs.bat`. This is now
    the single canonical driver artifact path; the legacy `driver\amd64\…`
    output is gone (the `build.bat` / `driver\sources` flow was deleted in
    the 2026-05-14 fix pass).
  - `userspace\build\Release\daemon.exe` — trace-recording daemon.
  - `examples\demo_trace.silm-trace` — checked in; reproducible via
    `scripts/generate_sample_trace.py`.
  - `examples\microarch_demo.silm-trace` — checked in; reproducible via
    `scripts/generate_microarch_demo.py`.
  - `gui\*.py` — Python sources (no compile step).

### 1.2 Alternative build paths

There are **three** build entry points (post-2026-05-14 consolidation; the
legacy `build.bat` / `driver\sources` / `driver\Makefile` flow was removed).
They produce equivalent driver artifacts.

| Entry point                         | Mechanism                                                                                          | Output path                                 | Status                                                                                                                                                                            |
| ----------------------------------- | -------------------------------------------------------------------------------------------------- | ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `build_vs.bat` (root)               | Calls `vcvars64.bat` then `msbuild InterruptLatencyMonitor.sln /p:Configuration=Release /p:Platform=x64` | `x64\Release\InterruptLatencyMonitor.sys`   | **Recommended.** Hard-codes WDK 10.0.26100 and VS 2022 Community paths.                                                                                                            |
| `InterruptLatencyMonitor.sln`       | Open in Visual Studio 2022 and Build Solution (Release\|x64).                                       | `x64\Release\InterruptLatencyMonitor.sys`   | Identical result to `build_vs.bat` — useful for interactive debugging / Driver Verifier setup.                                                                                    |
| `userspace\CMakeLists.txt`          | CMake + MSVC (or MinGW; CMake handles both, but daemon uses Win32 `<windows.h>` and `DeviceIoControl`). | `userspace\build\<config>\daemon.exe`       | Mandatory for the daemon — there is no `.vcxproj` or `.bat` wrapper for it.                                                                                                       |
| `install.bat` (root)                | `sc create … type= kernel binPath= "%~dp0x64\Release\InterruptLatencyMonitor.sys"` then `sc start`. | service `InterruptLatencyMonitor` registered | **Aligned with `build_vs.bat`** as of 2026-05-14 — fails fast if the `.sys` is missing, references `build_vs.bat`, and prints the `0xC0000428` / test-signing recipe on failure. No manual `copy` step needed. |

ARM64 and Win32 (x86) configurations are declared in the `.sln` and `.vcxproj`
but no build script exercises them; treat them as untested.

### 1.3 Dependencies

- **Required**:
  - **Driver**: Windows 10 SDK + WDK matching version 10.0.26100.0
    (declared as `WindowsTargetPlatformVersion`), Visual Studio 2022 with the
    "C++ and Spectre-mitigated x64 libraries (WDK)" workload, KMDF 1.15
    headers at `C:\Program Files (x86)\Windows Kits\10\Include\wdf\kmdf\1.15`.
    Administrator + **test-signing enabled** (`bcdedit /set testsigning on`,
    reboot) or a production signature to load.
  - **Daemon**: CMake >= 3.15, MSVC (C++17), Windows SDK (for `<windows.h>`,
    `DeviceIoControl`). The daemon `#include`s `InterruptLatencyMonitor.h`
    from `userspace/`, which is now a thin shim that pulls in the shared
    ABI header `shared/InterruptLatencyMonitor_abi.h` (the single source of
    truth for `IRQ_EVENT`, `EVT_PHASE`, the four `IOCTL_*` codes and their
    in/out structs, plus an `IRQ_EVENT_ABI_VERSION` sentinel). The kernel
    side (`driver/InterruptLatencyMonitor.h`) includes the same shared
    header, so the two sides cannot drift.
  - **Python analysis**: Python >= 3.10, `matplotlib>=3.5.0`, `numpy>=1.21.0`.
  - **Python tests**: `pytest>=7.0`, `hypothesis>=6.0`, `numpy>=1.21.0`.

- **Optional**:
  - Visual Studio 2022 (interactive driver debugging, WinDbg integration).
  - A live kernel-mode debugger (WinDbg + serial or `kdnet`) — strongly
    recommended for any real driver work; the synthetic harness emits
    `KdPrint` traces.
  - A second physical machine or a Hyper-V "Generation 1" guest with VTL
    disabled, for the bare-metal validation roadmap described in
    `README.md`.
  - Driver Verifier (`verifier /standard /driver InterruptLatencyMonitor.sys`)
    for stress testing.

---

## 2. Expected behavior

### 2.1 What this project does

SILM captures interrupt-handling timestamps inside the Windows kernel and
exports them to userspace for online statistical analysis:

- The KMDF driver allocates one lock-free ring per CPU (`RING_BUFFER_SIZE =
  4096`, power-of-two mask, `InterlockedIncrement`-driven head). It records
  five event phases (`ISR_START`, `ISR_END`, `DPC_QUEUE`, `DPC_START`,
  `DPC_END`) with `KeQueryPerformanceCounter()` and gated invariant-TSC
  timestamps. In the current revision the event source is a
  `KeSetTimerEx`-driven **synthetic harness** (`StartSyntheticInterruptSource`)
  — real-ISR binding via `WdfInterruptCreate` is the documented next step.
- Userspace consumers retrieve event batches via `IOCTL_GET_EVENTS`,
  `IOCTL_GET_STATISTICS`, `IOCTL_SET_CONFIG`.
- The C++ daemon writes raw events to a `.silm-trace` binary file (header +
  packed records) for offline analysis.
- Python tooling parses the trace, pairs ISR/DPC events, computes per-CPU
  EWMA / CUSUM / p50-p95-p99 latency, runs the policy engine, and the
  `MicroarchWitness` module flags TSC/QPC-ratio deviations against a
  MAD-based robust baseline.
- The Tk/matplotlib `GUI.py` renders latency-over-time, distribution, CPU
  comparison and anomaly panels.

### 2.2 Acceptance criteria

Each component is acceptance-tested separately.

- [ ] **Driver build**: `build_vs.bat` exits 0 and emits
  `x64\Release\InterruptLatencyMonitor.sys` (>= a few hundred KB, signed
  by the test-signing cert or unsigned + test-signing mode acceptable).
- [ ] **Driver load**: After running `install.bat` from an elevated shell
  (it now reads directly from `x64\Release\InterruptLatencyMonitor.sys` — no
  manual copy needed), `sc query InterruptLatencyMonitor` reports
  `STATE: 4 RUNNING`. `KdPrint` shows
  `InterruptLatencyMonitor: DriverEntry` and `Detected N processors`.
- [ ] **Daemon build**: `cmake --build userspace\build --config Release`
  exits 0 and produces `userspace\build\Release\daemon.exe`. No /W4 warnings
  outside system headers.
- [ ] **Daemon → driver round-trip**: `daemon.exe` opens the device handle,
  enables instrumentation, drains events, and writes a non-empty
  `silm_trace_*.bin` whose header magic is `SILM`.
- [ ] **Python parser**: `python -m pytest tests/ -v` exits 0; all of
  `test_trace_parser.py`, `test_statistics_processor.py`,
  `test_policy_engine.py`, `test_microarch_witness.py` pass.
- [ ] **End-to-end reproducibility (no driver)**:
  `python scripts/generate_sample_trace.py --out examples/demo_trace.silm-trace
  --duration 0.1 --cpus 2 --spike-at 0.05` produces a byte-identical file
  to the one shipped in `examples/`.
- [ ] **Microarchitectural witness sanity**: running
  `MicroarchWitness` over `examples/microarch_demo.silm-trace` reports
  `baseline_ratio == 300.0` and `anomaly_count == 43`, exactly as quoted
  in the README.
- [ ] **GUI launch**: `python gui/GUI.py` opens a matplotlib window with the
  four panels (Statistics, Graphs, Anomaly, Recommendations,
  Configuration). With no driver attached, it should degrade gracefully —
  the trace file path should still be loadable.
- [ ] **Service teardown**: `sc stop InterruptLatencyMonitor` followed by
  `sc delete InterruptLatencyMonitor` unloads cleanly; no bugcheck, no
  leaked non-paged pool (verifiable via `!pool` in WinDbg).

### 2.3 Manual verification

```powershell
# (A) On a machine with WDK + VS 2022:
.\build_vs.bat
dir x64\Release\InterruptLatencyMonitor.sys

# (B) Build the daemon:
cmake -S userspace -B userspace\build -A x64
cmake --build userspace\build --config Release
dir userspace\build\Release\daemon.exe

# (C) Enable test signing (one-time, REBOOT REQUIRED), then install:
bcdedit /set testsigning on
:: reboot
.\install.bat                          :: reads x64\Release\InterruptLatencyMonitor.sys directly
sc query InterruptLatencyMonitor      :: expect STATE: 4 RUNNING

# (D) Record a trace, then analyse offline:
.\userspace\build\Release\daemon.exe   :: writes silm_trace_*.bin
python -m pip install -r gui\requirements.txt
python -m pip install -r tests\requirements.txt
python -m pytest tests\ -v

# (E) Reproduce the published demo result without a driver:
python scripts\generate_microarch_demo.py --out examples\microarch_demo.silm-trace `
    --duration 0.1 --cpus 2 --anomaly-at 0.05 --anomaly-duration 0.01 --anomaly-factor 0.85
python -m pytest tests\test_microarch_witness.py -v
```

### 2.4 Automated verification

- **Python tests**: `python -m pytest tests/ -v` covers four suites
  (`trace_parser`, `statistics_processor`, `policy_engine`,
  `microarch_witness`).
- **CI**: `.github/workflows/python-tests.yml` runs the pytest suite on
  Ubuntu against Python 3.10, 3.11 and 3.12 on every push. The driver and
  the C++ daemon are **not** covered by CI (they require Windows + WDK +
  test signing, which a hosted runner cannot reasonably provide).
- **No automated driver test harness exists.** Driver verification is
  manual: install on a dedicated test VM (Hyper-V Gen 1 / VMware) with a
  kernel debugger attached, run Driver Verifier, exercise the synthetic
  source, then stop/delete the service.

---

## 3. Alternatives & improvements

### 3.1 Known fragilities

1. **Hard-coded WDK + VS paths.** `build_vs.bat` literally calls
   `"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"`
   and references `Windows Kits\10\Include\10.0.26100.0`. Any other VS
   edition (Professional/Enterprise/BuildTools) or WDK SDK version breaks
   the script silently. Fix: detect via `vswhere.exe` and read the
   installed Win10 SDK version from the registry.
2. **Test-signing requirement.** The driver is unsigned in-tree. Loading it
   needs `bcdedit /set testsigning on` + reboot — a manual, machine-altering
   step that cannot be CI'd, and most evaluators will refuse it on their
   primary machine. Use a throwaway VM.
3. ~~**`install.bat` path mismatch.** It expects the `.sys` at
   `driver\InterruptLatencyMonitor.sys`, but `build_vs.bat` deposits it at
   `x64\Release\` and `build.bat` (legacy) deposits at `driver\amd64\`.
   You must `copy` it into place first. README's `## Install` section
   doesn't mention this.~~ **RESOLVED 2026-05-14**: `install.bat` now reads
   from `%~dp0x64\Release\InterruptLatencyMonitor.sys` (the canonical
   `build_vs.bat` output), fails fast with a clear message if missing, and
   prints the `0xC0000428` / test-signing recipe on `sc start` failure.
4. ~~**Two competing driver build systems.** Modern path is MSBuild via the
   `.vcxproj` (toolset `WindowsKernelModeDriver10.0`); legacy path is
   `build.exe` via `driver\sources` + `driver\Makefile`. Modern WDKs no
   longer ship `build.exe`, so `build.bat` is dead on current installs but
   still documented in `README.md` (`cd driver && build.bat`).~~
   **RESOLVED 2026-05-14**: the legacy `build.bat` (WDK 7-era
   `build -cZ -x64`) was deleted. The canonical and only supported path is
   `build_vs.bat` → `x64\Release\InterruptLatencyMonitor.sys`. README's
   build section was updated to match.
5. **Solution GUIDs are placeholders.** Both the project and solution use
   `{12345678-1234-1234-1234-123456789ABC}` / `{87654321-…}` — harmless,
   but a fingerprint of generated boilerplate.
6. **KMDF 1.15 is conservative.** Modern WDKs default to 1.31+; pinning to
   1.15 maximises compatibility but disables newer KMDF features. Not a
   bug, just a constraint.
7. ~~**No daemon ↔ driver IOCTL ABI versioning** other than a `silm_trace`
   `version=1` field. The `IRQ_EVENT` struct is shared between `driver/` and
   `userspace/` via two **separately maintained** copies of
   `InterruptLatencyMonitor.h`. Layout drift between the two copies will
   produce silent data corruption — pin them with a static assert or vendor
   a single header.~~ **RESOLVED 2026-05-14**: the two copies were
   consolidated into `shared/InterruptLatencyMonitor_abi.h` (single source
   of truth for `IRQ_EVENT`, `EVT_PHASE`, the four `IOCTL_*` codes,
   `IOCTL_GET_EVENTS_IN/OUT`, `IOCTL_STATISTICS`, `IOCTL_CONFIG`). The
   shared header carries an `IRQ_EVENT_ABI_VERSION` sentinel that must be
   bumped on any wire-format change. `driver/InterruptLatencyMonitor.h`
   (now 132 LOC, kernel-only state) and `userspace/InterruptLatencyMonitor.h`
   (now 16 LOC, thin shim) both `#include` it — layout drift between sides
   is no longer possible.
8. **Synthetic event source only.** README is explicit that this is a
   pipeline-validation harness, not a real ISR binding. Evaluators looking
   for "this works on my hardware" will get synthetic data — that is
   working as designed, but should be highlighted up front.
9. **No driver SAL / Static Driver Verifier run is automated.** WDK ships
   `sdv`, `cav`, `pfd` but they are not invoked by either build script.

### 3.2 Fallbacks

- **No WDK installed?** Skip the driver entirely. The Python analysis
  stack is self-contained — `pip install -r gui/requirements.txt -r
  tests/requirements.txt`, then run pytest. Use the checked-in
  `examples/demo_trace.silm-trace` and `examples/microarch_demo.silm-trace`
  as substrate. The published README result (`baseline_ratio=300.0`,
  `anomaly_count=43`) is reproducible from Python alone.
- **No Windows host at all?** Spin up Windows 11 23H2 Eval in a VM, install
  VS 2022 Community + WDK 10.0.26100, and follow §2.3.
- **`build_vs.bat` fails on a non-Community VS edition?** Open
  `InterruptLatencyMonitor.sln` directly in the installed VS and Build
  Solution (Release | x64) — identical artifact, no batch-file path
  assumptions.
- **Can't enable test signing?** Skip §2.3 steps (C)–(D) and run only
  the Python flow in step (E).

### 3.3 Roadmap

- **Short-term (≤1 day)**:
  - Make `build_vs.bat` discover VS and WDK via `vswhere` + registry.
  - ~~Patch `install.bat` to look in `x64\Release\` and `driver\amd64\` for
    the `.sys`, or have the build scripts copy the artifact into
    `driver\` automatically.~~ **DONE 2026-05-14** — `install.bat` reads
    `%~dp0x64\Release\InterruptLatencyMonitor.sys` directly, fails fast if
    missing.
  - ~~Consolidate `driver\InterruptLatencyMonitor.h` and
    `userspace\InterruptLatencyMonitor.h` into a single shared header, or
    add a `static_assert(sizeof(IRQ_EVENT) == N)` on both sides.~~
    **DONE 2026-05-14** — both headers now include
    `shared/InterruptLatencyMonitor_abi.h`; ABI carries an explicit
    `IRQ_EVENT_ABI_VERSION` sentinel.
  - ~~Remove or clearly archive the legacy `driver\sources` + `Makefile`
    build path (and the `build.bat` that drives it) to avoid the
    documentation mismatch.~~ **DONE 2026-05-14** — `build.bat` deleted;
    `build_vs.bat` is the canonical entry point, mirrored in README.
- **Medium-term (≤1 week)**:
  - Add Static Driver Verifier (`/sdv`) and CodeAnalysis runs to
    `build_vs.bat` and gate CI on them where possible.
  - Add a GitHub Actions Windows runner that compiles the daemon (no
    driver — the WDK toolset isn't on hosted runners by default; an
    MSBuild + cl.exe job for the daemon is feasible).
  - Replace placeholder solution GUIDs.
  - Wire the GUI's "open trace file" flow into a smoke test that loads
    `examples/demo_trace.silm-trace` headlessly and asserts the policy
    engine produces the expected recommendation set.
- **Long-term**:
  - Bind a real ISR via `WdfInterruptCreate` against a known target
    (e.g. an `e1000`-class NIC's MSI-X vector) as a reference
    integration — this is item 1 of README's own limitations list.
  - Sign the driver with an EV cert or attestation-signed package so it
    loads without `testsigning`.
  - Run the bare-metal validation matrix sketched in
    README §"Bare-metal validation roadmap" (idle baseline,
    `CLFLUSH`/`MFENCE`/TLB-shootdown stress, Hyper-V/KVM guest).
  - Cross-validate against `xperf`, ETW kernel logger, and `perf`/eBPF
    on Linux equivalents (README limitation 4).

---

## 4. Sanity check

| Check                                  | Status   | Notes                                                                                                                                                                                                                                                |
| -------------------------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| README documents build                 | PASS     | `## Build`, `## Install`, `## Tests` and `## Demo data` sections all present; commands quoted verbatim. Build section updated 2026-05-14 to the single canonical `build_vs.bat` → `install.bat` flow and references the shared ABI header. |
| Build files present                    | PASS     | `build_vs.bat`, `install.bat`, `InterruptLatencyMonitor.sln`, `driver\*.vcxproj`, `userspace\CMakeLists.txt`, `gui\requirements.txt`, `tests\requirements.txt`, `shared\InterruptLatencyMonitor_abi.h` — all present. Legacy `build.bat` / `driver\sources` / `driver\Makefile` removed 2026-05-14. |
| Build files internally consistent      | PASS     | Single canonical path: `build_vs.bat` → `x64\Release\InterruptLatencyMonitor.sys` → `install.bat` (reads `%~dp0x64\Release\…sys`). No legacy alternates, no manual `copy` step. |
| ABI consistency (driver ↔ userspace)   | PASS     | `IRQ_EVENT`, `EVT_PHASE`, the four `IOCTL_*` codes and their in/out structs live in `shared/InterruptLatencyMonitor_abi.h` (single source of truth, carries `IRQ_EVENT_ABI_VERSION` sentinel). `driver/InterruptLatencyMonitor.h` (132 LOC, kernel-only state) and `userspace/InterruptLatencyMonitor.h` (16 LOC, shim) both include it — drift is structurally impossible. |
| Source structure matches README        | PASS     | `driver/InterruptLatencyMonitor.{c,h}` (KMDF), `shared/InterruptLatencyMonitor_abi.h`, `userspace/daemon.cpp` + `CMakeLists.txt`, `gui/{GUI,trace_parser,statistics_processor,policy_engine,microarch_witness}.py`, `scripts/generate_{sample,microarch}_demo.py`, `examples/*.silm-trace`. |
| Tests exist                            | PASS     | `tests/test_trace_parser.py`, `tests/test_statistics_processor.py`, `tests/test_policy_engine.py`, `tests/test_microarch_witness.py`, plus `conftest.py`.                                                                                            |
| Test invocation documented             | PASS     | README `## Tests` quotes `python -m pytest tests/ -v` and references `.github/workflows/python-tests.yml` CI.                                                                                                                                        |
| Output artifacts named in build files  | PASS     | `build_vs.bat` echoes `x64\Release\InterruptLatencyMonitor.sys`; `install.bat` reads the same path; CMake target `daemon` emits `daemon.exe`. Trace file magic `SILM` defined in `userspace/daemon.cpp`. All names agree. |

Overall status: **PASS.** As of the 2026-05-14 fix pass the Python analysis
stack remains fully reproducible from a clean checkout on any OS; the driver
and daemon build cleanly on a properly configured WDK + VS 2022 host and
`install.bat` now installs the artifact directly out of `x64\Release\` with
no manual `copy` step. The kernel/userspace ABI is consolidated in a single
shared header with an explicit version sentinel. The driver must still be
loaded on a test-signed system (i.e. a throwaway VM), and the synthetic-
harness scope remains as documented — both are by-design constraints
appropriate for a research-phase HBO portfolio project.
