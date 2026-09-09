"""Tests for the .silm-trace binary parser."""
import io
import struct

import pytest

from trace_parser import (
    MAGIC, VERSION,
    TraceFormatError,
    parse_header, iter_records, read_trace,
    write_header, write_record,
    _HEADER_FMT, _RECORD_SIZE,
)


def _make_trace_bytes(records):
    """Build a complete trace blob with header + given record tuples."""
    buf = io.BytesIO()
    write_header(buf, qpc_frequency=10_000_000, cpu_count=4, start_time_qpc=1_000_000)
    for r in records:
        write_record(buf, **r)
    return buf.getvalue()


def test_round_trip_single_record(tmp_path):
    rec = dict(
        cpu=2, vector=0xFF, event_cpu=2, phase=0,
        queue_depth=0, timestamp=12_345_678,
        tsc_value=0xDEADBEEF, sequence_id=1,
    )
    blob = _make_trace_bytes([rec])

    path = tmp_path / 'one.silm-trace'
    path.write_bytes(blob)

    header, records = read_trace(str(path))

    assert header.magic == MAGIC
    assert header.version == VERSION
    assert header.qpc_frequency == 10_000_000
    assert header.cpu_count == 4
    assert len(records) == 1

    r = records[0]
    assert r.cpu == 2
    assert r.vector == 0xFF
    assert r.event_cpu == 2
    assert r.phase == 0
    assert r.timestamp == 12_345_678
    assert r.tsc_value == 0xDEADBEEF
    assert r.sequence_id == 1


def test_round_trip_many_records():
    records = [
        dict(cpu=i % 4, vector=0xFF, event_cpu=i % 4, phase=i % 5,
             queue_depth=i, timestamp=1000 + i, tsc_value=i * 7,
             sequence_id=i + 1)
        for i in range(500)
    ]
    blob = _make_trace_bytes(records)

    stream = io.BytesIO(blob)
    parse_header(stream)
    parsed = list(iter_records(stream))

    assert len(parsed) == 500
    for i, r in enumerate(parsed):
        assert r.sequence_id == i + 1
        assert r.timestamp == 1000 + i
        assert r.cpu == i % 4


def test_bad_magic_rejected():
    blob = struct.pack(_HEADER_FMT, b'XXXX', VERSION, 0, 0, 0, 0)
    with pytest.raises(TraceFormatError, match='bad magic'):
        parse_header(io.BytesIO(blob))


def test_unsupported_version_rejected():
    blob = struct.pack(_HEADER_FMT, MAGIC, 99, 0, 0, 0, 0)
    with pytest.raises(TraceFormatError, match='unsupported version'):
        parse_header(io.BytesIO(blob))


def test_short_header_rejected():
    with pytest.raises(TraceFormatError, match='short header'):
        parse_header(io.BytesIO(b'SIL'))


def test_truncated_record_rejected():
    blob = _make_trace_bytes([
        dict(cpu=0, vector=0xFF, event_cpu=0, phase=0,
             queue_depth=0, timestamp=1, tsc_value=0, sequence_id=1)
    ])
    # Chop off the last 5 bytes of the record so it parses partially.
    truncated = blob[:-5]
    stream = io.BytesIO(truncated)
    parse_header(stream)
    with pytest.raises(TraceFormatError, match='truncated record'):
        list(iter_records(stream))


def test_as_event_dict_keys_match_processor_contract():
    rec = dict(
        cpu=1, vector=42, event_cpu=1, phase=3,
        queue_depth=5, timestamp=99_999,
        tsc_value=12345, sequence_id=7,
    )
    blob = _make_trace_bytes([rec])
    stream = io.BytesIO(blob)
    parse_header(stream)
    record = next(iter_records(stream))

    d = record.as_event_dict()
    # statistics_processor.process_events depends on exactly these keys.
    required = {'vector', 'cpu', 'phase', 'queue_depth',
                'timestamp', 'tsc_value', 'sequence_id'}
    assert required.issubset(d.keys())
    assert d['vector'] == 42
    assert d['phase'] == 3
    assert d['sequence_id'] == 7


def test_record_size_constant_matches_struct():
    # Guard against accidental layout drift between the parser and the daemon.
    # Daemon writes 4 (cpu) + 32 (IRQ_EVENT) = 36 bytes per record.
    assert _RECORD_SIZE == 36
