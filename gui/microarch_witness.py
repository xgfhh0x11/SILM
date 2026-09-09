#
# Microarchitectural Witness Module
#
# Treats the ratio of RDTSC-deltas to QPC-deltas across consecutive
# instrumented events as a microarchitectural witness signal:
#
#     r_i = (tsc[i] - tsc[i-1]) / (qpc[i] - qpc[i-1])
#
# On a healthy invariant-TSC system with a stable QPC source, r_i is
# (approximately) the constant ratio of the TSC frequency to the QPC
# frequency. Microarchitectural events that delay one clock relative
# to the other — long-running uninterruptible kernel operations,
# SMM transitions, hypervisor preemption, certain fault-injection
# patterns — produce localised deviations.
#
# This module computes the per-event ratio, derives a robust baseline
# (median / MAD), and flags windows whose ratio deviates by more than
# `threshold_mads` MADs from the baseline.
#
# Reference for MAD as a robust scale estimator:
#   Huber, P. J., *Robust Statistics*, Wiley, 1981.
#

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Iterable, List, Sequence


@dataclass(frozen=True)
class RatioPoint:
    timestamp: int       # QPC tick at the second event of the pair
    delta_qpc: int       # qpc[i] - qpc[i-1]
    delta_tsc: int       # tsc[i] - tsc[i-1]
    ratio: float         # delta_tsc / delta_qpc


@dataclass(frozen=True)
class AnomalyPoint:
    timestamp: int
    ratio: float
    baseline_ratio: float
    deviation_mads: float


class MicroarchWitness:
    """Analyse per-event TSC/QPC ratio deltas and surface deviation windows."""

    def __init__(self, min_delta_qpc: int = 10, threshold_mads: float = 5.0):
        """Args:
            min_delta_qpc: Drop pairs whose QPC delta is below this; very short
                gaps amplify quantisation noise into spurious ratio variance.
            threshold_mads: How many median absolute deviations from the baseline
                ratio counts as an anomaly. The default of 5 is conservative; for
                an approximately-normal distribution this corresponds to ≈ 7.4
                standard deviations, since stdev ≈ 1.4826 × MAD.
        """
        if min_delta_qpc < 1:
            raise ValueError('min_delta_qpc must be >= 1')
        if threshold_mads <= 0:
            raise ValueError('threshold_mads must be > 0')
        self.min_delta_qpc = min_delta_qpc
        self.threshold_mads = threshold_mads

    @staticmethod
    def _records_to_pairs(records) -> List[tuple]:
        """Return [(qpc, tsc), ...] for records where both are usable."""
        out: List[tuple] = []
        for r in records:
            qpc = getattr(r, 'timestamp', None)
            tsc = getattr(r, 'tsc_value', None)
            if qpc is None or tsc is None:
                continue
            if tsc <= 0:
                # tsc_value = 0 means "not recorded" (driver-side gating).
                continue
            out.append((qpc, tsc))
        out.sort(key=lambda p: p[0])
        return out

    def compute_ratios(self, records: Iterable) -> List[RatioPoint]:
        """Walk pairs of consecutive valid events and compute the ratio."""
        pairs = self._records_to_pairs(records)
        ratios: List[RatioPoint] = []
        for i in range(1, len(pairs)):
            q0, t0 = pairs[i - 1]
            q1, t1 = pairs[i]
            dq = q1 - q0
            dt = t1 - t0
            if dq < self.min_delta_qpc:
                continue
            if dt <= 0:
                # Non-monotonic TSC would indicate either a non-invariant TSC
                # or a frequency-scaling event; either way the ratio is not
                # well-defined here, so skip.
                continue
            ratios.append(RatioPoint(
                timestamp=q1, delta_qpc=dq, delta_tsc=dt, ratio=dt / dq,
            ))
        return ratios

    @staticmethod
    def baseline(ratios: Sequence[RatioPoint]) -> tuple[float, float]:
        """Return (median ratio, median absolute deviation) over a series."""
        if not ratios:
            return 0.0, 0.0
        values = [p.ratio for p in ratios]
        med = statistics.median(values)
        mad = statistics.median([abs(v - med) for v in values])
        return med, mad

    def detect_anomalies(self, ratios: Sequence[RatioPoint]) -> List[AnomalyPoint]:
        """Flag ratios that deviate by more than threshold_mads × MAD from the
        median. MAD = 0 is a degenerate case: if the majority of the input is
        literally constant, MAD-based scaling cannot distinguish small
        outliers from large ones. In that case fall back to "any point not
        equal to the median is anomalous" — by construction these points
        must come from a regime change relative to the constant majority.
        """
        med, mad = self.baseline(ratios)

        if mad == 0.0:
            return [
                AnomalyPoint(
                    timestamp=p.timestamp,
                    ratio=p.ratio,
                    baseline_ratio=med,
                    deviation_mads=float('inf'),
                )
                for p in ratios if p.ratio != med
            ]

        cutoff = self.threshold_mads * mad
        anomalies: List[AnomalyPoint] = []
        for p in ratios:
            dev = abs(p.ratio - med)
            if dev > cutoff:
                anomalies.append(AnomalyPoint(
                    timestamp=p.timestamp,
                    ratio=p.ratio,
                    baseline_ratio=med,
                    deviation_mads=dev / mad,
                ))
        return anomalies

    def summary(self, ratios: Sequence[RatioPoint],
                anomalies: Sequence[AnomalyPoint]) -> dict:
        """Compact dict summary suitable for JSON serialisation."""
        med, mad = self.baseline(ratios)
        return {
            'pair_count': len(ratios),
            'baseline_ratio': med,
            'mad': mad,
            'threshold_mads': self.threshold_mads,
            'anomaly_count': len(anomalies),
            'max_deviation_mads': max((a.deviation_mads for a in anomalies),
                                      default=0.0),
        }
