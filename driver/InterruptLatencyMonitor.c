//
// Interrupt Latency Monitor Driver
// Main driver implementation
//

// Force include WDK headers first
#include <ntddk.h>
#include <wdm.h>
#include "InterruptLatencyMonitor.h"
#include <intrin.h>

// Global variables
PPERCPU_RING g_PerCpuRings = NULL;
ULONG g_ProcessorCount = 0;
BOOLEAN g_InstrumentationEnabled = TRUE;
IOCTL_CONFIG g_Config = { TRUE, FALSE, 1 };
TSC_STATE g_TscState = { FALSE, FALSE, 0 };
SYNTHETIC_INTERRUPT_STATE g_SyntheticState = { 0 };

// Forward declarations
NTSTATUS InitializePerCpuBuffers(VOID);
VOID CleanupPerCpuBuffers(VOID);
NTSTATUS CreateInterruptObject(_In_ WDFDEVICE Device);

//
// Driver Entry Point
//
NTSTATUS DriverEntry(
    _In_ PDRIVER_OBJECT DriverObject,
    _In_ PUNICODE_STRING RegistryPath
)
{
    WDF_DRIVER_CONFIG config;
    NTSTATUS status;
    WDFDRIVER driver;

    UNREFERENCED_PARAMETER(RegistryPath);

    KdPrint(("InterruptLatencyMonitor: DriverEntry\n"));

    WDF_DRIVER_CONFIG_INIT(&config, EvtDeviceAdd);
    config.EvtDriverUnload = NULL; // KMDF handles cleanup

    status = WdfDriverCreate(DriverObject, RegistryPath, WDF_NO_OBJECT_ATTRIBUTES, &config, &driver);
    if (!NT_SUCCESS(status)) {
        KdPrint(("InterruptLatencyMonitor: WdfDriverCreate failed: 0x%08X\n", status));
        return status;
    }

    // Get processor count
    g_ProcessorCount = KeQueryActiveProcessorCountEx(ALL_PROCESSOR_GROUPS);
    KdPrint(("InterruptLatencyMonitor: Detected %lu processors\n", g_ProcessorCount));

    // Initialize per-CPU buffers
    status = InitializePerCpuBuffers();
    if (!NT_SUCCESS(status)) {
        KdPrint(("InterruptLatencyMonitor: InitializePerCpuBuffers failed: 0x%08X\n", status));
        return status;
    }

    return STATUS_SUCCESS;
}

//
// Initialize per-CPU ring buffers
//
NTSTATUS InitializePerCpuBuffers(VOID)
{
    NTSTATUS status;
    SIZE_T totalSize;
    ULONG i;

    totalSize = g_ProcessorCount * sizeof(PERCPU_RING);
    
    g_PerCpuRings = (PPERCPU_RING)ExAllocatePoolWithTag(
        NonPagedPoolNx,
        totalSize,
        'ILMR'  // Tag: "ILMR" = Interrupt Latency Monitor Ring
    );

    if (g_PerCpuRings == NULL) {
        return STATUS_INSUFFICIENT_RESOURCES;
    }

    RtlZeroMemory(g_PerCpuRings, totalSize);

    // Initialize each per-CPU ring buffer
    for (i = 0; i < g_ProcessorCount; i++) {
        PPERCPU_RING ring = GetPerCpuRing(i);
        ring->Head = -1;  // Start at -1 so first increment is 0
        ring->Tail = -1;  // Start at -1 for reader tracking
        ring->Mask = RING_BUFFER_MASK;
        ring->LostEvents = 0;
        ring->SequenceCounter = 0;
        
        // Get performance counter frequency. The kernel exposes no
        // KeQueryPerformanceFrequency; the frequency is returned via the
        // optional out-parameter of KeQueryPerformanceCounter.
        LARGE_INTEGER freq;
        (VOID)KeQueryPerformanceCounter(&freq);
        ring->Frequency = freq;
    }

    // Initialize TSC state at boot time
    InitializeTscState();

    return STATUS_SUCCESS;
}

