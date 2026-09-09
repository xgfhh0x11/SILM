#
# Trace Parser Module
# Reads .silm-trace binary files produced by the userspace daemon and exposes
# events as plain dictionaries compatible with the rest of the GUI pipeline.
#
# Binary format (little-endian, see userspace/daemon.cpp):
#
#   silm_trace_header (32 bytes):
#       char     magic[4]           # 'S','I','L','M'
#       uint32_t version            # currently 1
#       uint64_t qpc_frequency      # QueryPerformanceFrequency value
#       uint32_t cpu_count          # number of CPUs being recorded
#       uint32_t reserved           # 0
#       uint64_t start_time_qpc     # QPC counter at recording start
#
#   silm_trace_record (36 bytes), repeated until EOF:
#       uint32_t cpu                # source CPU
#       IRQ_EVENT event             # 32 bytes
#
#   IRQ_EVENT (32 bytes, packed):
#       uint16_t Vector
#       uint8_t  Cpu                # producer-side CPU (matches outer cpu)
#       uint8_t  Phase              # 0=ISR_START, 1=ISR_END, 2=DPC_QUEUE,
#                                   # 3=DPC_START, 4=DPC_END
#       uint32_t QueueDepth
#       int64_t  Timestamp          # KeQueryPerformanceCounter() value
#       uint64_t TscValue
#       uint64_t SequenceId
#

import struct
from dataclasses import dataclass
from typing import Iterable, List, Optional


MAGIC = b'SILM'
VERSION = 1

# struct format strings (little-endian)
_HEADER_FMT = '<4sIQIIQ'
_HEADER_SIZE = struct.calcsize(_HEADER_FMT)  # 32

_EVENT_FMT = '<HBBIqQQ'
_EVENT_SIZE = struct.calcsize(_EVENT_FMT)  # 32

_RECORD_FMT = '<I' + _EVENT_FMT[1:]
_RECORD_SIZE = struct.calcsize(_RECORD_FMT)  # 36


class TraceFormatError(ValueError):
    """Raised when a file does not match the .silm-trace binary format."""


@dataclass
class TraceHeader:
    magic: bytes
    version: int
    qpc_frequency: int
    cpu_count: int
    reserved: int
    start_time_qpc: int


@dataclass
class TraceRecord:
    cpu: int
    vector: int
    event_cpu: int
    phase: int
    queue_depth: int
    timestamp: int
    tsc_value: int
    sequence_id: int

    def as_event_dict(self) -> dict:
        """Return a dict compatible with statistics_processor.process_events()."""
        return {
            'vector': self.vector,
            'cpu': self.event_cpu,
            'phase': self.phase,
            'queue_depth': self.queue_depth,
            'timestamp': self.timestamp,
            'tsc_value': self.tsc_value,
            'sequence_id': self.sequence_id,
        }


def parse_header(stream) -> TraceHeader:
    raw = stream.read(_HEADER_SIZE)
    if len(raw) != _HEADER_SIZE:
        raise TraceFormatError(f'short header: expected {_HEADER_SIZE} bytes, got {len(raw)}')

    magic, version, qpc_freq, cpu_count, reserved, start_qpc = struct.unpack(_HEADER_FMT, raw)
    if magic != MAGIC:
        raise TraceFormatError(f'bad magic: {magic!r} (expected {MAGIC!r})')
    if version != VERSION:
        raise TraceFormatError(f'unsupported version: {version}')

    return TraceHeader(
        magic=magic,
        version=version,
        qpc_frequency=qpc_freq,
        cpu_count=cpu_count,
        reserved=reserved,
        start_time_qpc=start_qpc,
    )


def iter_records(stream) -> Iterable[TraceRecord]:
    """Yield TraceRecord objects from an already-headered stream."""
    while True:
        raw = stream.read(_RECORD_SIZE)
        if not raw:
            return
        if len(raw) != _RECORD_SIZE:
            raise TraceFormatError(
                f'truncated record: expected {_RECORD_SIZE} bytes, got {len(raw)}'
            )
        cpu, vector, event_cpu, phase, queue_depth, timestamp, tsc, seq = (
            struct.unpack(_RECORD_FMT, raw)
        )
        yield TraceRecord(
            cpu=cpu,
            vector=vector,
            event_cpu=event_cpu,
            phase=phase,
            queue_depth=queue_depth,
            timestamp=timestamp,
            tsc_value=tsc,
            sequence_id=seq,
        )


def read_trace(path: str) -> tuple[TraceHeader, List[TraceRecord]]:
    """Read an entire trace file. For large traces, prefer iter_records()."""
    with open(path, 'rb') as f:
        header = parse_header(f)
        records = list(iter_records(f))
    return header, records


# Writer helpers — used by tests and by the sample-trace generator.

def write_header(stream, qpc_frequency: int, cpu_count: int, start_time_qpc: int) -> None:
    stream.write(struct.pack(
        _HEADER_FMT,
        MAGIC, VERSION, qpc_frequency, cpu_count, 0, start_time_qpc,
    ))


def write_record(
    stream,
    cpu: int,
    vector: int,
    event_cpu: int,
    phase: int,
    queue_depth: int,
    timestamp: int,
    tsc_value: int,
    sequence_id: int,
) -> None:
    stream.write(struct.pack(
        _RECORD_FMT,
        cpu, vector, event_cpu, phase, queue_depth, timestamp, tsc_value, sequence_id,
    ))
