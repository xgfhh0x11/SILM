"""Tests for the policy engine: recommendation triggering and ordering."""
from policy_engine import PolicyEngine, Recommendation


def _stats(p99_us=0.0, total=1000, anomaly=False, cusum=0.0):
    return {
        'p99_us': p99_us,
        'total_events': total,
        'anomaly_detected': anomaly,
        'cusum': cusum,
    }


def test_no_recommendations_on_empty_stats():
    eng = PolicyEngine()
    assert eng.analyze({}) == []


def test_no_recommendations_when_cpu_has_no_events():
    eng = PolicyEngine()
    recs = eng.analyze({0: _stats(p99_us=99999, total=0)})
    # CPU with zero events is skipped entirely.
    assert recs == []


def test_high_latency_triggers_recommendation():
    eng = PolicyEngine()
    # Default threshold is 1000.0 us.
    recs = eng.analyze({0: _stats(p99_us=2000.0, total=500)})

    types = [r.type for r in recs]
    assert 'High Latency' in types


def test_high_latency_does_not_trigger_below_threshold():
    eng = PolicyEngine()
    recs = eng.analyze({0: _stats(p99_us=999.0, total=500)})
    types = [r.type for r in recs]
    assert 'High Latency' not in types


def test_cpu_imbalance_triggers_above_50_percent():
    eng = PolicyEngine()
    # CPU0 owns 80% of events, CPU1 the rest → imbalance on CPU0.
    recs = eng.analyze({
        0: _stats(total=800),
        1: _stats(total=200),
    })
    cpu0_imbalance = [
        r for r in recs if r.type == 'CPU Imbalance' and 'CPU 0' in r.description
    ]
    assert cpu0_imbalance, f'expected CPU Imbalance for CPU 0, got {recs!r}'


def test_anomaly_flag_triggers_high_priority():
    eng = PolicyEngine()
    recs = eng.analyze({0: _stats(total=500, anomaly=True, cusum=42.0)})
    anomaly_recs = [r for r in recs if r.type == 'Anomaly Detected']
    assert anomaly_recs
    assert anomaly_recs[0].priority == 1


def test_recommendations_sorted_by_priority():
    eng = PolicyEngine()
    # Build a stats dict that generates one anomaly (prio 1) and one imbalance
    # (prio 2). The returned list must place priority-1 first.
    recs = eng.analyze({
        0: _stats(total=800, anomaly=True, cusum=10.0),
        1: _stats(total=200),
    })
    priorities = [r.priority for r in recs]
    assert priorities == sorted(priorities)


def test_solution_options_exist_for_each_recommendation_type():
    eng = PolicyEngine()
    for rec_type in ['High Latency', 'CPU Imbalance', 'Anomaly Detected']:
        options = eng.get_solution_options(rec_type)
        assert options, f'no solution options for {rec_type!r}'
        assert all(isinstance(s, str) and s for s in options)


def test_solution_options_returns_empty_for_unknown_type():
    eng = PolicyEngine()
    assert eng.get_solution_options('Made Up Type') == []