//
// Cleanup per-CPU buffers
//
VOID CleanupPerCpuBuffers(VOID)
{
    // Stop the synthetic interrupt source first
    StopSyntheticInterruptSource();

    if (g_PerCpuRings != NULL) {
        ExFreePoolWithTag(g_PerCpuRings, 'ILMR');
        g_PerCpuRings = NULL;
    }
}

//
// Device Add Event
//
NTSTATUS EvtDeviceAdd(
    _In_ WDFDRIVER Driver,
    _Inout_ PWDFDEVICE_INIT DeviceInit
)
{
    NTSTATUS status;
    WDFDEVICE device;
    WDF_OBJECT_ATTRIBUTES attributes;
    WDF_FILEOBJECT_CONFIG fileConfig;
    WDF_IO_QUEUE_CONFIG queueConfig;
    WDFQUEUE queue;
    UNICODE_STRING deviceName, symbolicLink;

    UNREFERENCED_PARAMETER(Driver);

    KdPrint(("InterruptLatencyMonitor: EvtDeviceAdd\n"));

    // Set device characteristics
    WdfDeviceInitSetDeviceType(DeviceInit, FILE_DEVICE_UNKNOWN);
    WdfDeviceInitSetIoType(DeviceInit, WdfDeviceIoBuffered);

    // Create device name
    RtlInitUnicodeString(&deviceName, L"\\Device\\InterruptLatencyMonitor");
    status = WdfDeviceInitAssignName(DeviceInit, &deviceName);
    if (!NT_SUCCESS(status)) {
        KdPrint(("InterruptLatencyMonitor: WdfDeviceInitAssignName failed: 0x%08X\n", status));
        return status;
    }

    // Create device
    WDF_OBJECT_ATTRIBUTES_INIT(&attributes);
    attributes.EvtCleanupCallback = NULL; // Cleanup handled by framework
    status = WdfDeviceCreate(&DeviceInit, &attributes, &device);
    if (!NT_SUCCESS(status)) {
        KdPrint(("InterruptLatencyMonitor: WdfDeviceCreate failed: 0x%08X\n", status));
        return status;
    }

    // Create symbolic link
    RtlInitUnicodeString(&symbolicLink, L"\\DosDevices\\InterruptLatencyMonitor");
    status = WdfDeviceCreateSymbolicLink(device, &symbolicLink);
    if (!NT_SUCCESS(status)) {
        KdPrint(("InterruptLatencyMonitor: WdfDeviceCreateSymbolicLink failed: 0x%08X\n", status));
        return status;
    }

    // Configure file object
    WDF_FILEOBJECT_CONFIG_INIT(&fileConfig, EvtDeviceFileCreate, EvtDeviceFileClose, WDF_NO_EVENT_CALLBACK);
    WdfDeviceInitSetFileObjectConfig(DeviceInit, &fileConfig, WDF_NO_OBJECT_ATTRIBUTES);

    // Create I/O queue
    WDF_IO_QUEUE_CONFIG_INIT_DEFAULT_QUEUE(&queueConfig, WdfIoQueueDispatchParallel);
    queueConfig.EvtIoDeviceControl = EvtIoDeviceControl;
    status = WdfIoQueueCreate(device, &queueConfig, WDF_NO_OBJECT_ATTRIBUTES, &queue);
    if (!NT_SUCCESS(status)) {
        KdPrint(("InterruptLatencyMonitor: WdfIoQueueCreate failed: 0x%08X\n", status));
        return status;
    }

    // Create interrupt object (for instrumentation)
    status = CreateInterruptObject(device);
    if (!NT_SUCCESS(status)) {
        KdPrint(("InterruptLatencyMonitor: CreateInterruptObject failed: 0x%08X\n", status));
        // Non-fatal, continue
    }

    return STATUS_SUCCESS;
}

