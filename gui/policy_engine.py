#
# Policy Engine Module
# Anomaly detection and recommendations
#

from typing import List, Dict, Optional


class Recommendation:
    """Recommendation structure"""
    def __init__(self, rec_type: str, description: str, action: str, priority: int):
        self.type = rec_type
        self.description = description
        self.action = action
        self.priority = priority  # 1 = High, 2 = Medium, 3 = Low
    
    def __repr__(self):
        return f"{self.type}: {self.description} (Priority: {self.priority})"


class PolicyEngine:
    """Anomaly detection and recommendation engine"""
    
    def __init__(self):
        self.high_latency_threshold_us = 1000.0  # 1ms in microseconds
        self.cpu_imbalance_threshold = 50.0  # 50% of interrupts
    
    def analyze(self, all_stats: Dict[int, Dict]) -> List[Recommendation]:
        """Analyze all per-CPU statistics and produce recommendations"""
        recommendations = []
        
        if not all_stats:
            return recommendations
        
        # Calculate total events across all CPUs
        total_events = sum(stats.get('total_events', 0) for stats in all_stats.values())
        
        for cpu, stats in all_stats.items():
            if stats.get('total_events', 0) == 0:
                continue
            
            # High latency check
            p99_us = stats.get('p99_us', 0.0)
            if p99_us > self.high_latency_threshold_us:
                rec = Recommendation(
                    "High Latency",
                    f"CPU {cpu} shows high P99 latency ({p99_us:.2f} us)",
                    "Consider increasing interrupt moderation or redistributing interrupts",
                    1
                )
                recommendations.append(rec)
            
            # CPU imbalance check
            if total_events > 0:
                percentage = (100.0 * stats.get('total_events', 0)) / total_events
                if percentage > self.cpu_imbalance_threshold:
                    rec = Recommendation(
                        "CPU Imbalance",
                        f"CPU {cpu} handles {percentage:.1f}% of interrupts",
                        "Consider redistributing interrupts using IRQ affinity",
                        2
                    )
                    recommendations.append(rec)
            
            # Anomaly detection check
            if stats.get('anomaly_detected', False):
                rec = Recommendation(
                    "Anomaly Detected",
                    f"CPU {cpu} shows anomalous behavior (CUSUM: {stats.get('cusum', 0.0):.2f})",
                    "Investigate interrupt flooding or misconfiguration",
                    1
                )
                recommendations.append(rec)
        
        # Sort by priority
        recommendations.sort(key=lambda x: x.priority)
        
        return recommendations
    
    def get_solution_options(self, rec_type: str) -> List[str]:
        """Solution options for a given recommendation type"""
        solutions = {
            "High Latency": [
                "Increase interrupt moderation (NDIS)",
                "Redistribute interrupts using IRQ affinity",
                "Optimize MSI-X vector count"
            ],
            "CPU Imbalance": [
                "Adjust IRQ affinity using KeSetTargetProcessorDpc()",
                "Implement irqbalance-like dynamic redistribution"
            ],
            "Anomaly Detected": [
                "Check for interrupt flooding (DoS attack)",
                "Verify driver configuration",
                "Review system configuration for conflicts"
            ]
        }
        
        return solutions.get(rec_type, [])

