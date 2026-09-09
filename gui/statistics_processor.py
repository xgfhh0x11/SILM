#
# Statistics Processor Module
# Processes events and computes statistics
#

import threading
from collections import defaultdict
from typing import Dict, List, Optional
import time


class StatisticsProcessor:
    """Module that processes events and computes statistics"""
    
    # Event phases
    EVT_ISR_START = 0
    EVT_ISR_END = 1
    EVT_DPC_QUEUE = 2
    EVT_DPC_START = 3
    EVT_DPC_END = 4
    
    def __init__(self, perf_frequency=10000000, warmup_seconds=30):  # Default 10 MHz, 30s warmup
        self.perf_frequency = perf_frequency
        self.warmup_seconds = warmup_seconds
        self.start_time = time.time()
        self.lock = threading.Lock()
        
        # Per-CPU statistics
        self.per_cpu_stats = defaultdict(lambda: {
            'total_events': 0,
            'lost_events': 0,
            'isr_count': 0,
            'dpc_count': 0,
            'isr_latencies': [],            # ISR_START → ISR_END
            'dpc_latencies': [],            # DPC_START → DPC_END
            'scheduling_latencies': [],     # ISR_START → DPC_START (scheduler delay)
            'end_to_end_latencies': [],     # ISR_START → DPC_END  (full chain — single source)
            'pending_isrs': {},             # (vector, cpu, seq) -> ISR start event
            'min_latency': None,
            'max_latency': None,
            'avg_latency': 0.0,
            'std_dev': 0.0,
            'p50': 0,
            'p95': 0,
            'p99': 0,
            # Scheduling latency (ISR→DPC gap) metrics
            'avg_scheduling_latency': 0.0,
            'p99_scheduling_latency': 0,
            'ewma': 0.0,
            'cusum': 0.0,
            'anomaly_detected': False,
            'last_update': time.time(),
            'last_sequence_id': 0,
            # Adaptive threshold parameters
            'baseline_avg': 0.0,
            'baseline_stddev': 0.0,
            'adaptive_threshold': 5.0,
            'threshold_k': 3.0,
            'is_warmup': True,
            'warmup_samples': [],
            'warmup_start_time': time.time()
        })
    
    def process_events(self, cpu: int, events: List[Dict]):
        """Process events and update statistics"""
        if not events:
            return
        
        with self.lock:
            stats = self.per_cpu_stats[cpu]
            last_sequence_id = stats.get('last_sequence_id', 0)
            
            for event in events:
                stats['total_events'] += 1
                
                vector = event['vector']
                phase = event['phase']
                timestamp = event['timestamp']
                sequence_id = event.get('sequence_id', 0)  # Monotonic sequence ID from the kernel
                
                # Sequence gap detection (lost events)
                if last_sequence_id > 0 and sequence_id > 0:
                    expected_seq = last_sequence_id + 1
                    if sequence_id > expected_seq:
                        # Sequence gap detected - events were lost
                        gap = sequence_id - expected_seq
                        stats['lost_events'] += gap
                
                last_sequence_id = sequence_id
                stats['last_sequence_id'] = sequence_id
                
                # Event key for pairing: use vector + CPU + sequence_id
                event_key = (vector, cpu, sequence_id)
                
                if phase == self.EVT_ISR_START:
                    stats['isr_count'] += 1
                    stats['pending_isrs'][event_key] = {
                        'timestamp': timestamp,
                        'vector': vector,
                        'sequence_id': sequence_id
                    }
                
                elif phase == self.EVT_ISR_END:
                    if event_key in stats['pending_isrs']:
                        isr_start = stats['pending_isrs'][event_key]
                        latency = timestamp - isr_start['timestamp']
                        stats['isr_latencies'].append(latency)
                        # Intentionally do NOT overwrite pending_isrs[event_key]:
                        # downstream DPC_START / DPC_END must measure relative
                        # to ISR_START to yield true end-to-end chain latency.
                
                elif phase == self.EVT_DPC_START:
                    stats['dpc_count'] += 1
                    # ISR_START → DPC_START = scheduling latency (scheduler delay)
                    # This goes to scheduling_latencies, NOT end_to_end_latencies.
                    # end_to_end is computed only at ISR_START → DPC_END.
                    best_match = None
                    best_diff = float('inf')
                    
                    for key, isr_event in stats['pending_isrs'].items():
                        key_vector, key_cpu, key_seq = key
                        if key_vector == vector and key_cpu == cpu:
                            diff = abs(sequence_id - key_seq) if sequence_id > 0 and key_seq > 0 else float('inf')
                            if diff < best_diff and diff < 1000:
                                best_diff = diff
                                best_match = key
                    
                    if best_match:
                        isr_event = stats['pending_isrs'][best_match]
                        sched_latency = timestamp - isr_event['timestamp']
                        stats['scheduling_latencies'].append(sched_latency)
                        # Stays in pending_isrs — DPC_END will still match it
                
                elif phase == self.EVT_DPC_END:
                    # ISR_START → DPC_END = true end-to-end latency (full interrupt chain)
                    # This list is the single reference source — DPC_START does not write here.
                    best_match = None
                    best_diff = float('inf')
                    
                    for key, isr_event in stats['pending_isrs'].items():
                        key_vector, key_cpu, key_seq = key
                        if key_vector == vector and key_cpu == cpu:
                            diff = abs(sequence_id - key_seq) if sequence_id > 0 and key_seq > 0 else float('inf')
                            if diff < best_diff and diff < 1000:
                                best_diff = diff
                                best_match = key
                    
                    if best_match:
                        isr_event = stats['pending_isrs'][best_match]
                        e2e_latency = timestamp - isr_event['timestamp']
                        stats['end_to_end_latencies'].append(e2e_latency)
                        del stats['pending_isrs'][best_match]  # Close the pair
            
            # Update statistics
            self._update_statistics(cpu)
    
    def _update_statistics(self, cpu: int):
        """Update statistics"""
        stats = self.per_cpu_stats[cpu]
        latencies = stats['end_to_end_latencies']
        current_time = time.time()
        elapsed_time = current_time - stats['warmup_start_time']
        
        # Check if we're still in warm-up period
        if elapsed_time < self.warmup_seconds:
            stats['is_warmup'] = True
            # Collect samples during warm-up but don't trigger anomalies
            if latencies:
                stats['warmup_samples'].extend(latencies[-100:])  # Keep last 100 samples
                # Calculate baseline from warm-up samples
                if len(stats['warmup_samples']) > 100:
                    warmup_sorted = sorted(stats['warmup_samples'])
                    stats['baseline_avg'] = sum(warmup_sorted) / len(warmup_sorted)
                    warmup_variance = sum((x - stats['baseline_avg']) ** 2 for x in warmup_sorted) / len(warmup_sorted)
                    stats['baseline_stddev'] = warmup_variance ** 0.5
        else:
            # Warm-up period ended - establish baseline if not set
            if stats['is_warmup']:
                stats['is_warmup'] = False
                if stats['warmup_samples']:
                    warmup_sorted = sorted(stats['warmup_samples'])
                    stats['baseline_avg'] = sum(warmup_sorted) / len(warmup_sorted)
                    warmup_variance = sum((x - stats['baseline_avg']) ** 2 for x in warmup_sorted) / len(warmup_sorted)
                    stats['baseline_stddev'] = warmup_variance ** 0.5
                    # Initialize EWMA with baseline
                    stats['ewma'] = stats['baseline_avg']
                stats['warmup_samples'] = []  # Clear warm-up samples
        
        if not latencies:
            return
        
        # Keep only last 10000 samples to prevent memory growth
        if len(latencies) > 10000:
            latencies = latencies[-10000:]
            stats['end_to_end_latencies'] = latencies

        # Scheduling latency metrics (ISR_START → DPC_START)
        sched_lats = stats['scheduling_latencies']
        if sched_lats:
            if len(sched_lats) > 10000:
                sched_lats = sched_lats[-10000:]
                stats['scheduling_latencies'] = sched_lats
            stats['avg_scheduling_latency'] = sum(sched_lats) / len(sched_lats)
            sched_sorted = sorted(sched_lats)
            size_s = len(sched_sorted)
            stats['p99_scheduling_latency'] = sched_sorted[size_s * 99 // 100]

        # Sort for percentiles
        sorted_latencies = sorted(latencies)
        
        # Min/Max
        stats['min_latency'] = sorted_latencies[0]
        stats['max_latency'] = sorted_latencies[-1]
        
        # Average
        stats['avg_latency'] = sum(sorted_latencies) / len(sorted_latencies)
        
        # Standard deviation
        variance = sum((x - stats['avg_latency']) ** 2 for x in sorted_latencies) / len(sorted_latencies)
        stats['std_dev'] = variance ** 0.5
        
        # Update CPU-specific baseline if we have enough samples
        # Baseline adapts slowly to system changes
        if not stats['is_warmup'] and len(sorted_latencies) > 100:
            # Update baseline using exponential moving average (slow adaptation)
            baseline_alpha = 0.01  # Very slow adaptation
            if stats['baseline_avg'] == 0.0:
                stats['baseline_avg'] = stats['avg_latency']
                stats['baseline_stddev'] = stats['std_dev']
            else:
                stats['baseline_avg'] = baseline_alpha * stats['avg_latency'] + (1 - baseline_alpha) * stats['baseline_avg']
                stats['baseline_stddev'] = baseline_alpha * stats['std_dev'] + (1 - baseline_alpha) * stats['baseline_stddev']
        
        # Percentiles
        size = len(sorted_latencies)
        stats['p50'] = sorted_latencies[size * 50 // 100] if size > 0 else 0
        stats['p95'] = sorted_latencies[size * 95 // 100] if size > 0 else 0
        stats['p99'] = sorted_latencies[size * 99 // 100] if size > 0 else 0
        
        # EWMA (Exponentially Weighted Moving Average)
        alpha = 0.1
        if stats['ewma'] == 0.0:
            stats['ewma'] = stats['avg_latency']
        else:
            stats['ewma'] = alpha * stats['avg_latency'] + (1 - alpha) * stats['ewma']
        
        # CUSUM anomaly detection with adaptive threshold
        # Use CPU-specific baseline for deviation calculation
        if stats['baseline_avg'] > 0:
            expected_value = stats['baseline_avg']  # Use baseline instead of EWMA for deviation
        else:
            expected_value = stats['ewma']  # Fallback to EWMA if baseline not set
        
        deviation = stats['avg_latency'] - expected_value
        stats['cusum'] += deviation
        if stats['cusum'] < 0:
            stats['cusum'] = 0
        
        # Adaptive threshold: k * stddev (CPU-specific)
        # Use baseline stddev if available, otherwise current stddev
        threshold_stddev = stats['baseline_stddev'] if stats['baseline_stddev'] > 0 else stats['std_dev']
        stats['adaptive_threshold'] = stats['threshold_k'] * threshold_stddev if threshold_stddev > 0 else 10000.0
        
        # Only detect anomalies after warm-up period
        if stats['is_warmup']:
            stats['anomaly_detected'] = False
        else:
            stats['anomaly_detected'] = stats['cusum'] > stats['adaptive_threshold']
        
        stats['last_update'] = current_time
    
    def get_statistics(self, cpu: int) -> Optional[Dict]:
        """Get statistics for a CPU"""
        with self.lock:
            if cpu not in self.per_cpu_stats:
                return None
            
            stats = self.per_cpu_stats[cpu].copy()
            
            # Convert to microseconds
            if stats['min_latency'] is not None:
                stats['min_latency_us'] = (stats['min_latency'] * 1000000.0) / self.perf_frequency
                stats['max_latency_us'] = (stats['max_latency'] * 1000000.0) / self.perf_frequency
                stats['avg_latency_us'] = (stats['avg_latency'] * 1000000.0) / self.perf_frequency
                stats['std_dev_us'] = (stats['std_dev'] * 1000000.0) / self.perf_frequency
                stats['p50_us'] = (stats['p50'] * 1000000.0) / self.perf_frequency
                stats['p95_us'] = (stats['p95'] * 1000000.0) / self.perf_frequency
                stats['p99_us'] = (stats['p99'] * 1000000.0) / self.perf_frequency
                stats['ewma_us'] = (stats['ewma'] * 1000000.0) / self.perf_frequency
                # Scheduling latency (ISR→DPC gap)
                stats['avg_scheduling_latency_us'] = (stats['avg_scheduling_latency'] * 1000000.0) / self.perf_frequency
                stats['p99_scheduling_latency_us'] = (stats['p99_scheduling_latency'] * 1000000.0) / self.perf_frequency
            else:
                stats['min_latency_us'] = 0.0
                stats['max_latency_us'] = 0.0
                stats['avg_latency_us'] = 0.0
                stats['std_dev_us'] = 0.0
                stats['p50_us'] = 0.0
                stats['p95_us'] = 0.0
                stats['p99_us'] = 0.0
                stats['ewma_us'] = 0.0
                stats['avg_scheduling_latency_us'] = 0.0
                stats['p99_scheduling_latency_us'] = 0.0
            
            return stats
    
    def get_all_statistics(self) -> Dict[int, Dict]:
        """Get statistics for all CPUs"""
        with self.lock:
            result = {}
            for cpu in self.per_cpu_stats.keys():
                result[cpu] = self.get_statistics(cpu)
            return result
    
    def reset(self, cpu: Optional[int] = None):
        """Reset statistics"""
        with self.lock:
            if cpu is None:
                self.per_cpu_stats.clear()
            elif cpu in self.per_cpu_stats:
                self.per_cpu_stats[cpu] = {
                    'total_events': 0,
                    'lost_events': 0,
                    'isr_count': 0,
                    'dpc_count': 0,
                    'isr_latencies': [],
                    'dpc_latencies': [],
                    'scheduling_latencies': [],
                    'end_to_end_latencies': [],
                    'pending_isrs': {},
                    'min_latency': None,
                    'max_latency': None,
                    'avg_latency': 0.0,
                    'std_dev': 0.0,
                    'p50': 0,
                    'p95': 0,
                    'p99': 0,
                    'avg_scheduling_latency': 0.0,
                    'p99_scheduling_latency': 0,
                    'ewma': 0.0,
                    'cusum': 0.0,
                    'anomaly_detected': False,
                    'last_update': time.time(),
                    'last_sequence_id': 0,
                    'baseline_avg': 0.0,
                    'baseline_stddev': 0.0,
                    'adaptive_threshold': 5.0,
                    'threshold_k': 3.0,
                    'is_warmup': True,
                    'warmup_samples': [],
                    'warmup_start_time': time.time()
                }