//
// CreateInterruptObject — starts the synthetic interrupt source
//
NTSTATUS CreateInterruptObject(_In_ WDFDEVICE Device)
{
    NTSTATUS status;

    UNREFERENCED_PARAMETER(Device);

    KdPrint(("InterruptLatencyMonitor: CreateInterruptObject — starting synthetic source\n"));

    status = StartSyntheticInterruptSource();
    if (!NT_SUCCESS(status)) {
        KdPrint(("InterruptLatencyMonitor: StartSyntheticInterruptSource failed: 0x%08X\n", status));
        return status;
    }

    KdPrint(("InterruptLatencyMonitor: Synthetic interrupt source active (%d ms interval)\n",
             SYNTHETIC_TIMER_INTERVAL_MS));
    return STATUS_SUCCESS;
}

//
// SyntheticTimerDpc — Timer DPC callback (DISPATCH_LEVEL)
//
// KeSetTimerEx invokes this function every SYNTHETIC_TIMER_INTERVAL_MS
// milliseconds. The function simulates what an ISR does:
//   1. Writes an ISR_START event
//   2. Performs minimal work (interrupt acknowledge simulation)
//   3. Writes an ISR_END event
//   4. Queues the work DPC
//
VOID SyntheticTimerDpc(
    _In_ PKDPC Dpc,
    _In_opt_ PVOID DeferredContext,
    _In_opt_ PVOID SystemArgument1,
    _In_opt_ PVOID SystemArgument2
)
{
    IRQ_EVENT event;
    ULONG cpu;

    UNREFERENCED_PARAMETER(Dpc);
    UNREFERENCED_PARAMETER(DeferredContext);
    UNREFERENCED_PARAMETER(SystemArgument1);
    UNREFERENCED_PARAMETER(SystemArgument2);

    if (!g_InstrumentationEnabled) {
        return;
    }

    cpu = (ULONG)KeGetCurrentProcessorNumberEx(NULL);

    // Increment fire counter
    InterlockedIncrement64((volatile LONGLONG*)&g_SyntheticState.FireCount);

    // ── ISR_START ──────────────────────────────────────────────
    RtlZeroMemory(&event, sizeof(event));
    event.Vector    = SYNTHETIC_VECTOR;
    event.Cpu       = (UCHAR)cpu;
    event.Phase     = EVT_ISR_START;
    event.QueueDepth = 0;
    KeQueryPerformanceCounter(&event.Timestamp);
    event.TscValue  = 0;    // No TSC in ISR — overhead minimization
    WriteEvent(&event, cpu);

    // ISR work: just record the last fire time (analogous to the
    // "acknowledge hardware" step in a real ISR)
    KeQueryPerformanceCounter(&g_SyntheticState.LastFired);

    // ── ISR_END ────────────────────────────────────────────────
    event.Phase = EVT_ISR_END;
    KeQueryPerformanceCounter(&event.Timestamp);
    event.TscValue = 0;
    WriteEvent(&event, cpu);

    // ── Queue the Work DPC ─────────────────────────────────────
    // KeInsertQueueDpc: enqueues a DPC — analogous to WdfInterruptQueueDpcForIsr
    // We pass the CPU number to the DPC via SystemArgument1
    KeInsertQueueDpc(&g_SyntheticState.WorkDpc,
                     (PVOID)(ULONG_PTR)cpu,
                     NULL);
}

