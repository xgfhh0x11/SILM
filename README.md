# SILM — Per-CPU Interrupt Latency Monitor with Online Anomaly Detection

A kernel-mode framework for capturing per-CPU ISR/DPC event traces and surfacing
latency anomalies online via change-point detection. Built as a research substrate
for studying interrupt-timing as a defensive observable.

---

## Motivation

Interrupt latency is one of the few defensive signals that crosses the hardware
boundary into kernel-visible territory. It reflects scheduling pressure, DMA
contention, and DPC queue backlog — but in adversarial settings it also encodes
signals from co-resident workloads: SMM transitions, hypervisor preemption,
branch-predictor training by neighbouring tenants, and timer-aligned
single-stepping primitives of the kind used by SGX-Step (Van Bulck et al., 2017).

Most existing monitoring stacks (ETW, perfmon, `xperf`) aggregate at coarse
intervals. SILM is designed for per-CPU, per-event resolution with lock-free
acquisition, so that the *distribution* of latencies — not the mean — is
available to downstream analysis. Anomaly flags emerge from online change-point
detection (CUSUM, Page 1954) over an EWMA-tracked baseline.

## Design

```
                    +----------------------+      +----------------------+
                    |   Userspace Daemon   | ---> |  Python Analysis     |
                    |  (raw event recorder,|.silm |  Layer (CUSUM, EWMA, |
                    |   writes .silm-trace)| trace|   p50/p95/p99)       |
                    +----------+-----------+      +----------------------+
                               ^
                       IOCTL_GET_EVENTS
                               |
+------------------------------+------------------------------+
|                  Kernel Driver (KMDF)                       |
|                                                             |
|  +-----------+  +-----------+  ... +-----------+            |
|  | CPU0 Ring |  | CPU1 Ring |      | CPUn Ring |  per-CPU   |
|  | (lockfree)|  | (lockfree)|      | (lockfree)|  buffers   |
|  +-----------+  +-----------+      +-----------+            |
|        ^             ^                  ^                   |
|        |  ISR_START / ISR_END           |                   |
|        |  DPC_QUEUE / DPC_START / DPC_END                   |
|        |                                                    |
|  +-----+---------------------------------+                  |
|  |  Event source (synthetic harness OR   |                  |
|  |  WdfInterruptCreate-bound driver)     |                  |
|  +---------------------------------------+                  |
+-------------------------------------------------------------+
```

**Driver (KMDF):**

- Per-CPU lock-free ring buffers (`RING_BUFFER_SIZE = 4096`, power-of-two mask,
  `InterlockedIncrement` head pointer).
