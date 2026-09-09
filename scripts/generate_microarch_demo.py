#!/usr/bin/env python3
"""Generate a .silm-trace whose TSC/QPC ratio carries a deliberate, localised
deviation — useful for exercising the microarch-witness analyser end-to-end
without privileged hardware.

The base ratio mirrors a realistic invariant-TSC system: QPC at 10 MHz,
TSC at ~3 GHz, so tsc_delta / qpc_delta ≈ 300. Inside the configured
anomaly window the per-event TSC delta is scaled by `anomaly_factor`, so
the witness sees a ratio shift of that magnitude.

Usage:
    python scripts/generate_microarch_demo.py \\
        --out examples/microarch_demo.silm-trace \\
        --duration 0.1 --cpus 2 \\
        --anomaly-at 0.05 --anomaly-duration 0.01 --anomaly-factor 0.85
"""
import argparse
import os
import random
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), 'gui'))

from trace_parser import write_header, write_record  # noqa: E402

ISR_START = 0
ISR_END = 1
DPC_START = 3
DPC_END = 4
SYNTHETIC_VECTOR = 0xFF

QPC_HZ = 10_000_000           # 10 MHz QPC
TSC_PER_QPC = 300             # ~3 GHz TSC -> 300 tsc-ticks per qpc-tick


def _emit_chain(stream, cpu, qpc, seq, isr_dur, sched_gap, dpc_dur, tsc_scale):
    """Emit a 4-event ISR/DPC chain with TSC values derived from QPC.

    `tsc_scale` lets the caller perturb the per-event TSC delta during an
    anomaly window. Values < 1.0 model a TSC that lags QPC (i.e. the system
    spent QPC time without commensurate TSC time — characteristic of e.g.
    long uninterruptible kernel paths, certain hypervisor preemptions);
    values > 1.0 model the inverse.
    """
    def tsc_for(qpc_value):
        return int(qpc_value * TSC_PER_QPC * tsc_scale)

    write_record(stream, cpu=cpu, vector=SYNTHETIC_VECTOR, event_cpu=cpu,
                 phase=ISR_START, queue_depth=0, timestamp=qpc,
                 tsc_value=tsc_for(qpc), sequence_id=seq)
    seq += 1
    qpc_isr_end = qpc + isr_dur
    write_record(stream, cpu=cpu, vector=SYNTHETIC_VECTOR, event_cpu=cpu,
                 phase=ISR_END, queue_depth=0, timestamp=qpc_isr_end,
                 tsc_value=tsc_for(qpc_isr_end), sequence_id=seq)
    seq += 1
    qpc_dpc_start = qpc_isr_end + sched_gap
    write_record(stream, cpu=cpu, vector=SYNTHETIC_VECTOR, event_cpu=cpu,
                 phase=DPC_START, queue_depth=0, timestamp=qpc_dpc_start,
                 tsc_value=tsc_for(qpc_dpc_start), sequence_id=seq)
    seq += 1
    qpc_dpc_end = qpc_dpc_start + dpc_dur
    write_record(stream, cpu=cpu, vector=SYNTHETIC_VECTOR, event_cpu=cpu,
                 phase=DPC_END, queue_depth=0, timestamp=qpc_dpc_end,
                 tsc_value=tsc_for(qpc_dpc_end), sequence_id=seq)
    return seq + 1, qpc_dpc_end


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='microarch_demo.silm-trace')
    ap.add_argument('--duration', type=float, default=0.1,
                    help='Trace duration in synthetic seconds.')
    ap.add_argument('--cpus', type=int, default=2)
    ap.add_argument('--anomaly-at', type=float, default=None,
                    help='Anomaly window start, in synthetic seconds.')
    ap.add_argument('--anomaly-duration', type=float, default=0.01,
                    help='Anomaly window length, in synthetic seconds.')
    ap.add_argument('--anomaly-factor', type=float, default=0.85,
                    help='Multiplier applied to the TSC-delta within the '
                         'anomaly window. <1 models TSC lag; >1 models lead.')
    ap.add_argument('--seed', type=int, default=0xA17EA77E)
    args = ap.parse_args()

    random.seed(args.seed)

    ms_to_ticks = QPC_HZ // 1000
    total_chains_per_cpu = int(args.duration * 1000)
    anomaly_start_ms = (int(args.anomaly_at * 1000)
                        if args.anomaly_at is not None else None)
    anomaly_end_ms = (anomaly_start_ms
                      + int(args.anomaly_duration * 1000)
                      if anomaly_start_ms is not None else None)

    seq_per_cpu = {cpu: 1 for cpu in range(args.cpus)}

    with open(args.out, 'wb') as f:
        write_header(f, qpc_frequency=QPC_HZ,
                     cpu_count=args.cpus, start_time_qpc=0)
        for chain_idx in range(total_chains_per_cpu):
            base_qpc = chain_idx * ms_to_ticks
            in_anomaly = (anomaly_start_ms is not None
                          and anomaly_start_ms <= chain_idx < anomaly_end_ms)
            tsc_scale = args.anomaly_factor if in_anomaly else 1.0
            for cpu in range(args.cpus):
                isr_dur   = max(1, int(random.gauss(10, 2)))
                sched_gap = max(1, int(random.gauss(30, 5)))
                dpc_dur   = max(1, int(random.gauss(50, 8)))
                seq_per_cpu[cpu], _ = _emit_chain(
                    f, cpu=cpu, qpc=base_qpc, seq=seq_per_cpu[cpu],
                    isr_dur=isr_dur, sched_gap=sched_gap, dpc_dur=dpc_dur,
                    tsc_scale=tsc_scale,
                )

    total_events = total_chains_per_cpu * args.cpus * 4
    print(f'wrote {args.out}: {args.duration}s × {args.cpus} CPUs, '
          f'{total_events} events, '
          f'anomaly={"yes" if anomaly_start_ms is not None else "no"}'
          + (f' (factor={args.anomaly_factor})' if anomaly_start_ms is not None else ''))


if __name__ == '__main__':
    main()