//
// SyntheticWorkDpc — Work DPC callback (DISPATCH_LEVEL)
//
// The "heavy work" DPC queued by the ISR.
// In a real driver, packet processing, I/O completion, etc. happen here.
// We only measure timing.
//
VOID SyntheticWorkDpc(
    _In_ PKDPC Dpc,
    _In_opt_ PVOID DeferredContext,
    _In_opt_ PVOID SystemArgument1,
    _In_opt_ PVOID SystemArgument2
)
{
    IRQ_EVENT event;
    ULONG cpu;
    ULONG queueDepth;

    UNREFERENCED_PARAMETER(Dpc);
    UNREFERENCED_PARAMETER(DeferredContext);
    UNREFERENCED_PARAMETER(SystemArgument2);

    if (!g_InstrumentationEnabled) {
        return;
    }

    // Get CPU number from the ISR (passed via SystemArgument1)
    cpu = (ULONG)(ULONG_PTR)SystemArgument1;
    if (cpu >= g_ProcessorCount) {
        cpu = (ULONG)KeGetCurrentProcessorNumberEx(NULL);
    }

    queueDepth = QueryDpcQueueDepth();

    // ── DPC_START ──────────────────────────────────────────────
    RtlZeroMemory(&event, sizeof(event));
    event.Vector     = SYNTHETIC_VECTOR;
    event.Cpu        = (UCHAR)cpu;
    event.Phase      = EVT_DPC_START;
    event.QueueDepth = queueDepth;
    KeQueryPerformanceCounter(&event.Timestamp);
    // At DPC level, TSC is used conditionally
    event.TscValue = ShouldUseTscInIsr() ? ReadTsc() : 0;
    WriteEvent(&event, cpu);

    // DPC work simulation — real driver data processing would happen here.
    // Left empty: for measurement we want to observe pure scheduling latency.

    // ── DPC_END ────────────────────────────────────────────────
    event.Phase    = EVT_DPC_END;
    event.QueueDepth = 0;
    KeQueryPerformanceCounter(&event.Timestamp);
    event.TscValue = ShouldUseTscInIsr() ? ReadTsc() : 0;
    WriteEvent(&event, cpu);
}

//
// StartSyntheticInterruptSource
//
// Initializes a KTIMER and two KDPC objects.
// The timer triggers SyntheticTimerDpc every SYNTHETIC_TIMER_INTERVAL_MS ms.
//
NTSTATUS StartSyntheticInterruptSource(VOID)
{
    LARGE_INTEGER dueTime;

    if (g_SyntheticState.Active) {
        return STATUS_SUCCESS;  // Already active
    }

    // Initialize timer and DPC objects
    KeInitializeTimer(&g_SyntheticState.Timer);

    KeInitializeDpc(&g_SyntheticState.TimerDpc,
                    SyntheticTimerDpc,
                    NULL);

    KeInitializeDpc(&g_SyntheticState.WorkDpc,
                    SyntheticWorkDpc,
                    NULL);

    // Pin WorkDpc to a specific CPU — for consistent measurement
    // Use KeSetTargetProcessorDpc to pin to CPU 0
    KeSetTargetProcessorDpc(&g_SyntheticState.WorkDpc, 0);

    g_SyntheticState.FireCount = 0;
    g_SyntheticState.Active    = TRUE;

    // Start the timer:
    // dueTime negative = relative time (100-nanosecond units)
    // SYNTHETIC_TIMER_INTERVAL_MS * -10000 = ms → 100ns units
    dueTime.QuadPart = (LONGLONG)SYNTHETIC_TIMER_INTERVAL_MS * -10000LL;

    KeSetTimerEx(
        &g_SyntheticState.Timer,
        dueTime,
        SYNTHETIC_TIMER_INTERVAL_MS,    // Period (ms)
        &g_SyntheticState.TimerDpc
    );

    KdPrint(("InterruptLatencyMonitor: Synthetic timer started, interval=%d ms\n",
             SYNTHETIC_TIMER_INTERVAL_MS));
    return STATUS_SUCCESS;
}

//
// StopSyntheticInterruptSource
//
// Stops the timer and waits for pending DPCs to complete.
// Called from the EvtDeviceAdd cleanup path or from IOCTL_SET_CONFIG.
//
VOID StopSyntheticInterruptSource(VOID)
{
    if (!g_SyntheticState.Active) {
        return;
    }

    g_SyntheticState.Active = FALSE;

    // Cancel the timer — FALSE: do not wait for the timer DPC to complete
    KeCancelTimer(&g_SyntheticState.Timer);

    // Brief wait for pending DPCs to complete
    // KeFlushQueuedDpcs() requires PASSIVE_LEVEL — safe in the driver unload path
    KeFlushQueuedDpcs();

    KdPrint(("InterruptLatencyMonitor: Synthetic timer stopped. Total fires: %llu\n",
             g_SyntheticState.FireCount));
}

//
// File Create Event
//
VOID EvtDeviceFileCreate(
    _In_ WDFDEVICE Device,
    _In_ WDFREQUEST Request,
    _In_ WDFFILEOBJECT FileObject
)
{
    UNREFERENCED_PARAMETER(Device);
    UNREFERENCED_PARAMETER(FileObject);

    KdPrint(("InterruptLatencyMonitor: File opened\n"));
    WdfRequestComplete(Request, STATUS_SUCCESS);
}