- Five event phases tracked: `ISR_START`, `ISR_END`, `DPC_QUEUE`, `DPC_START`,
  `DPC_END`. Each event records vector ID, CPU number, a `QueueDepth` field,
  `KeQueryPerformanceCounter()` timestamp, and an optional `RDTSC` value
  gated on invariant-TSC capability detection. **`QueueDepth` is currently
  always `0`**: `QueryDpcQueueDepth()` in the driver is an explicit stub
  (accessing the kernel's real DPC queue depth needs kernel structures that
  aren't directly exposed) and every synthetic trace generator also hardcodes
  `queue_depth=0`. Treat the field as reserved, not a measured quantity, until
  that stub is implemented.
- IOCTL surface: `IOCTL_GET_EVENTS`, `IOCTL_GET_STATISTICS`, `IOCTL_SET_CONFIG`,
  `IOCTL_RESET_BUFFERS`. **`IOCTL_GET_STATISTICS` is not implemented** — the
  kernel handler unconditionally returns `STATUS_NOT_IMPLEMENTED`; all
  statistics in this project are computed by `gui/statistics_processor.py`
  from raw `IOCTL_GET_EVENTS` output (relayed to it via the `.silm-trace`
  files the daemon records), not from a kernel-side aggregation path.

**Userspace daemon (C++):**

- Opens the driver handle, enables instrumentation via `IOCTL_SET_CONFIG`,
  and drains raw events per CPU via `IOCTL_GET_EVENTS`.
- Writes the raw event stream, unmodified, to a packed-binary `.silm-trace`
  file (header + fixed-layout records — see `userspace/daemon.cpp`).
- Does **not** pair events, compute latencies, or run EWMA/CUSUM itself —
  by design, all of that analysis (pairing `ISR_START`/`ISR_END` and
  `ISR_START`/`DPC_START`/`DPC_END` by `(vector, CPU, sequence)`, percentile and
  EWMA/CUSUM estimation) lives in the Python analysis layer below, to keep
  a single source of truth for the analytics rather than duplicating it in
  C++.

**Analysis layer (Python):**

- `statistics_processor.py` — pairs ISR/DPC events by `(vector, CPU, sequence)`,
  maintains per-CPU EWMA, CUSUM, and percentile (p50/p95/p99) estimators,
  refreshed from event batches.
- `policy_engine.py` — rule-based recommendations (high P99, CPU imbalance,
  CUSUM anomaly) with priority sorting.
- `GUI.py` — matplotlib panels for latency-over-time, distribution, CPU
  comparison, anomaly status.

## Current Implementation Status

SILM is currently a **validated pipeline with a synthetic event source**. The
driver implements:

- `StartSyntheticInterruptSource()` — a `KeSetTimerEx`-driven periodic source
  that posts paired ISR/DPC events into the per-CPU rings, used to exercise the
  end-to-end stack (kernel ring buffer → IOCTL → daemon → `.silm-trace` →
  Python analysis (CUSUM) → recommendation).

This design separates the *measurement plumbing* (which is fully implemented
and testable in isolation) from the *interrupt source* (which is pluggable).
Production deployment binds a real ISR via `WdfInterruptCreate` against a target
driver's interrupt object, an integration point left as a documented extension
rather than baked into a single hardware target.

This split is deliberate: the synthetic harness allows pipeline validation,
benchmark calibration, and CI without privileged hardware, while preserving a
clean integration point for real-target binding.

## Threat Model & Scope

SILM is an **observability tool**, not a mitigation. It explicitly does not:

- Modify kernel control flow or interrupt dispatch.
- Make security decisions on behalf of the system.
- Distinguish benign latency spikes (legitimate DPC bursts, scheduler quanta)
  from adversarial ones without an externally supplied prior.

It does:

- Produce reproducible per-CPU latency traces at event-level resolution.
- Flag change-points in the latency distribution as candidates for review.
- Expose quantitative metrics (percentiles, CPU share, and a reserved
  `QueueDepth` field — currently always `0`, see below) that other
  detection layers can consume.

The intended consumer is a forensic or research analyst, not an automated
response system.

## Side-Channel Observability

A secondary motivation is empirical: interrupt timing is a documented side
channel. SGX-Step (Van Bulck et al., SysTEX 2017) uses APIC timer interrupts
to single-step SGX enclaves; Hund et al. (S&P 2013) demonstrated KASLR breaks
via syscall/interrupt timing. SILM's per-event timestamping at ISR and DPC
boundaries, with both QPC and invariant-TSC sources, is a candidate substrate
for empirical study of such leakage observable from the OS layer without
specialized hardware.

## Synthetic sanity check: TSC/QPC ratio as a microarchitectural witness

> **This is a self-consistency / round-trip check on synthetic data, not an
> empirical hardware finding.** The demo generator
> (`scripts/generate_microarch_demo.py`) *computes* each event's `tsc_value`
> deterministically as `qpc * TSC_PER_QPC * tsc_scale` — i.e. it plants the
> exact ratio the detector below is designed to recover, then perturbs that
> ratio inside a chosen window. The detector correctly recovers its own
> planted constant (`mad == 0.0` — a degenerate/toy-data signature; real
> noisy hardware telemetry would essentially never produce `MAD == 0` over
> 400+ samples) and flags exactly the planted perturbation window. That
> demonstrates the detector's arithmetic is correct — it is a unit test of
> `MicroarchWitness`, not evidence about real timing side-channel behavior on
> hardware. No real hardware measurement has been collected yet; see
> "Bare-metal validation roadmap" below for what that would take.

The framework includes a robust per-event detector based on the dual-clock
recording: for each pair of consecutive instrumented events `i-1, i`, the
ratio

    r_i = (tsc[i] - tsc[i-1]) / (qpc[i] - qpc[i-1])

is, on a healthy invariant-TSC system, the fixed ratio of TSC frequency
to QPC frequency. Microarchitectural events that progress one clock
without progressing the other — long uninterruptible kernel paths, SMM
transitions, hypervisor preemption windows, certain voltage- or
clock-glitch outcomes — produce localised, characteristic deviations
from this constant.

The `MicroarchWitness` module in `gui/microarch_witness.py` computes
`r_i` over a trace, derives a robust baseline (median, with MAD as a
scale estimator; cf. Huber, *Robust Statistics*, 1981), and flags
ratio points that deviate by more than `threshold_mads × MAD` from
that baseline.

The shipped sample trace
`examples/microarch_demo.silm-trace` embeds a deterministic
TSC perturbation (15% deficit) inside a 10 ms window inside a 100 ms
trace, generated via `scripts/generate_microarch_demo.py`. Running the
analyser against it reproduces:

```
{
  "pair_count": 406,
  "baseline_ratio": 300.0,
  "mad": 0.0,
  "threshold_mads": 3.0,
  "anomaly_count": 43,
  "max_deviation_mads": Infinity
}
first 3 anomalies:
  t=500010 ratio=255.00 baseline=300.00 dev=inf MADs
  t=500032 ratio=255.00 baseline=300.00 dev=inf MADs
  t=500078 ratio=255.00 baseline=300.00 dev=inf MADs
```

The baseline ratio `300.0` matches the generator's `TSC_PER_QPC`
constant; the injected anomaly window begins at QPC timestamp
`500_000` (= 50 ms × 10 MHz) and all 43 flagged points fall inside it.

Reproducing the result, end-to-end:

```bash
python scripts/generate_microarch_demo.py \
    --out examples/microarch_demo.silm-trace \
    --duration 0.1 --cpus 2 \
    --anomaly-at 0.05 --anomaly-duration 0.01 --anomaly-factor 0.85
python -m pytest tests/test_microarch_witness.py -v
```

### Bare-metal validation roadmap

The simulator result above demonstrates the analyser's correctness on
a controlled, synthetic perturbation. The natural next step is to bind
SILM's event source to a real ISR via `WdfInterruptCreate`, deploy on a
dedicated bare-metal host with serial output for externally-attested
trace export, and run the analyser against traces collected under:

1. Idle baseline (control).
2. Controlled microarchitectural stress: `CLFLUSH` burst over a hot
   region, `MFENCE` storm, induced TLB shootdowns.
3. Guest-side recording inside a Hyper-V / KVM VM (probes for
   hypervisor preemption signatures in the TSC/QPC differential).

Each condition is hypothesised to leave a distinguishable signature in
the ratio time-series; the empirical question is the strength and
shape of that signature on commodity hardware. This experimental work
is out of scope for the current revision; the framework is the
substrate.

## Build

```
:: From SILM root, in an "x64 Native Tools Command Prompt for VS 2022":
build_vs.bat                       :: msbuild via WDK 10
                                   :: -> x64\Release\InterruptLatencyMonitor.sys
install.bat                        :: sc create + sc start (admin; test-signed)

cd userspace
cmake -B build && cmake --build build --config Release

cd ..\gui
pip install -r requirements.txt
```

The driver's `.sys` is produced at the canonical path
`x64\Release\InterruptLatencyMonitor.sys`; `install.bat` reads from
that location. Wire-format types shared between the driver and the
user-mode daemon live in `shared/InterruptLatencyMonitor_abi.h` —
both sides include it, so the IRQ_EVENT struct and IOCTL codes
cannot drift silently.

The project consists of three components built independently:

- `driver/` — KMDF driver (`InterruptLatencyMonitor.sys`)
- `userspace/` — C++ daemon (binary trace recorder, emits `.silm-trace`)
- `gui/` — Python analysis and visualization layer (parser, statistics,
  policy engine, Tk GUI)

## Tests

The Python analysis layer ships with a pytest suite covering the trace
parser, the statistics processor, and the policy engine:

```bash
pip install -r tests/requirements.txt
python -m pytest tests/ -v
```

Continuous integration runs the suite on every push under
`.github/workflows/python-tests.yml` (Python 3.10 / 3.11 / 3.12 on Ubuntu).

## Demo data

A small, deterministic trace is shipped at
`examples/demo_trace.silm-trace` and can be consumed without a live driver
run. Regenerate it with:

```bash
python scripts/generate_sample_trace.py \
    --out examples/demo_trace.silm-trace \
    --duration 0.1 --cpus 2 --spike-at 0.05
```

## Install

The driver requires test-signing enabled (`bcdedit /set testsigning on`) or a
production signature. Installation via `install.bat` creates a kernel-mode
service; `uninstall.bat` reverses it.

## Limitations and Roadmap

The project is research-phase. Known gaps, prioritized:

1. **Real-driver binding.** Current event source is the synthetic harness.
   A reference integration with a known driver (e.g., a NIC's MSI-X vector)
   is the next concrete step.
2. **Formal CUSUM threshold derivation.** The threshold is currently a
   heuristic constant. ROC analysis against a labelled trace dataset is
   needed to derive per-class thresholds.
3. **Public dataset.** No reproducible trace set exists for cross-system
   validation. Capturing a labelled dataset (clean baseline + injected
   anomaly classes) is part of the roadmap.
4. **Comparative evaluation.** Side-by-side measurement against `xperf`,
   ETW kernel logger, and `eBPF`/`perf` (where applicable) would situate
   SILM's overhead and resolution claims quantitatively.
5. **Side-channel characterization.** The framework supports SGX-Step-style
   interrupt-timing inspection in principle, but no end-to-end study has
   been carried out.

## References

- E. S. Page, "Continuous Inspection Schemes," *Biometrika*, vol. 41, 1954.
- J. Van Bulck, F. Piessens, R. Strackx, "SGX-Step: A Practical Attack
  Framework for Precise Enclave Execution Control," *SysTEX*, 2017.
- R. Hund, C. Willems, T. Holz, "Practical Timing Side Channel Attacks Against
  Kernel Space ASLR," *IEEE S&P*, 2013.
- Microsoft, "Kernel-Mode Driver Framework Reference,"
  `WdfInterruptCreate`, `KeQueryPerformanceCounter`.

## Status

Research / non-production. The framework is intended for measurement and
analysis on dedicated test systems. Driver signing and installation require
administrator privileges and should be carried out only on systems where this
is appropriate.

## License

MIT — see `LICENSE`.
