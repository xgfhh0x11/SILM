# Interrupt Latency Monitor — GUI Application

Python visualization layer for the SILM framework. Consumes events from the
kernel driver via the IOCTL interface and renders per-CPU latency statistics,
anomaly status, and policy recommendations.

## Modules

1. **`driver_interface.py`** — Windows driver communication
   - IOCTL wrappers
   - Event collection
   - Configuration management

2. **`statistics_processor.py`** — Statistics computation
   - Event processing and ISR/DPC pairing
   - EWMA, CUSUM, baseline tracking
   - Percentile calculation
   - Per-CPU statistics

3. **`policy_engine.py`** — Anomaly detection and recommendations
   - High latency detection
   - CPU imbalance detection
   - Anomaly flagging
   - Solution suggestions

4. **`GUI.py`** — Main application
   - Statistics panel
   - Graphs panel
   - Anomaly panel
   - Recommendations panel
   - Configuration panel

## Installation

```bash
cd gui
pip install -r requirements.txt
```

## Usage

```bash
python GUI.py
```

Administrator privileges may be required for driver access.

## GUI Panels

### Statistics Panel
- Per-CPU statistics
- Real-time latency metrics
- P50, P95, P99 percentiles
- EWMA and CUSUM values

### Graphs Panel
- Latency over time
- Latency distribution histogram
- Per-CPU comparison

### Anomaly Detection Panel
- Real-time anomaly status
- CUSUM values
- Per-CPU anomaly state

### Recommendations Panel
- Policy engine suggestions
- Priority-based sorting
- Solution options

### Configuration Panel
- Enable/disable instrumentation
- RDTSC toggle
- Sampling rate configuration

## Requirements

- Python 3.7+
- Windows (for driver interface)
- Administrator privileges (for driver access)
- matplotlib
- numpy
