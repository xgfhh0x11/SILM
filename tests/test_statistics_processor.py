"""Tests for the per-CPU statistics processor.

These tests pin the contract the rest of the GUI relies on:
ISR/DPC event pairing, percentile correctness, EWMA/CUSUM behaviour,
warmup gating, and lost-event detection from sequence gaps.
"""
import numpy as np
import pytest

from statistics_processor import StatisticsProcessor


# Phase constants mirror StatisticsProcessor's EVT_* enum.
ISR_START = 0
ISR_END = 1
DPC_QUEUE = 2
DPC_START = 3
DPC_END = 4


def _event(phase, timestamp, sequence_id, vector=0xFF):
    return {
        'vector': vector,
        'cpu': 0,
        'phase': phase,
        'queue_depth': 0,
        'timestamp': timestamp,
        'tsc_value': 0,
        'sequence_id': sequence_id,
    }


def _full_chain(start_ts, sequence_id, isr_dur=10, sched_gap=20, dpc_dur=30):
    """Emit one ISR/DPC chain occupying 4 events with matching sequence_id."""
    t = start_ts
    yield _event(ISR_START, t, sequence_id);                    t += isr_dur
    yield _event(ISR_END, t, sequence_id);                      t += sched_gap
    yield _event(DPC_START, t, sequence_id);                    t += dpc_dur
    yield _event(DPC_END, t, sequence_id)


def _fresh(warmup=0):
    """Return a processor with warmup disabled by default so anomaly logic
    is exercised immediately."""
    return StatisticsProcessor(perf_frequency=10_000_000, warmup_seconds=warmup)


def test_empty_events_does_not_crash():
    proc = _fresh()
    proc.process_events(0, [])
    assert proc.get_statistics(0) is None  # CPU never recorded


def test_isr_pair_recorded():
    proc = _fresh()
    events = list(_full_chain(start_ts=1000, sequence_id=1))
    proc.process_events(0, events)
    stats = proc.get_statistics(0)

    assert stats['isr_count'] == 1
    assert stats['dpc_count'] == 1
    # End-to-end = ISR_START → DPC_END
    assert stats['min_latency'] == 10 + 20 + 30
    assert stats['max_latency'] == 10 + 20 + 30


def test_percentiles_match_numpy():
    """Feed N chains with controlled increasing latencies, confirm p50/p95/p99
    match numpy.percentile to integer index."""
    proc = _fresh()
    latencies_expected = []
    seq = 0
    ts = 0
    for i in range(100):
        seq += 1
        # End-to-end latency = isr_dur + sched_gap + dpc_dur
        e2e = 100 + i  # 100..199
        latencies_expected.append(e2e)
        # split: isr_dur=10, sched_gap=20, dpc_dur=e2e-30
        for ev in _full_chain(ts, seq, isr_dur=10, sched_gap=20, dpc_dur=e2e - 30):
            proc.process_events(0, [ev])
        ts += 1000  # large gap between chains

    stats = proc.get_statistics(0)
    sorted_lat = sorted(latencies_expected)
    # statistics_processor uses index = size * p // 100 (floor), not interpolated.
    assert stats['p50'] == sorted_lat[len(sorted_lat) * 50 // 100]
    assert stats['p95'] == sorted_lat[len(sorted_lat) * 95 // 100]
    assert stats['p99'] == sorted_lat[len(sorted_lat) * 99 // 100]
    # Monotonic relation that must hold for any distribution.
    assert stats['p50'] <= stats['p95'] <= stats['p99']


def test_ewma_converges_to_constant_input():
    """If every batch reports the same average latency, EWMA must converge."""
    proc = _fresh()
    const_e2e = 500
    for i in range(50):
        for ev in _full_chain(start_ts=i * 1000, sequence_id=i + 1,
                              isr_dur=10, sched_gap=20, dpc_dur=const_e2e - 30):
            proc.process_events(0, [ev])

    stats = proc.get_statistics(0)
    # alpha=0.1; after 50 batches with constant input, EWMA should be ~within 0.5%.
    assert abs(stats['ewma'] - const_e2e) < const_e2e * 0.005


def test_warmup_suppresses_anomaly():
    """During warmup, even a wild spike must not set anomaly_detected."""
    proc = StatisticsProcessor(perf_frequency=10_000_000, warmup_seconds=999)
    seq = 0
    for spike in [100] * 20 + [100_000] * 20:
        seq += 1
        for ev in _full_chain(seq * 1000, seq, isr_dur=10, sched_gap=20,
                              dpc_dur=max(1, spike - 30)):
            proc.process_events(0, [ev])

    stats = proc.get_statistics(0)
    assert stats['is_warmup'] is True
    assert stats['anomaly_detected'] is False


def test_lost_event_detected_from_sequence_gap():
    """Sequence ID jump should be reflected in lost_events counter."""
    proc = _fresh()
    proc.process_events(0, [_event(ISR_START, 100, sequence_id=1)])
    # Skip seq 2, 3, 4 (3 lost events).
    proc.process_events(0, [_event(ISR_START, 200, sequence_id=5)])

    stats = proc.get_statistics(0)
    assert stats['lost_events'] == 3


def test_reset_clears_per_cpu_state():
    proc = _fresh()
    for ev in _full_chain(start_ts=1000, sequence_id=1):
        proc.process_events(0, [ev])
    assert proc.get_statistics(0) is not None

    proc.reset(cpu=0)
    stats = proc.get_statistics(0)
    assert stats['total_events'] == 0
    assert stats['isr_count'] == 0
    assert stats['dpc_count'] == 0


def test_unit_conversion_to_microseconds():
    """*_us fields should equal (raw * 1e6) / perf_frequency."""
    proc = StatisticsProcessor(perf_frequency=10_000_000, warmup_seconds=0)
    # End-to-end = 60 QPC ticks; freq = 10MHz → 6.0 us
    for ev in _full_chain(start_ts=0, sequence_id=1,
                          isr_dur=10, sched_gap=20, dpc_dur=30):
        proc.process_events(0, [ev])

    stats = proc.get_statistics(0)
    expected_us = 60 * 1_000_000.0 / 10_000_000
    assert stats['avg_latency_us'] == pytest.approx(expected_us)
    assert stats['min_latency_us'] == pytest.approx(expected_us)