//
// File Close Event
//
VOID EvtDeviceFileClose(
    _In_ WDFFILEOBJECT FileObject
)
{
    UNREFERENCED_PARAMETER(FileObject);
    KdPrint(("InterruptLatencyMonitor: File closed\n"));
}

//
// I/O Device Control Handler
//
VOID EvtIoDeviceControl(
    _In_ WDFQUEUE Queue,
    _In_ WDFREQUEST Request,
    _In_ size_t OutputBufferLength,
    _In_ size_t InputBufferLength,
    _In_ ULONG IoControlCode
)
{
    NTSTATUS status = STATUS_SUCCESS;
    PIOCTL_GET_EVENTS_IN getEventsIn = NULL;
    PIOCTL_GET_EVENTS_OUT getEventsOut = NULL;
    PIOCTL_CONFIG config = NULL;
    ULONG bytesReturned = 0;

    UNREFERENCED_PARAMETER(Queue);

    switch (IoControlCode) {
    case IOCTL_GET_EVENTS:
        if (InputBufferLength < sizeof(IOCTL_GET_EVENTS_IN)) {
            status = STATUS_BUFFER_TOO_SMALL;
            break;
        }

        // WdfRequestRetrieveInputBuffer returns NTSTATUS and yields the buffer
        // through its 3rd parameter; it must not be cast to a pointer.
        status = WdfRequestRetrieveInputBuffer(Request, sizeof(IOCTL_GET_EVENTS_IN), (PVOID*)&getEventsIn, NULL);
        if (!NT_SUCCESS(status)) {
            break;
        }

        if (getEventsIn->CpuNumber >= g_ProcessorCount) {
            status = STATUS_INVALID_PARAMETER;
            break;
        }

        {
            PPERCPU_RING ring = GetPerCpuRing(getEventsIn->CpuNumber);
            ULONG maxEvents;
            ULONG eventsToCopy;
            ULONG currentHead;
            ULONG currentTail;
            ULONG i;
            ULONG64 lastSequence = 0;

            // Validate and retrieve the output buffer BEFORE doing any
            // arithmetic derived from the caller-supplied OutputBufferLength.
            // WdfRequestRetrieveOutputBuffer's minimum-size check guarantees
            // OutputBufferLength >= sizeof(IOCTL_GET_EVENTS_OUT), which is
            // strictly greater than FIELD_OFFSET(IOCTL_GET_EVENTS_OUT, Events)
            // (EventCount precedes Events in the struct), so the subtraction
            // below can no longer underflow. Previously maxEvents was computed
            // from the unvalidated OutputBufferLength first, which would wrap
            // to a huge size_t for an undersized output buffer.
            status = WdfRequestRetrieveOutputBuffer(Request, sizeof(IOCTL_GET_EVENTS_OUT), (PVOID*)&getEventsOut, NULL);
            if (!NT_SUCCESS(status)) {
                break;
            }

            maxEvents = (ULONG)(OutputBufferLength - FIELD_OFFSET(IOCTL_GET_EVENTS_OUT, Events)) / sizeof(IRQ_EVENT);
            eventsToCopy = min(maxEvents, RING_BUFFER_SIZE);
            currentHead = (ULONG)InterlockedOr((volatile LONG*)&ring->Head, 0); // Read current head
            currentTail = (ULONG)InterlockedOr((volatile LONG*)&ring->Tail, 0); // Read current tail

            // Copy events from ring buffer
            // Start from Tail (or StartIndex if provided) and read up to Head
            ULONG startIdx = (getEventsIn->StartIndex > 0) ? getEventsIn->StartIndex : ((currentTail + 1) & ring->Mask);
            ULONG endIdx = currentHead;
            
            getEventsOut->EventCount = 0;
            for (i = 0; i < eventsToCopy; i++) {
                ULONG idx = (startIdx + i) & ring->Mask;
                
                // Check for sequence gaps (lost events).
                // DEAD CODE / intentional no-op: this branch deliberately does
                // nothing on the kernel side. Gap detection is performed
                // independently in userspace (gui/statistics_processor.py)
                // from the same monotonic SequenceId field returned in each
                // IRQ_EVENT, so no kernel-side action is required here. Left
                // in place as a documented observation point, not a bug to
                // "finish" -- do not add kernel-side handling without a
                // concrete reason userspace's detection is insufficient.
                if (i > 0 && lastSequence > 0) {
                    ULONG64 expectedSeq = lastSequence + 1;
                    if (ring->Buffer[idx].SequenceId != expectedSeq && ring->Buffer[idx].SequenceId != 0) {
                        // Sequence gap detected - events were lost.
                        // Intentionally no-op; see comment above.
                    }
                }
                
                getEventsOut->Events[i] = ring->Buffer[idx];
                lastSequence = ring->Buffer[idx].SequenceId;
                getEventsOut->EventCount++;
                
                // Stop if we've reached the current head
                if (idx == (endIdx & ring->Mask)) {
                    break;
                }
            }
            
            // Update Tail to mark what we've read
            if (getEventsOut->EventCount > 0) {
                ULONG newTail = (startIdx + getEventsOut->EventCount - 1) & ring->Mask;
                InterlockedExchange(&ring->Tail, (LONG)newTail);
            }

            bytesReturned = FIELD_OFFSET(IOCTL_GET_EVENTS_OUT, Events) + (getEventsOut->EventCount * sizeof(IRQ_EVENT));
        }
        break;

    case IOCTL_GET_STATISTICS:
        // Aggregated statistics are computed in userspace from raw event
        // traces returned by IOCTL_GET_EVENTS. Kernel-side aggregation is
        // reserved for future work; signal that explicitly rather than
        // returning a zero buffer that callers may mistake for valid data.
        status = STATUS_NOT_IMPLEMENTED;
        break;

    case IOCTL_RESET_BUFFERS:
        {
            ULONG i;
            for (i = 0; i < g_ProcessorCount; i++) {
                PPERCPU_RING ring = GetPerCpuRing(i);
                InterlockedExchange(&ring->Head, -1);
                InterlockedExchange(&ring->Tail, -1);
                ring->LostEvents = 0;
                ring->SequenceCounter = 0;
                RtlZeroMemory(ring->Buffer, sizeof(ring->Buffer));
            }
            bytesReturned = 0;
        }
        break;

    case IOCTL_SET_CONFIG:
        if (InputBufferLength < sizeof(IOCTL_CONFIG)) {
            status = STATUS_BUFFER_TOO_SMALL;
            break;
        }

        status = WdfRequestRetrieveInputBuffer(Request, sizeof(IOCTL_CONFIG), (PVOID*)&config, NULL);
        if (!NT_SUCCESS(status)) {
            break;
        }

        g_Config = *config;
        g_InstrumentationEnabled = config->EnableInstrumentation;

        // Manage the synthetic timer when instrumentation is toggled
        if (config->EnableInstrumentation && !g_SyntheticState.Active) {
            StartSyntheticInterruptSource();
        } else if (!config->EnableInstrumentation && g_SyntheticState.Active) {
            StopSyntheticInterruptSource();
        }

        bytesReturned = 0;
        break;

    default:
        status = STATUS_INVALID_DEVICE_REQUEST;
        break;
    }

    WdfRequestCompleteWithInformation(Request, status, bytesReturned);
}

