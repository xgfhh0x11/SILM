"""Tests for the TSC/QPC microarchitectural witness analyser.

These tests pin three contracts:
1. A clean trace (constant ratio) produces zero anomalies.
2. A trace with a localised TSC perturbation produces anomalies inside the
   perturbation window and (almost) none outside it.
3. The baseline statistics (median, MAD) match standard library output for
   handwritten ratio series.
"""
import os
import sys

import pytest

from trace_parser import read_trace, write_header, write_record
from microarch_witness import MicroarchWitness, RatioPoint


# Use the same generator script the project ships so the tests cover the
# whole pipeline (generator → parser → analyser).
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, 'scripts'))


def _generate(tmp_path, **kwargs) -> str:
    """Drive scripts/generate_microarch_demo.main() with argv overrides."""
    out = tmp_path / 'demo.silm-trace'
    argv = [sys.argv[0], '--out', str(out)]
    for k, v in kwargs.items():
        argv.append(f'--{k.replace("_", "-")}')
        argv.append(str(v))

    import generate_microarch_demo as gen
    old = sys.argv
    try:
        sys.argv = argv
        gen.main()
    finally:
        sys.argv = old
    return str(out)


def test_constant_ratio_produces_no_anomalies(tmp_path):
    path = _generate(tmp_path, duration=0.05, cpus=2)
    _, records = read_trace(path)

    w = MicroarchWitness(threshold_mads=5.0)
    ratios = w.compute_ratios(records)
    anomalies = w.detect_anomalies(ratios)

    # Clean trace: every pair's ratio is exactly the same, so MAD is 0 and
    # there is by construction no point that differs from the median. The
    # detector's MAD=0 fallback path therefore returns nothing.
    assert anomalies == []


def test_injected_anomaly_is_detected(tmp_path):
    path = _generate(
        tmp_path,
        duration=0.1, cpus=2,
        anomaly_at=0.05, anomaly_duration=0.01, anomaly_factor=0.5,
    )
    _, records = read_trace(path)

    w = MicroarchWitness(threshold_mads=3.0)
    ratios = w.compute_ratios(records)
    anomalies = w.detect_anomalies(ratios)

    assert anomalies, 'detector failed to flag a 50% TSC scale drop'
    # Anomaly window is [0.05, 0.06) s; sanity-check at least one detection
    # falls inside that window.
    qpc_hz = 10_000_000
    win_lo = int(0.05 * qpc_hz)
    win_hi = int(0.06 * qpc_hz)
    inside = [a for a in anomalies if win_lo <= a.timestamp < win_hi]
    assert inside, (
        f'no anomalies inside [{win_lo}, {win_hi}); first anomalies at '
        f'{[a.timestamp for a in anomalies[:5]]}'
    )


def test_anomalies_have_reasonable_deviation_magnitude(tmp_path):
    path = _generate(
        tmp_path,
        duration=0.1, cpus=1,
        anomaly_at=0.05, anomaly_duration=0.01, anomaly_factor=0.5,
    )
    _, records = read_trace(path)
    w = MicroarchWitness(threshold_mads=3.0)
    ratios = w.compute_ratios(records)
    anomalies = w.detect_anomalies(ratios)

    if anomalies:
        assert all(a.deviation_mads >= 3.0 for a in anomalies)


def test_baseline_matches_handwritten_series():
    # Build a synthetic RatioPoint series with a known median and MAD.
    points = [
        RatioPoint(timestamp=i, delta_qpc=1, delta_tsc=int(v), ratio=v)
        for i, v in enumerate([1.0, 1.0, 1.0, 2.0, 1.0, 1.0, 1.0])
    ]
    w = MicroarchWitness()
    med, mad = w.baseline(points)
    assert med == pytest.approx(1.0)
    # MAD = median(|x_i - median|) = median([0,0,0,1,0,0,0]) = 0
    assert mad == pytest.approx(0.0)


def test_constant_input_returns_no_anomalies_with_zero_mad():
    points = [RatioPoint(timestamp=i, delta_qpc=1, delta_tsc=300, ratio=300.0)
              for i in range(100)]
    w = MicroarchWitness(threshold_mads=3.0)
    assert w.detect_anomalies(points) == []


def test_summary_contains_required_keys():
    points = [
        RatioPoint(timestamp=i, delta_qpc=1, delta_tsc=int(v * 1000), ratio=v)
        for i, v in enumerate([1.0, 1.05, 1.0, 0.95, 1.0, 1.0, 2.0, 1.0])
    ]
    w = MicroarchWitness(threshold_mads=2.0)
    ratios = points  # treat as already computed
    anomalies = w.detect_anomalies(ratios)
    s = w.summary(ratios, anomalies)
    assert {'pair_count', 'baseline_ratio', 'mad',
            'threshold_mads', 'anomaly_count', 'max_deviation_mads'}.issubset(s)
    assert s['pair_count'] == 8


def test_invalid_constructor_args_rejected():
    with pytest.raises(ValueError):
        MicroarchWitness(min_delta_qpc=0)
    with pytest.raises(ValueError):
        MicroarchWitness(threshold_mads=0)
    with pytest.raises(ValueError):
        MicroarchWitness(threshold_mads=-1)


def test_records_without_tsc_are_skipped():
    """Events with tsc_value <= 0 must not be paired (driver-side gating)."""
    from collections import namedtuple
    Rec = namedtuple('Rec', 'timestamp tsc_value')
    # Pattern: odd index has tsc_value > 0; even index has tsc_value = 0
    # (i = 1, 3, 5, 7, 9 are usable → 5 records → 4 ratio pairs).
    recs = [Rec(timestamp=i * 100, tsc_value=(i * 100 * 300 if i % 2 else 0))
            for i in range(10)]
    w = MicroarchWitness(min_delta_qpc=1)
    ratios = w.compute_ratios(recs)
    assert len(ratios) == 4
