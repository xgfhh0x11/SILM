#!/usr/bin/env python3
"""Generate a synthetic .silm-trace file for demos, testing, and CI.

Produces a file that matches the binary format emitted by the userspace
daemon (userspace/daemon.cpp), so it can be consumed by the GUI's
trace_parser and statistics_processor without requiring a live driver run.

Usage:
    python scripts/generate_sample_trace.py [--out PATH] [--duration SECONDS]
                                            [--cpus N] [--spike-at SECONDS]
"""
import argparse
import os
import random
import sys

# Make the parser importable when running from the repo root.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), 'gui'))

from trace_parser import write_header, write_record  # noqa: E402

# Phase IDs match StatisticsProcessor.EVT_* and the driver's EVT_PHASE enum.
ISR_START = 0
ISR_END = 1
DPC_START = 3
DPC_END = 4

# Synthetic-source vector (matches SYNTHETIC_VECTOR in the driver).
SYNTHETIC_VECTOR = 0xFF


def _emit_chain(stream, cpu, ts, seq, isr_dur, sched_gap, dpc_dur):
    """Emit a 4-event ISR/DPC chain with monotonic sequence IDs."""
    write_record(stream, cpu=cpu, vector=SYNTHETIC_VECTOR, event_cpu=cpu,
                 phase=ISR_START, queue_depth=0, timestamp=ts,
                 tsc_value=0, sequence_id=seq)
    seq += 1
    ts_isr_end = ts + isr_dur
    write_record(stream, cpu=cpu, vector=SYNTHETIC_VECTOR, event_cpu=cpu,
                 phase=ISR_END, queue_depth=0, timestamp=ts_isr_end,
                 tsc_value=0, sequence_id=seq)
    seq += 1
    ts_dpc_start = ts_isr_end + sched_gap
    write_record(stream, cpu=cpu, vector=SYNTHETIC_VECTOR, event_cpu=cpu,
                 phase=DPC_START, queue_depth=0, timestamp=ts_dpc_start,
                 tsc_value=0, sequence_id=seq)
    seq += 1
    ts_dpc_end = ts_dpc_start + dpc_dur
    write_record(stream, cpu=cpu, vector=SYNTHETIC_VECTOR, event_cpu=cpu,
                 phase=DPC_END, queue_depth=0, timestamp=ts_dpc_end,
                 tsc_value=0, sequence_id=seq)
    return seq + 1, ts_dpc_end


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='sample_trace.silm-trace',
                    help='Output trace path')
    ap.add_argument('--duration', type=float, default=10.0,
                    help='Trace duration in seconds (synthetic)')
    ap.add_argument('--cpus', type=int, default=4,
                    help='Number of CPUs to simulate')
    ap.add_argument('--spike-at', type=float, default=None,
                    help='Inject a 10x latency spike starting at this second')
    ap.add_argument('--seed', type=int, default=0xC0FFEE,
                    help='RNG seed for reproducibility')
    args = ap.parse_args()

    random.seed(args.seed)

    qpc_freq = 10_000_000          # 10 MHz pretend QPC
    ticks_per_sec = qpc_freq
    ms_to_ticks = ticks_per_sec // 1000

    # Synthetic timer fires every 1 ms (matches SYNTHETIC_TIMER_INTERVAL_MS).
    total_chains_per_cpu = int(args.duration * 1000)
    spike_chain = int(args.spike_at * 1000) if args.spike_at else None

    seq_per_cpu = {cpu: 1 for cpu in range(args.cpus)}

    with open(args.out, 'wb') as f:
        write_header(f,
                     qpc_frequency=qpc_freq,
                     cpu_count=args.cpus,
                     start_time_qpc=0)

        for chain_idx in range(total_chains_per_cpu):
            base_ts = chain_idx * ms_to_ticks
            for cpu in range(args.cpus):
                # Baseline: ISR ~1us, sched gap ~3us, DPC ~5us, with noise.
                isr_dur = max(1, int(random.gauss(10, 2)))     # ticks
                sched_gap = max(1, int(random.gauss(30, 5)))
                dpc_dur = max(1, int(random.gauss(50, 8)))

                # Optional spike window: 10x latency between [spike, spike+0.1s)
                if spike_chain is not None and spike_chain <= chain_idx < spike_chain + 100:
                    dpc_dur *= 10

                seq_per_cpu[cpu], _ = _emit_chain(
                    f, cpu=cpu, ts=base_ts, seq=seq_per_cpu[cpu],
                    isr_dur=isr_dur, sched_gap=sched_gap, dpc_dur=dpc_dur,
                )

    print(f'wrote {args.out}: '
          f'{args.duration}s x {args.cpus} CPUs '
          f'({total_chains_per_cpu * args.cpus} chains, '
          f'{total_chains_per_cpu * args.cpus * 4} events)')


if __name__ == '__main__':
    main()