//
// Interrupt Service Routine
//
// DEAD CODE (currently unreachable): this handler is fully implemented and
// declared in the header (EVT_WDF_INTERRUPT_ISR), but nothing in this driver
// ever calls WdfInterruptCreate to bind it to a real interrupt object --
// CreateInterruptObject() only starts the synthetic KeSetTimerEx harness
// (see SyntheticTimerDpc/SyntheticWorkDpc below), which is the only event
// source that runs in the current build. Binding this handler to a real
// target interrupt via WdfInterruptCreate is the documented next step
// (README "Limitations and Roadmap" #1) and is intentionally NOT done here:
// it requires a specific target device/interrupt resource and real hardware
// to validate, which is untestable in this environment.
//
BOOLEAN EvtInterruptIsr(
    _In_ WDFINTERRUPT Interrupt,
    _In_ ULONG MessageID
)
{
    IRQ_EVENT event;
    ULONG cpu;

    if (!g_InstrumentationEnabled) {
        return FALSE;
    }

    cpu = (ULONG)KeGetCurrentProcessorNumberEx(NULL);

    // ISR START
    // Note: In ISR, we minimize overhead - use QPC only
    // TSC reading moved to DPC level if needed for higher resolution
    RtlZeroMemory(&event, sizeof(event));
    event.Vector = (USHORT)MessageID;
    event.Cpu = (UCHAR)cpu;
    event.Phase = EVT_ISR_START;
    event.QueueDepth = 0;
    KeQueryPerformanceCounter(&event.Timestamp);
    // Don't use TSC in ISR - it can add latency on some systems
    // If TSC is needed, read it at DPC level
    event.TscValue = 0;
    WriteEvent(&event, cpu);

    // Schedule DPC
    WdfInterruptQueueDpcForIsr(Interrupt);

    // ISR END
    event.Phase = EVT_ISR_END;
    KeQueryPerformanceCounter(&event.Timestamp);
    // Don't use TSC in ISR - minimize latency
    event.TscValue = 0;
    WriteEvent(&event, cpu);

    return TRUE;
}

