# Demo trace

`demo_trace.silm-trace` is a small, regenerable sample of the binary trace
format produced by the userspace daemon (`userspace/daemon.cpp`). It allows
the Python analysis stack — `gui/trace_parser.py`, `gui/statistics_processor.py`,
`gui/policy_engine.py` — to be exercised end-to-end without a live driver
or signed environment.

## What's in it

- 0.1 seconds of synthetic ISR/DPC chains
- 2 simulated CPUs
- 200 chains × 4 phase events = **800 events**
- A 10× latency spike injected at t = 0.05 s to exercise CUSUM anomaly logic

## Reproducing it

```bash
python scripts/generate_sample_trace.py \
    --out examples/demo_trace.silm-trace \
    --duration 0.1 --cpus 2 --spike-at 0.05
```

The generator is deterministic (`--seed` defaults to a constant); identical
arguments produce a byte-identical trace.

## Consuming it from Python

```python
from gui.trace_parser import read_trace
from gui.statistics_processor import StatisticsProcessor

header, records = read_trace('examples/demo_trace.silm-trace')
proc = StatisticsProcessor(perf_frequency=header.qpc_frequency,
                           warmup_seconds=0)
for r in records:
    proc.process_events(r.cpu, [r.as_event_dict()])

print(proc.get_all_statistics())
```
