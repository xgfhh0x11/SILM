//
// Interrupt Latency Monitor Driver — kernel-side header.
//
// Wire-format types (IRQ_EVENT, IOCTL codes, IOCTL_* request/response
// structures) are defined in ../shared/InterruptLatencyMonitor_abi.h
// and shared with the user-mode app. Do not redefine them here.
//

#pragma once

// WDK headers — order matters: ntddk.h first.
#include <ntddk.h>
#include <wdm.h>
#include <wdf.h>
#include <wdfrequest.h>
#include <wdfdevice.h>
#include <wdfinterrupt.h>
#include <evntrace.h>
#include <intrin.h>

// Ensure KeQueryPerformanceFrequency is visible on every supported
// WDK build (some toolchains require the explicit prototype).
#ifndef KeQueryPerformanceFrequency
NTKERNELAPI
VOID
KeQueryPerformanceFrequency(
    _Out_ PLARGE_INTEGER Frequency
);
#endif

// Wire-format ABI shared with userspace/.
#include "../shared/InterruptLatencyMonitor_abi.h"

// =================================================================
// Driver version
// =================================================================

#define DRIVER_VERSION_MAJOR 0
#define DRIVER_VERSION_MINOR 1
#define DRIVER_VERSION_BUILD 0

// =================================================================
// Device interface
// =================================================================

DEFINE_GUID(GUID_DEVINTERFACE_InterruptLatencyMonitor,
    0x12345678, 0x1234, 0x1234, 0x12, 0x34, 0x12, 0x34, 0x12, 0x34, 0x12, 0x34);

// =================================================================
// Per-CPU ring buffer — kernel-only state, not part of the wire ABI.
// =================================================================

#define RING_BUFFER_SIZE 4096
#define RING_BUFFER_MASK (RING_BUFFER_SIZE - 1)

typedef struct _PERCPU_RING {
    volatile LONG   Head;             // Atomic head pointer
    volatile LONG   Tail;             // Atomic tail (reader tracking)
    ULONG           Mask;             // Size mask for modulo
    IRQ_EVENT       Buffer[RING_BUFFER_SIZE];
    ULONG64         LostEvents;       // Counter for lost events
    ULONG64         SequenceCounter;  // Monotonic sequence counter
    LARGE_INTEGER   Frequency;        // Performance counter frequency
} PERCPU_RING, *PPERCPU_RING;

#define CTL_CODE_FUNCTION(x) ((x) & 0x3FF)

// =================================================================
// TSC state
// =================================================================

typedef struct _TSC_STATE {
    BOOLEAN     IsInvariant;
    BOOLEAN     IsInitialized;
    ULONG64     TscFrequency;
} TSC_STATE, *PTSC_STATE;

// =================================================================
// Synthetic interrupt source — KeSetTimerEx-based.
// In the absence of a real hardware interrupt, a periodic timer DPC
// simulates the ISR/DPC chain and writes events into the ring buffer.
// =================================================================

#define SYNTHETIC_TIMER_INTERVAL_MS     1       // 1 ms period (1000 Hz)
#define SYNTHETIC_VECTOR                0xFF    // Reserved synthetic vector

typedef struct _SYNTHETIC_INTERRUPT_STATE {
    KTIMER          Timer;
    KDPC            TimerDpc;         // Triggered by the timer
    KDPC            WorkDpc;          // Queued from the "ISR"
    BOOLEAN         Active;
    LARGE_INTEGER   LastFired;
    ULONG64         FireCount;
} SYNTHETIC_INTERRUPT_STATE, *PSYNTHETIC_INTERRUPT_STATE;

// Helper macros
#define GetPerCpuRing(cpu) ((PPERCPU_RING)((PUCHAR)g_PerCpuRings + (cpu) * sizeof(PERCPU_RING)))

// =================================================================
// Forward declarations
// =================================================================

NTSTATUS DriverEntry(_In_ PDRIVER_OBJECT DriverObject, _In_ PUNICODE_STRING RegistryPath);
EVT_WDF_DRIVER_DEVICE_ADD EvtDeviceAdd;
EVT_WDF_DEVICE_FILE_CREATE EvtDeviceFileCreate;
EVT_WDF_FILE_CLOSE EvtDeviceFileClose;
EVT_WDF_IO_QUEUE_IO_DEVICE_CONTROL EvtIoDeviceControl;
EVT_WDF_INTERRUPT_ISR EvtInterruptIsr;
EVT_WDF_INTERRUPT_DPC EvtInterruptDpc;

KDEFERRED_ROUTINE SyntheticTimerDpc;  // Timer DPC — simulates the "ISR"
KDEFERRED_ROUTINE SyntheticWorkDpc;   // Work DPC — simulates the "DPC"

// =================================================================
// Globals (extern)
// =================================================================

extern PPERCPU_RING                  g_PerCpuRings;
extern ULONG                         g_ProcessorCount;
extern BOOLEAN                       g_InstrumentationEnabled;
extern IOCTL_CONFIG                  g_Config;
extern TSC_STATE                     g_TscState;
extern SYNTHETIC_INTERRUPT_STATE     g_SyntheticState;

// =================================================================
// Utilities
// =================================================================

__forceinline VOID WriteEvent(_In_ PIRQ_EVENT Event, _In_ ULONG Cpu);
ULONG QueryDpcQueueDepth(VOID);
BOOLEAN IsInvariantTsc(VOID);
ULONG64 ReadTsc(VOID);
VOID InitializeTscState(VOID);
BOOLEAN ShouldUseTscInIsr(VOID);
NTSTATUS StartSyntheticInterruptSource(VOID);
VOID StopSyntheticInterruptSource(VOID);