//
// Deferred Procedure Call
//
// DEAD CODE (currently unreachable): same status as EvtInterruptIsr above --
// never bound via WdfInterruptCreate, so it never runs in the current build.
//
VOID EvtInterruptDpc(
    _In_ WDFINTERRUPT Interrupt,
    _In_ WDFOBJECT AssociatedObject
)
{
    IRQ_EVENT event;
    ULONG cpu;
    WDF_INTERRUPT_INFO info;

    UNREFERENCED_PARAMETER(AssociatedObject);

    if (!g_InstrumentationEnabled) {
        return;
    }

    cpu = (ULONG)KeGetCurrentProcessorNumberEx(NULL);

    WdfInterruptGetInfo(Interrupt, &info);

    // DPC START
    // DPC level is safer for TSC reading - less latency impact
    RtlZeroMemory(&event, sizeof(event));
    event.Vector = (USHORT)info.MessageNumber;
    event.Cpu = (UCHAR)cpu;
    event.Phase = EVT_DPC_START;
    event.QueueDepth = QueryDpcQueueDepth();
    KeQueryPerformanceCounter(&event.Timestamp);
    // Use TSC at DPC level if available and configured
    if (ShouldUseTscInIsr()) {
        event.TscValue = ReadTsc();
    } else {
        event.TscValue = 0;
    }
    WriteEvent(&event, cpu);

    // DPC processing would happen here
    // ...

    // DPC END
    event.Phase = EVT_DPC_END;
    KeQueryPerformanceCounter(&event.Timestamp);
    // Use TSC at DPC level if available and configured
    if (ShouldUseTscInIsr()) {
        event.TscValue = ReadTsc();
    } else {
        event.TscValue = 0;
    }
    WriteEvent(&event, cpu);
}

