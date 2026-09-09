//
// Single source of truth for the wire-format types and IOCTL surface
// shared between the kernel driver (driver/) and the user-mode app
// (userspace/). Both sides include this header — never define IRQ_EVENT
// or IOCTL_* locally.
//
// Includer prerequisites:
//   - Kernel side  : #include <ntddk.h>  before this header.
//   - User side    : #include <windows.h> #include <winioctl.h>  before
//                    this header.
// These supply CTL_CODE, FILE_DEVICE_UNKNOWN, METHOD_BUFFERED,
// FILE_ANY_ACCESS, USHORT / UCHAR / ULONG / ULONG64 / BOOLEAN /
// LONGLONG / LARGE_INTEGER.
//
// If you change a wire-format struct in this file (insertion,
// re-ordering, size change), bump IRQ_EVENT_ABI_VERSION below so the
// drift is observable at runtime instead of silently corrupting
// traces.
//

#pragma once

#ifndef IRQ_LATENCY_MONITOR_ABI_H
#define IRQ_LATENCY_MONITOR_ABI_H

// =================================================================
// Event phases
// =================================================================
// Order matters for downstream analysis tooling — do not renumber.

typedef enum _EVT_PHASE {
    EVT_ISR_START = 0,
    EVT_ISR_END,
    EVT_DPC_QUEUE,
    EVT_DPC_START,
    EVT_DPC_END
} EVT_PHASE, *PEVT_PHASE;

// =================================================================
// IRQ_EVENT — wire-format record written by the driver, read by the
// user-mode app via IOCTL_GET_EVENTS.
// =================================================================

typedef struct _IRQ_EVENT {
    USHORT          Vector;           // Interrupt vector / MessageID
    UCHAR           Cpu;              // CPU number
    UCHAR           Phase;            // EVT_PHASE value (kept as UCHAR for packing)
    ULONG           QueueDepth;       // DPC queue depth at event time
    LARGE_INTEGER   Timestamp;        // KeQueryPerformanceCounter() value
    ULONG64         TscValue;         // RDTSC value (when invariant TSC available)
    ULONG64         SequenceId;       // Monotonic counter for lost-event detection
} IRQ_EVENT, *PIRQ_EVENT;

#define IRQ_EVENT_ABI_VERSION 1u

// =================================================================
// IOCTL surface
// =================================================================

#define IOCTL_BASE 0x8000u

#define IOCTL_GET_EVENTS \
    CTL_CODE(FILE_DEVICE_UNKNOWN, IOCTL_BASE + 0x01, METHOD_BUFFERED, FILE_ANY_ACCESS)

#define IOCTL_GET_STATISTICS \
    CTL_CODE(FILE_DEVICE_UNKNOWN, IOCTL_BASE + 0x02, METHOD_BUFFERED, FILE_ANY_ACCESS)

#define IOCTL_RESET_BUFFERS \
    CTL_CODE(FILE_DEVICE_UNKNOWN, IOCTL_BASE + 0x03, METHOD_BUFFERED, FILE_ANY_ACCESS)

#define IOCTL_SET_CONFIG \
    CTL_CODE(FILE_DEVICE_UNKNOWN, IOCTL_BASE + 0x04, METHOD_BUFFERED, FILE_ANY_ACCESS)

// IOCTL request / response structures.

typedef struct _IOCTL_GET_EVENTS_IN {
    ULONG   CpuNumber;
    ULONG   MaxEvents;
    ULONG   StartIndex;
} IOCTL_GET_EVENTS_IN, *PIOCTL_GET_EVENTS_IN;

typedef struct _IOCTL_GET_EVENTS_OUT {
    ULONG       EventCount;
    IRQ_EVENT   Events[1];            // Variable length; size from caller
} IOCTL_GET_EVENTS_OUT, *PIOCTL_GET_EVENTS_OUT;

typedef struct _IOCTL_STATISTICS {
    ULONG       CpuNumber;
    ULONG64     TotalEvents;
    ULONG64     LostEvents;
    LONGLONG    MinLatency;           // ISR -> DPC latency in QPC ticks
    LONGLONG    MaxLatency;
    LONGLONG    AvgLatency;
    LONGLONG    P95Latency;
    LONGLONG    P99Latency;
    ULONG64     IsrCount;
    ULONG64     DpcCount;
} IOCTL_STATISTICS, *PIOCTL_STATISTICS;

typedef struct _IOCTL_CONFIG {
    BOOLEAN     EnableInstrumentation;
    BOOLEAN     UseRdtsc;
    ULONG       SamplingRate;         // 1 = every event; N = every Nth event
} IOCTL_CONFIG, *PIOCTL_CONFIG;

#endif /* IRQ_LATENCY_MONITOR_ABI_H */