//
// Write event to per-CPU ring buffer (lock-free).
// Caller passes the current CPU number so the function avoids a redundant
// KeGetCurrentProcessorNumberEx call and the risk of a DPC migrating between
// the caller's measurement and the slot index assignment.
//
__forceinline VOID WriteEvent(_In_ PIRQ_EVENT Event, _In_ ULONG Cpu)
{
    PPERCPU_RING ring;
    LONG idx;
    LONG tail;
    ULONG64 sequenceId;

    if (Event == NULL || !g_InstrumentationEnabled) {
        return;
    }

    ring = GetPerCpuRing(Cpu);

    // Lock-free slot reservation: InterlockedIncrement returns the post-
    // increment value, so the writer's slot is (idx & Mask).
    idx = InterlockedIncrement(&ring->Head);

    // Monotonic sequence number for lost-event detection by the consumer.
    sequenceId = (ULONG64)InterlockedIncrement64((volatile LONGLONG*)&ring->SequenceCounter);
    Event->SequenceId = sequenceId;

    // Commit the event into the reserved slot.
    ring->Buffer[(ULONG)idx & ring->Mask] = *Event;

    // Overflow detection: if the producer has lapped the consumer by a full
    // ring (Head - Tail > RING_BUFFER_SIZE), the slot we just wrote replaced
    // an event the consumer never read. Tail is the consumer's high-water
    // mark, initialized to -1 (no event ever read), advanced by IOCTL_GET_EVENTS.
    tail = InterlockedOr((volatile LONG*)&ring->Tail, 0);
    if ((idx - tail) > (LONG)RING_BUFFER_SIZE) {
        InterlockedIncrement64((volatile LONGLONG*)&ring->LostEvents);
    }
}

//
// Query DPC queue depth (simplified - actual implementation would query kernel structures)
//
ULONG QueryDpcQueueDepth(VOID)
{
    // This is a placeholder - actual implementation would need to access
    // kernel DPC queue structures which may not be directly accessible
    // In production, you might use kernel debugging extensions or maintain
    // a per-CPU counter that tracks DPC enqueue/dequeue operations
    return 0;
}

//
// Initialize TSC state at boot time
//
VOID InitializeTscState(VOID)
{
    // Check CPUID feature flags for invariant TSC
    // CPUID function 0x80000007, EDX bit 8 = Invariant TSC
    int cpuInfo[4];
    __cpuidex(cpuInfo, 0x80000007, 0);
    g_TscState.IsInvariant = (cpuInfo[3] & (1 << 8)) != 0; // EDX register, bit 8
    
    // Additional check: CPUID function 0x80000001, EDX bit 27 = RDTSCP support
    __cpuidex(cpuInfo, 0x80000001, 0);
    BOOLEAN hasRdtscp = (cpuInfo[3] & (1 << 27)) != 0;
    
    // If TSC is not invariant, we should not use it in ISR
    // Even if invariant, check if we should use it based on system configuration
    if (g_TscState.IsInvariant && hasRdtscp) {
        // Try to get TSC frequency (if available via HalQuerySystemInformation)
        // For now, we'll rely on QPC for cross-CPU synchronization
        g_TscState.TscFrequency = 0; // Will be calibrated if needed
    }
    
    g_TscState.IsInitialized = TRUE;
    
    KdPrint(("InterruptLatencyMonitor: TSC State - Invariant: %s, Initialized: %s\n",
        g_TscState.IsInvariant ? "YES" : "NO",
        g_TscState.IsInitialized ? "YES" : "NO"));
}

//
// Check if TSC is invariant (doesn't change with CPU frequency scaling)
//
// DEAD CODE: never called anywhere in this driver. ShouldUseTscInIsr()
// below inlines the same g_TscState.IsInvariant && g_TscState.IsInitialized
// check directly rather than calling this helper. Kept as documented,
// unused API surface rather than removed, in case a future caller wants the
// invariant-TSC check in isolation from ShouldUseTscInIsr()'s additional
// UseRdtsc config gate.
//
BOOLEAN IsInvariantTsc(VOID)
{
    return g_TscState.IsInvariant && g_TscState.IsInitialized;
}

//
// Determine if we should use TSC in ISR context
// Rule: Only use TSC in ISR if it's invariant AND we're not on a system where QPC is faster
//
BOOLEAN ShouldUseTscInIsr(VOID)
{
    // Only use TSC in ISR if:
    // 1. TSC is invariant
    // 2. TSC state has been initialized
    // 3. Config allows it
    // Note: On some systems, QPC may be faster due to optimized paths
    // For ISR, we prefer QPC for cross-CPU synchronization unless TSC is explicitly needed
    return g_TscState.IsInvariant && 
           g_TscState.IsInitialized && 
           g_Config.UseRdtsc;
}

//
// Read TSC (Time Stamp Counter)
//
ULONG64 ReadTsc(VOID)
{
    return __rdtsc();
}

