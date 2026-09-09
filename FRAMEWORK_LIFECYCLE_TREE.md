```
┌──────────────────────────────────────────────────────────────────────────┐
│     INTERRUPT LATENCY MONITORING FRAMEWORK                                 │
│                    COMPLETE LIFECYCLE TREE                                 │
└──────────────────────────────────────────────────────────────────────────┘

SYSTEM STARTUP
│
├─► [KERNEL] Driver Load
│   │
│   ├─► DriverEntry()
│   │   │
│   │   ├─► WdfDriverCreate()
│   │   │   │
│   │   │   ├─► [SUCCESS] → EvtDeviceAdd() registered
│   │   │   │   │
│   │   │   │   ├─► KeQueryActiveProcessorCountEx()
│   │   │   │   │   │
│   │   │   │   │   ├─► [SUCCESS] → g_ProcessorCount = N
│   │   │   │   │   │   │
│   │   │   │   │   │   └─► InitializePerCpuBuffers()
│   │   │   │   │   │       │
│   │   │   │   │   │       ├─► ExAllocatePoolWithTag(NonPagedPoolNx, ...)
│   │   │   │   │   │       │   │
│   │   │   │   │   │       │   ├─► [SUCCESS] → Memory allocated
│   │   │   │   │   │       │   │   │
│   │   │   │   │   │       │   │   ├─► RtlZeroMemory(g_PerCpuRings, ...)
│   │   │   │   │   │       │   │   │   │
│   │   │   │   │   │       │   │   │   └─► For each CPU (0 to N-1):
│   │   │   │   │   │       │   │   │       │
│   │   │   │   │   │       │   │   │       ├─► GetPerCpuRing(cpu)
│   │   │   │   │   │       │   │   │       │   │
│   │   │   │   │   │       │   │   │       │   ├─► ring->Head = -1
│   │   │   │   │   │       │   │   │       │   ├─► ring->Mask = 0x0FFF
│   │   │   │   │   │       │   │   │       │   ├─► ring->LostEvents = 0
│   │   │   │   │   │       │   │   │       │   └─► KeQueryPerformanceFrequency()
│   │   │   │   │   │       │   │   │       │       │
│   │   │   │   │   │       │   │   │       │       └─► ring->Frequency = freq
│   │   │   │   │   │       │   │   │       │
│   │   │   │   │   │       │   │   │       └─► [All CPUs init] → SUCCESS
│   │   │   │   │   │       │   │   │
│   │   │   │   │   │       │   │   └─► [INIT COMPLETE]
│   │   │   │   │   │       │   │
│   │   │   │   │   │       │   └─► [FAILURE] → INSUFFICIENT_RESOURCES
│   │   │   │   │   │       │       │
│   │   │   │   │   │       │       └─► [SOLUTION] → Reduce buffer size
│   │   │   │   │   │       │
│   │   │   │   │   │       └─► [FAILURE] → Return error
│   │   │   │   │   │
│   │   │   │   │   └─► [FAILURE] → g_ProcessorCount = 0
│   │   │   │   │       │
│   │   │   │   │       └─► [SOLUTION] → Check processor groups
│   │   │   │   │
│   │   │   │   └─► [FAILURE] → WdfDriverCreate failed
│   │   │   │       │
│   │   │   │       └─► [SOLUTION] → Check WDF version
│   │   │   │
│   │   │   └─► [FAILURE] → Return error
│   │   │
│   │   └─► [DRIVER ENTRY COMPLETE] → SUCCESS
│   │
│   └─► [DEVICE CREATION] EvtDeviceAdd()
│       │
│       ├─► WdfDeviceInitSetDeviceType()
│       ├─► WdfDeviceInitSetIoType()
│       │
│       ├─► WdfDeviceInitAssignName()
│       │   │
│       │   ├─► [SUCCESS] → Device name assigned
│       │   │   │
│       │   │   └─► WdfDeviceCreate()
│       │   │       │
│       │   │       ├─► [SUCCESS] → Device created
│       │   │       │   │
│       │   │       │   ├─► WdfDeviceCreateSymbolicLink()
│       │   │       │   │   │
│       │   │       │   │   ├─► [SUCCESS] → Link created
│       │   │       │   │   │   │
│       │   │       │   │   │   ├─► WDF_FILEOBJECT_CONFIG_INIT()
│       │   │       │   │   │   │   │
│       │   │       │   │   │   │   └─► WdfDeviceInitSetFileObjectConfig()
│       │   │       │   │   │   │
│       │   │       │   │   │   └─► WDF_IO_QUEUE_CONFIG_INIT()
│       │   │       │   │   │       │
│       │   │       │   │   │       ├─► queueConfig.EvtIoDeviceControl = ...
│       │   │       │   │   │       │   │
│       │   │       │   │   │       │   └─► WdfIoQueueCreate()
│       │   │       │   │   │       │       │
│       │   │       │   │   │       │       ├─► [SUCCESS] → Queue created
│       │   │       │   │   │       │       │   │
│       │   │       │   │   │       │       │   └─► CreateInterruptObject()
│       │   │       │   │   │       │       │       │
│       │   │       │   │   │       │       │       ├─► [PLACEHOLDER] → No interrupt
│       │   │       │   │   │       │       │       │   │
│       │   │       │   │   │       │       │       │   └─► [NOTE] → Hook in production
│       │   │       │   │   │       │       │       │
│       │   │       │   │   │       │       │       └─► [DEVICE READY]
│       │   │       │   │   │       │       │
│       │   │       │   │   │       │       └─► [FAILURE] → Queue failed
│       │   │       │   │   │       │           │
│       │   │       │   │   │       │           └─► [SOLUTION] → Check WDF config
│       │   │       │   │   │       │
│       │   │       │   │   │       └─► [FAILURE] → Link failed
│       │   │       │   │   │           │
│       │   │       │   │   │           └─► [SOLUTION] → Check permissions
│       │   │       │   │   │
│       │   │       │   │   └─► [FAILURE] → Device creation failed
│       │   │       │   │       │
│       │   │       │   │       └─► [SOLUTION] → Check name conflicts
│       │   │       │   │
│       │   │       │   └─► [FAILURE] → Name assignment failed
│       │   │       │       │
│       │   │       │       └─► [SOLUTION] → Check registry
│       │   │       │
│       │   │       └─► [DEVICE ADD COMPLETE] → SUCCESS
│       │   │
│       │   └─► [DRIVER LOADED AND READY]
│       │
│       └─► [SYSTEM READY]
│
│
├─► [USERSPACE] Daemon Startup
│   │
│   ├─► daemon.exe Start
│   │   │
│   │   ├─► Initialize()
│   │   │   │
│   │   │   ├─► OpenDevice()
│   │   │   │   │
│   │   │   │   ├─► CreateFile(L"\\\\.\\InterruptLatencyMonitor", ...)
│   │   │   │   │   │
│   │   │   │   │   ├─► [SUCCESS] → Handle valid
│   │   │   │   │   │   │
│   │   │   │   │   │   ├─► GetSystemInfo()
│   │   │   │   │   │   │   │
│   │   │   │   │   │   │   └─► m_processorCount = sysInfo.dwNumberOfProcessors
│   │   │   │   │   │   │       │
│   │   │   │   │   │   │       └─► m_perCpuStats.resize(m_processorCount)
│   │   │   │   │   │   │           │
│   │   │   │   │   │   │           └─► For each CPU: Init Statistics
│   │   │   │   │   │   │
│   │   │   │   │   │   └─► IOCTL_SET_CONFIG
│   │   │   │   │   │       │
│   │   │   │   │   │       ├─► [KERNEL] EvtIoDeviceControl()
│   │   │   │   │   │       │   │
│   │   │   │   │   │       │   ├─► Validate input buffer
│   │   │   │   │   │       │   │   │
│   │   │   │   │   │       │   │   ├─► [VALID] → Continue
│   │   │   │   │   │       │   │   │   │
│   │   │   │   │   │       │   │   │   └─► config = *input
│   │   │   │   │   │       │   │   │       │
│   │   │   │   │   │       │   │   │       ├─► g_Config = config
│   │   │   │   │   │       │   │   │       │   │
│   │   │   │   │   │       │   │   │       │   └─► g_InstrumentationEnabled = ...
│   │   │   │   │   │       │   │   │       │
│   │   │   │   │   │       │   │   │       └─► [CONFIG APPLIED] → SUCCESS
│   │   │   │   │   │       │   │   │
│   │   │   │   │   │       │   │   └─► [INVALID] → INVALID_PARAMETER
│   │   │   │   │   │       │   │       │
│   │   │   │   │   │       │   │       └─► [SOLUTION] → Check buffer size
│   │   │   │   │   │       │   │
│   │   │   │   │   │       │   └─► [CONFIG COMPLETE]
│   │   │   │   │   │       │
│   │   │   │   │   │       └─► [FAILURE] → DeviceIoControl failed
│   │   │   │   │   │           │
│   │   │   │   │   │           └─► [SOLUTION] → Check driver status
│   │   │   │   │   │
│   │   │   │   │   └─► [INIT COMPLETE] → Return true
│   │   │   │   │
│   │   │   │   └─► [FAILURE] → CreateFile failed
│   │   │   │       │
│   │   │   │       ├─► [ERROR: FILE_NOT_FOUND] → Driver not loaded
│   │   │   │       │   │
│   │   │   │       │   └─► [SOLUTION] → sc start InterruptLatencyMonitor
│   │   │   │       │
│   │   │   │       ├─► [ERROR: ACCESS_DENIED] → No privileges
│   │   │   │       │   │
│   │   │   │       │   └─► [SOLUTION] → Run as admin
│   │   │   │       │
│   │   │   │       └─► [ERROR: OTHER] → Check GetLastError()
│   │   │   │           │
│   │   │   │           └─► [SOLUTION] → Verify installation
│   │   │   │
│   │   │   └─► [DAEMON INITIALIZED]
│   │   │
│   │   └─► Start()
│   │       │
│   │       ├─► m_running = true
│   │       │   │
│   │       │   └─► m_collectionThread = std::thread(&CollectionLoop, ...)
│   │       │       │
│   │       │       └─► [COLLECTION THREAD STARTED]
│   │       │
│   │       └─► [DAEMON RUNNING]
│   │
│   └─► [USERSPACE READY]
│
│
├─► [RUNTIME] Interrupt Handling
│   │
│   ├─► [HARDWARE] Interrupt Occurs
│   │   │
│   │   ├─► Hardware raises IRQ
│   │   │   │
│   │   │   └─► [KERNEL] KiInterruptDispatch()
│   │   │       │
│   │   │       └─► [IF HOOKED] → EvtInterruptIsr()
│   │   │           │
│   │   │           ├─► [CHECK] g_InstrumentationEnabled == TRUE?
│   │   │           │   │
│   │   │           │   ├─► [YES] → Continue instrumentation
│   │   │           │   │   │
│   │   │           │   │   ├─► cpu = KeGetCurrentProcessorNumberEx(NULL)
│   │   │           │   │   │   │
│   │   │           │   │   │   └─► ring = GetPerCpuRing(cpu)
│   │   │           │   │   │
│   │   │           │   │   ├─► [ISR_START Event Creation]
│   │   │           │   │   │   │
│   │   │           │   │   │   ├─► event.Vector = (USHORT)MessageID
│   │   │           │   │   │   ├─► event.Cpu = (UCHAR)cpu
│   │   │           │   │   │   ├─► event.Phase = EVT_ISR_START
│   │   │           │   │   │   ├─► event.QueueDepth = 0
│   │   │           │   │   │   │
│   │   │           │   │   │   ├─► KeQueryPerformanceCounter(&event.Timestamp)
│   │   │           │   │   │   │   │
│   │   │           │   │   │   │   └─► [QPC READ] → High-res timestamp
│   │   │           │   │   │   │
│   │   │           │   │   │   └─► [IF g_Config.UseRdtsc] → Check TSC
│   │   │           │   │   │       │
│   │   │           │   │   │       ├─► [YES] → IsInvariantTsc()
│   │   │           │   │   │       │   │
│   │   │           │   │   │       │   ├─► [TRUE] → ReadTsc()
│   │   │           │   │   │       │   │   │
│   │   │           │   │   │       │   │   └─► event.TscValue = __rdtsc()
│   │   │           │   │   │       │   │
│   │   │           │   │   │       │   └─► [FALSE] → event.TscValue = 0
│   │   │           │   │   │       │       │
│   │   │           │   │   │       │       └─► [NOTE] → Use QPC only
│   │   │           │   │   │       │
│   │   │           │   │   │       └─► [NO] → event.TscValue = 0
│   │   │           │   │   │
│   │   │           │   │   └─► WriteEvent(&event)
│   │   │           │   │       │
│   │   │           │   │       ├─► [LOCK-FREE WRITE]
│   │   │           │   │       │   │
│   │   │           │   │       │   ├─► idx = InterlockedIncrement(&ring->Head)
│   │   │           │   │       │   │   │
│   │   │           │   │       │   │   └─► [ATOMIC] → Thread-safe
│   │   │           │   │       │   │
│   │   │           │   │       │   ├─► bufferIdx = idx & ring->Mask
│   │   │           │   │       │   │   │
│   │   │           │   │       │   │   └─► [POWER-OF-2 MODULO] → Fast calc
│   │   │           │   │       │   │
│   │   │           │   │       │   ├─► ring->Buffer[bufferIdx] = *event
│   │   │           │   │       │   │   │
│   │   │           │   │       │   │   └─► [SINGLE WRITE] → Atomic (24 bytes)
│   │   │           │   │       │   │
│   │   │           │   │       │   └─► [CHECK OVERFLOW]
│   │   │           │   │       │       │
│   │   │           │   │       │       ├─► [IF (idx & ~ring->Mask) != 0]
│   │   │           │   │       │       │   │
│   │   │           │   │       │       │   └─► InterlockedIncrement64(&LostEvents)
│   │   │           │   │       │       │       │
│   │   │           │   │       │       │       └─► [OVERFLOW] → Event lost
│   │   │           │   │       │       │
│   │   │           │   │       │       └─► [NO OVERFLOW] → Success
│   │   │           │   │       │
│   │   │           │   │       └─► [ISR_START LOGGED]
│   │   │           │   │
│   │   │           │   ├─► [ISR Processing]
│   │   │           │   │   │
│   │   │           │   │   ├─► Acknowledge interrupt
│   │   │           │   │   ├─► Minimal processing
│   │   │           │   │   │   │
│   │   │           │   │   │   └─► [BEST PRACTICE] → ISR < 10us
│   │   │           │   │   │
│   │   │           │   │   └─► WdfInterruptQueueDpcForIsr()
│   │   │           │   │       │
│   │   │           │   │       └─► [DPC QUEUED]
│   │   │           │   │
│   │   │           │   └─► [ISR_END Event Creation]
│   │   │           │       │
│   │   │           │       ├─► event.Phase = EVT_ISR_END
│   │   │           │       ├─► KeQueryPerformanceCounter(&event.Timestamp)
│   │   │           │       │   │
│   │   │           │       │   └─► [QPC READ] → ISR end timestamp
│   │   │           │       │
│   │   │           │       └─► WriteEvent(&event)
│   │   │           │           │
│   │   │           │           └─► [ISR_END LOGGED]
│   │   │           │
│   │   │           └─► [NO] → Skip instrumentation
│   │   │               │
│   │   │               └─► [NOTE] → Disabled via IOCTL_SET_CONFIG
│   │   │
│   │   └─► [ISR COMPLETE] → Return TRUE
│   │
│   ├─► [KERNEL] DPC Scheduling
│   │   │
│   │   ├─► [DISPATCH_LEVEL] DPC queued
│   │   │   │
│   │   │   └─► [QUEUE DELAY] → ISR_END to DPC_START
│   │   │       │
│   │   │       └─► [MEASURED] → DPC_START.Timestamp - ISR_END.Timestamp
│   │   │
│   │   └─► [KERNEL] KiExecuteDpc()
│   │       │
│   │       └─► [IF HOOKED] → EvtInterruptDpc()
│   │           │
│   │           ├─► [CHECK] g_InstrumentationEnabled == TRUE?
│   │           │   │
│   │           │   ├─► [YES] → Continue instrumentation
│   │           │   │   │
│   │           │   │   ├─► cpu = KeGetCurrentProcessorNumberEx(NULL)
│   │           │   │   │   │
│   │           │   │   │   └─► ring = GetPerCpuRing(cpu)
│   │           │   │   │
│   │           │   │   ├─► WdfInterruptGetInfo(Interrupt, &info)
│   │           │   │   │   │
│   │           │   │   │   └─► event.Vector = (USHORT)info.MessageNumber
│   │           │   │   │
│   │           │   │   ├─► [DPC_START Event Creation]
│   │           │   │   │   │
│   │           │   │   │   ├─► event.Phase = EVT_DPC_START
│   │           │   │   │   ├─► event.QueueDepth = QueryDpcQueueDepth()
│   │           │   │   │   │   │
│   │           │   │   │   │   └─► [NOTE] → DPC queue depth
│   │           │   │   │   │
│   │           │   │   │   ├─► KeQueryPerformanceCounter(&event.Timestamp)
│   │           │   │   │   │   │
│   │           │   │   │   │   └─► [QPC READ] → DPC start timestamp
│   │           │   │   │   │
│   │           │   │   │   └─► [IF g_Config.UseRdtsc] → ReadTsc()
│   │           │   │   │       │
│   │           │   │   │       └─► event.TscValue = __rdtsc()
│   │           │   │   │
│   │           │   │   └─► WriteEvent(&event)
│   │           │   │       │
│   │           │   │       └─► [DPC_START LOGGED]
│   │           │   │
│   │           │   ├─► [DPC Processing]
│   │           │   │   │
│   │           │   │   ├─► Heavy interrupt work
│   │           │   │   │   │
│   │           │   │   │   └─► [BEST PRACTICE] → Move work from ISR
│   │           │   │   │
│   │           │   │   ├─► I/O completion
│   │           │   │   ├─► Data processing
│   │           │   │   └─► [DPC WORK COMPLETE]
│   │           │   │
│   │           │   └─► [DPC_END Event Creation]
│   │           │       │
│   │           │       ├─► event.Phase = EVT_DPC_END
│   │           │       ├─► KeQueryPerformanceCounter(&event.Timestamp)
│   │           │       │   │
│   │           │       │   └─► [QPC READ] → DPC end timestamp
│   │           │       │
│   │           │       └─► WriteEvent(&event)
│   │           │           │
│   │           │           └─► [DPC_END LOGGED]
│   │           │
│   │           └─► [NO] → Skip instrumentation
│   │
│   └─► [INTERRUPT PROCESSING COMPLETE]
│
│
├─► [USERSPACE] Event Collection
│   │
│   ├─► CollectionLoop() [Background Thread]
│   │   │
│   │   ├─► while (m_running == true)
│   │   │   │
│   │   │   ├─► For each CPU (0 to m_processorCount-1)
│   │   │   │   │
│   │   │   │   ├─► CollectEventsFromCpu(cpu, events)
│   │   │   │   │   │
│   │   │   │   │   ├─► [IOCTL_GET_EVENTS Request]
│   │   │   │   │   │   │
│   │   │   │   │   │   ├─► input.CpuNumber = cpu
│   │   │   │   │   │   │   ├─► input.MaxEvents = 1000
│   │   │   │   │   │   │   └─► input.StartIndex = 0
│   │   │   │   │   │   │
│   │   │   │   │   │   └─► DeviceIoControl(IOCTL_GET_EVENTS, ...)
│   │   │   │   │   │       │
│   │   │   │   │   │       └─► [KERNEL] EvtIoDeviceControl()
│   │   │   │   │   │           │
│   │   │   │   │   │           ├─► [VALIDATE INPUT]
│   │   │   │   │   │           │   │
│   │   │   │   │   │           │   ├─► [CHECK] InputBufferLength >= ...?
│   │   │   │   │   │           │   │   │
│   │   │   │   │   │           │   │   ├─► [YES] → Continue
│   │   │   │   │   │           │   │   │   │
│   │   │   │   │   │           │   │   │   └─► getEventsIn = WdfRequestRetrieveInputBuffer(...)
│   │   │   │   │   │           │   │   │       │
│   │   │   │   │   │           │   │   │       └─► [CHECK] getEventsIn != NULL?
│   │   │   │   │   │           │   │   │           │
│   │   │   │   │   │           │   │   │           ├─► [YES] → Continue
│   │   │   │   │   │           │   │   │           │   │
│   │   │   │   │   │           │   │   │           │   └─► [CHECK] CpuNumber < g_ProcessorCount?
│   │   │   │   │   │           │   │   │           │       │
│   │   │   │   │   │           │   │   │           │       ├─► [YES] → Valid CPU
│   │   │   │   │   │           │   │   │           │       │   │
│   │   │   │   │   │           │   │   │           │       │   └─► ring = GetPerCpuRing(...)
│   │   │   │   │   │           │   │   │           │       │       │
│   │   │   │   │   │           │   │   │           │       │       ├─► currentHead = InterlockedOr(...)
│   │   │   │   │   │           │   │   │           │       │       │   │
│   │   │   │   │   │           │   │   │           │       │       │   └─► [READ HEAD] → May be stale
│   │   │   │   │   │           │   │   │           │       │       │
│   │   │   │   │   │           │   │   │           │       │       ├─► maxEvents = (OutputBufferLength - offset) / sizeof(IRQ_EVENT)
│   │   │   │   │   │           │   │   │           │       │       │   │
│   │   │   │   │   │           │   │   │           │       │       │   └─► eventsToCopy = min(maxEvents, RING_BUFFER_SIZE)
│   │   │   │   │   │           │   │   │           │       │       │
│   │   │   │   │   │           │   │   │           │       │       └─► [COPY EVENTS]
│   │   │   │   │   │           │   │   │           │       │           │
│   │   │   │   │   │           │   │   │           │       │           └─► For i = 0 to eventsToCopy:
│   │   │   │   │   │           │   │   │           │       │               │
│   │   │   │   │   │           │   │   │           │       │               ├─► idx = (StartIndex + i) & ring->Mask
│   │   │   │   │   │           │   │   │           │       │               │   │
│   │   │   │   │   │           │   │   │           │       │               │   └─► [WRAP-AROUND] → Power-of-2 modulo
│   │   │   │   │   │           │   │   │           │       │               │
│   │   │   │   │   │           │   │   │           │       │               └─► output->Events[i] = ring->Buffer[idx]
│   │   │   │   │   │           │   │   │           │       │                   │
│   │   │   │   │   │           │   │   │           │       │                   └─► [EVENT COPIED] → Race OK
│   │   │   │   │   │           │   │   │           │       │
│   │   │   │   │   │           │   │   │           │       └─► output->EventCount = eventsToCopy
│   │   │   │   │   │           │   │   │           │           │
│   │   │   │   │   │           │   │   │           │           └─► bytesReturned = offset + (EventCount * sizeof(IRQ_EVENT))
│   │   │   │   │   │           │   │   │           │
│   │   │   │   │   │           │   │   │           └─► [NO] → INVALID_PARAMETER
│   │   │   │   │   │           │   │   │               │
│   │   │   │   │   │           │   │   │               └─► [SOLUTION] → Verify CPU number
│   │   │   │   │   │           │   │   │
│   │   │   │   │   │           │   │   └─► [NO] → INVALID_PARAMETER
│   │   │   │   │   │           │   │       │
│   │   │   │   │   │           │   │       └─► [SOLUTION] → Check buffer retrieval
│   │   │   │   │   │           │   │
│   │   │   │   │   │           │   └─► [NO] → BUFFER_TOO_SMALL
│   │   │   │   │   │           │       │
│   │   │   │   │   │           │       └─► [SOLUTION] → Increase buffer size
│   │   │   │   │   │           │
│   │   │   │   │   │           └─► [EVENTS RETRIEVED] → Return to userspace
│   │   │   │   │   │
│   │   │   │   │   ├─► [SUCCESS] → events vector populated
│   │   │   │   │   │   │
│   │   │   │   │   │   └─► events.assign(output->Events, ...)
│   │   │   │   │   │
│   │   │   │   │   └─► [FAILURE] → DeviceIoControl failed
│   │   │   │   │       │
│   │   │   │   │       ├─► [ERROR: INVALID_HANDLE] → Handle invalid
│   │   │   │   │       │   │
│   │   │   │   │       │   └─► [SOLUTION] → Reopen device
│   │   │   │   │       │
│   │   │   │   │       └─► [ERROR: OTHER] → Check GetLastError()
│   │   │   │   │           │
│   │   │   │   │           └─► [SOLUTION] → Verify IOCTL code
│   │   │   │   │
│   │   │   │   └─► ProcessEvents(cpu, events)
│   │   │   │       │
│   │   │   │       ├─► [IF events.empty()] → Skip processing
│   │   │   │       │   │
│   │   │   │       │   └─► [NO EVENTS] → Continue to next CPU
│   │   │   │       │
│   │   │   │       ├─► [LOCK] m_statsMutex.lock()
│   │   │   │       │   │
│   │   │   │       │   └─► stats = &m_perCpuStats[cpu]
│   │   │   │       │
│   │   │   │       ├─► [EVENT PARSING]
│   │   │   │       │   │
│   │   │   │       │   ├─► pendingIsrs = std::map<EventKey, IRQ_EVENT>
│   │   │   │       │   │   │
│   │   │   │       │   │   └─► [TRACK ISR/DPC PAIRS] → Match by vector+seq
│   │   │   │       │   │
│   │   │   │       │   └─► For each event in events:
│   │   │   │       │       │
│   │   │   │       │       ├─► stats->totalEvents++
│   │   │   │       │       │   │
│   │   │   │       │       │   └─► [INCREMENT COUNTER]
│   │   │   │       │       │
│   │   │   │       │       ├─► [IF event.Phase == EVT_ISR_START]
│   │   │   │       │       │   │
│   │   │   │       │       │   ├─► stats->isrCount++
│   │   │   │       │       │   │   │
│   │   │   │       │       │   │   └─► [ISR COUNTER INCREMENTED]
│   │   │   │       │       │   │
│   │   │   │       │       │   └─► pendingIsrs[key] = event
│   │   │   │       │       │       │
│   │   │   │       │       │       └─► [TRACK ISR START] → Wait for DPC
│   │   │   │       │       │
│   │   │   │       │       ├─► [IF event.Phase == EVT_ISR_END]
│   │   │   │       │       │   │
│   │   │   │       │       │   ├─► it = pendingIsrs.find(key)
│   │   │   │       │       │   │   │
│   │   │   │       │       │   │   └─► [IF it != pendingIsrs.end()]
│   │   │   │       │       │   │       │
│   │   │   │       │       │   │       ├─► latency = event.Timestamp - it->second.Timestamp
│   │   │   │       │       │   │       │   │
│   │   │   │       │       │   │       │   └─► [ISR DURATION] → ISR_END - ISR_START
│   │   │   │       │       │   │       │
│   │   │   │       │       │   │       └─► stats->isrLatencies.push_back(latency)
│   │   │   │       │       │   │           │
│   │   │   │       │       │   │           └─► [ISR LATENCY RECORDED]
│   │   │   │       │       │   │
│   │   │   │       │       │   └─► [ELSE] → ISR_START not found
│   │   │   │       │       │       │
│   │   │   │       │       │       └─► [NOTE] → Event lost/out of order
│   │   │   │       │       │
│   │   │   │       │       ├─► [IF event.Phase == EVT_DPC_START]
│   │   │   │       │       │   │
│   │   │   │       │       │   ├─► stats->dpcCount++
│   │   │   │       │       │   │   │
│   │   │   │       │       │   │   └─► [DPC COUNTER INCREMENTED]
│   │   │   │       │       │   │
│   │   │   │       │       │   └─► it = pendingIsrs.lower_bound({event.Vector, 0})
│   │   │   │       │       │       │
│   │   │   │       │       │       └─► [IF it != pendingIsrs.end() && it->first.vector == event.Vector]
│   │   │   │       │       │           │
│   │   │   │       │       │           ├─► latency = event.Timestamp - it->second.Timestamp
│   │   │   │       │       │           │   │
│   │   │   │       │       │           │   └─► [ISR_TO_DPC LATENCY] → DPC_START - ISR_START
│   │   │   │       │       │           │
│   │   │   │       │       │           └─► stats->endToEndLatencies.push_back(latency)
│   │   │   │       │       │               │
│   │   │   │       │       │               └─► [END-TO-END LATENCY RECORDED]
│   │   │   │       │       │
│   │   │   │       │       └─► [IF event.Phase == EVT_DPC_END]
│   │   │   │       │           │
│   │   │   │       │           └─► it = pendingIsrs.lower_bound({event.Vector, 0})
│   │   │   │       │               │
│   │   │   │       │               └─► [IF it != pendingIsrs.end() && it->first.vector == event.Vector]
│   │   │   │       │                   │
│   │   │   │       │                   ├─► latency = event.Timestamp - it->second.Timestamp
│   │   │   │       │                   │   │
│   │   │   │       │                   │   └─► [FULL END-TO-END] → DPC_END - ISR_START
│   │   │   │       │                   │
│   │   │   │       │                   └─► stats->endToEndLatencies.push_back(latency)
│   │   │   │       │                       │
│   │   │   │       │                       └─► pendingIsrs.erase(it)
│   │   │   │       │                           │
│   │   │   │       │                           └─► [PAIR COMPLETE] → Remove from map
│   │   │   │       │
│   │   │   │       └─► UpdateStatistics(*stats)
│   │   │   │           │
│   │   │   │           ├─► [IF stats->endToEndLatencies.empty()] → Skip
│   │   │   │           │   │
│   │   │   │           │   └─► [NO DATA] → Return early
│   │   │   │           │
│   │   │   │           ├─► [PERCENTILE CALCULATION]
│   │   │   │           │   │
│   │   │   │           │   ├─► sorted = stats->endToEndLatencies
│   │   │   │           │   │   │
│   │   │   │           │   │   └─► std::sort(sorted.begin(), sorted.end())
│   │   │   │           │   │
│   │   │   │           │   ├─► stats->minLatency = sorted.front()
│   │   │   │           │   ├─► stats->maxLatency = sorted.back()
│   │   │   │           │   │   │
│   │   │   │           │   │   └─► [MIN/MAX] → First and last
│   │   │   │           │   │
│   │   │   │           │   ├─► sum = std::accumulate(sorted.begin(), sorted.end(), 0.0)
│   │   │   │           │   │   │
│   │   │   │           │   │   └─► stats->avgLatency = sum / sorted.size()
│   │   │   │           │   │       │
│   │   │   │           │   │       └─► [AVERAGE] → Sum / count
│   │   │   │           │   │
│   │   │   │           │   ├─► [STANDARD DEVIATION]
│   │   │   │           │   │   │
│   │   │   │           │   │   ├─► variance = 0.0
│   │   │   │           │   │   │   │
│   │   │   │           │   │   │   └─► For each val in sorted:
│   │   │   │           │   │   │       │
│   │   │   │           │   │   │       └─► variance += (val - avgLatency)²
│   │   │   │           │   │   │           │
│   │   │   │           │   │   │           └─► [VARIANCE] → Sum of squared diffs
│   │   │   │           │   │   │
│   │   │   │           │   │   └─► stats->stdDev = sqrt(variance / sorted.size())
│   │   │   │           │   │       │
│   │   │   │           │   │       └─► [STD DEV] → sqrt(variance)
│   │   │   │           │   │
│   │   │   │           │   ├─► [PERCENTILES]
│   │   │   │           │   │   │
│   │   │   │           │   │   ├─► [IF sorted.size() > 0]
│   │   │   │           │   │   │   │
│   │   │   │           │   │   │   ├─► stats->p50 = sorted[sorted.size() * 50 / 100]
│   │   │   │           │   │   │   │   │
│   │   │   │           │   │   │   │   └─► [MEDIAN] → 50th percentile
│   │   │   │           │   │   │   │
│   │   │   │           │   │   │   ├─► stats->p95 = sorted[sorted.size() * 95 / 100]
│   │   │   │           │   │   │   │   │
│   │   │   │           │   │   │   │   └─► [P95] → 95th percentile
│   │   │   │           │   │   │   │
│   │   │   │           │   │   │   └─► stats->p99 = sorted[sorted.size() * 99 / 100]
│   │   │   │           │   │   │       │
│   │   │   │           │   │   │       └─► [P99] → 99th percentile
│   │   │   │           │   │   │
│   │   │   │           │   │   └─► [ELSE] → No data, skip percentiles
│   │   │   │           │   │
│   │   │   │           │   ├─► [EWMA UPDATE]
│   │   │   │           │   │   │
│   │   │   │           │   │   ├─► [IF stats->ewma == 0.0]
│   │   │   │           │   │   │   │
│   │   │   │           │   │   │   └─► stats->ewma = stats->avgLatency
│   │   │   │           │   │   │       │
│   │   │   │           │   │   │       └─► [INITIALIZE] → First value
│   │   │   │           │   │   │
│   │   │   │           │   │   └─► [ELSE]
│   │   │   │           │   │       │
│   │   │   │           │   │       └─► stats->ewma = alpha * avgLatency + (1 - alpha) * ewma
│   │   │   │           │   │           │
│   │   │   │           │   │           └─► [EWMA UPDATE] → Exponentially weighted
│   │   │   │           │   │
│   │   │   │           │   └─► [CUSUM ANOMALY DETECTION]
│   │   │   │           │       │
│   │   │   │           │       ├─► deviation = stats->avgLatency - stats->ewma
│   │   │   │           │       │   │
│   │   │   │           │       │   └─► [DEVIATION] → Diff from expected (EWMA)
│   │   │   │           │       │
│   │   │   │           │       ├─► stats->cusum += deviation
│   │   │   │           │       │   │
│   │   │   │           │       │   └─► [CUMULATIVE SUM] → Accumulate deviations
│   │   │   │           │       │
│   │   │   │           │       ├─► [IF stats->cusum < 0]
│   │   │   │           │       │   │
│   │   │   │           │       │   └─► stats->cusum = 0
│   │   │   │           │       │       │
│   │   │   │           │       │       └─► [RESET] → No anomaly, reset CUSUM
│   │   │   │           │       │
│   │   │   │           │       └─► stats->anomalyDetected = (stats->cusum > stats->threshold)
│   │   │   │           │           │
│   │   │   │           │           └─► [ANOMALY CHECK] → CUSUM > threshold?
│   │   │   │           │
│   │   │   │           └─► [UNLOCK] m_statsMutex.unlock()
│   │   │   │
│   │   │   └─► [EVENTS PROCESSED] → Continue to next CPU
│   │   │
│   │   └─► std::this_thread::sleep_for(100ms)
│   │       │
│   │       └─► [SLEEP] → Prevent CPU spinning
│   │
│   └─► [COLLECTION LOOP CONTINUES]
│
│
├─► [POLICY ENGINE] Anomaly Detection and Recommendations
│   │
│   ├─► PolicyEngine::Analyze(stats)
│   │   │
│   │   ├─► recommendations = std::vector<Recommendation>()
│   │   │   │
│   │   │   └─► [INITIALIZE] → Empty list
│   │   │
│   │   ├─► For each CPU (0 to stats.size()-1)
│   │   │   │
│   │   │   ├─► [HIGH LATENCY CHECK]
│   │   │   │   │
│   │   │   │   ├─► [IF stats[i].p99 > 10000] → Threshold (QPC ticks)
│   │   │   │   │   │
│   │   │   │   │   ├─► [YES] → High latency detected
│   │   │   │   │   │   │
│   │   │   │   │   │   ├─► rec.type = "High Latency"
│   │   │   │   │   │   │   ├─► rec.description = "CPU " + i + " high P99"
│   │   │   │   │   │   │   ├─► rec.action = "Increase moderation or redistribute"
│   │   │   │   │   │   │   ├─► rec.priority = 1 (High)
│   │   │   │   │   │   │   │
│   │   │   │   │   │   │   └─► recommendations.push_back(rec)
│   │   │   │   │   │   │
│   │   │   │   │   │   └─► [SOLUTION OPTIONS]
│   │   │   │   │   │       │
│   │   │   │   │   │       ├─► [OPTION 1] → Increase interrupt moderation (NDIS)
│   │   │   │   │   │       │   │
│   │   │   │   │   │       │   └─► [ACTION] → Modify NIC driver params
│   │   │   │   │   │       │
│   │   │   │   │   │       ├─► [OPTION 2] → Redistribute interrupts
│   │   │   │   │   │       │   │
│   │   │   │   │   │       │   └─► [ACTION] → Use IRQ affinity
│   │   │   │   │   │       │
│   │   │   │   │   │       └─► [OPTION 3] → Optimize MSI-X vector count
│   │   │   │   │   │           │
│   │   │   │   │   │           └─► [ACTION] → Increase/redistribute vectors
│   │   │   │   │   │
│   │   │   │   │   └─► [NO] → Latency OK
│   │   │   │   │
│   │   │   │   ├─► [CPU IMBALANCE CHECK]
│   │   │   │   │   │
│   │   │   │   │   ├─► [IF stats[i].totalEvents > 0]
│   │   │   │   │   │   │
│   │   │   │   │   │   ├─► totalEvents = sum of all stats[j].totalEvents
│   │   │   │   │   │   │   │
│   │   │   │   │   │   │   └─► [CALCULATE TOTAL] → Sum across CPUs
│   │   │   │   │   │   │
│   │   │   │   │   │   ├─► percentage = (100.0 * stats[i].totalEvents) / totalEvents
│   │   │   │   │   │   │   │
│   │   │   │   │   │   │   └─► [PERCENTAGE] → CPU's share
│   │   │   │   │   │   │
│   │   │   │   │   │   └─► [IF percentage > 50.0]
│   │   │   │   │   │       │
│   │   │   │   │   │       ├─► [YES] → CPU imbalance detected
│   │   │   │   │   │       │   │
│   │   │   │   │   │       │   ├─► rec.type = "CPU Imbalance"
│   │   │   │   │   │       │   ├─► rec.description = "CPU " + i + " handles " + percentage + "%"
│   │   │   │   │   │       │   ├─► rec.action = "Redistribute using IRQ affinity"
│   │   │   │   │   │       │   ├─► rec.priority = 2 (Medium)
│   │   │   │   │   │       │   │
│   │   │   │   │   │       │   └─► recommendations.push_back(rec)
│   │   │   │   │   │       │
│   │   │   │   │   │       └─► [SOLUTION OPTIONS]
│   │   │   │   │   │           │
│   │   │   │   │   │           ├─► [OPTION 1] → Adjust IRQ affinity
│   │   │   │   │   │           │   │
│   │   │   │   │   │           │   └─► [ACTION] → Use KeSetTargetProcessorDpc()
│   │   │   │   │   │           │
│   │   │   │   │   │           └─► [OPTION 2] → Implement irqbalance-like logic
│   │   │   │   │   │               │
│   │   │   │   │   │               └─► [ACTION] → Dynamic redistribution
│   │   │   │   │   │
│   │   │   │   │   └─► [NO] → Balanced
│   │   │   │   │
│   │   │   │   └─► [ANOMALY DETECTION CHECK]
│   │   │   │       │
│   │   │   │       └─► [IF stats[i].anomalyDetected == true]
│   │   │   │           │
│   │   │   │           ├─► [YES] → Anomaly detected by CUSUM
│   │   │   │           │   │
│   │   │   │           │   ├─► rec.type = "Anomaly Detected"
│   │   │   │           │   │   ├─► rec.description = "CPU " + i + " anomalous"
│   │   │   │           │   │   ├─► rec.action = "Investigate flooding/misconfig"
│   │   │   │           │   │   ├─► rec.priority = 1 (High)
│   │   │   │           │   │   │
│   │   │   │           │   │   └─► recommendations.push_back(rec)
│   │   │   │           │   │
│   │   │   │           │   └─► [SOLUTION OPTIONS]
│   │   │   │           │       │
│   │   │   │           │       ├─► [OPTION 1] → Check for interrupt flooding
│   │   │   │           │       │   │
│   │   │   │           │       │   └─► [ACTION] → Monitor IRQ rate, check DoS
│   │   │   │           │       │
│   │   │   │           │       ├─► [OPTION 2] → Verify driver configuration
│   │   │   │           │       │   │
│   │   │   │           │       │   └─► [ACTION] → Check moderation settings
│   │   │   │           │       │
│   │   │   │           │       └─► [OPTION 3] → Check for misconfiguration
│   │   │   │           │           │
│   │   │   │           │           └─► [ACTION] → Review system config
│   │   │   │           │
│   │   │   │           └─► [NO] → No anomaly
│   │   │   │
│   │   │   └─► [CPU ANALYSIS COMPLETE]
│   │   │
│   │   └─► [RETURN] recommendations
│   │
│   └─► [POLICY ANALYSIS COMPLETE]
│
│
├─► [OUTPUT] Statistics Display ve Export
│   │
│   ├─► PrintStatistics()
│   │   │
│   │   ├─► [LOCK] m_statsMutex.lock()
│   │   │   │
│   │   │   └─► [THREAD-SAFE ACCESS]
│   │   │
│   │   ├─► For each CPU (0 to m_processorCount-1)
│   │   │   │
│   │   │   ├─► [IF stats.totalEvents == 0] → Skip empty CPUs
│   │   │   │   │
│   │   │   │   └─► [NO DATA] → Continue to next CPU
│   │   │   │
│   │   │   ├─► [DISPLAY HEADER]
│   │   │   │   │
│   │   │   │   └─► std::cout << "CPU " << cpu << ":"
│   │   │   │
│   │   │   ├─► [DISPLAY COUNTERS]
│   │   │   │   │
│   │   │   │   ├─► Total Events
│   │   │   │   ├─► Lost Events
│   │   │   │   ├─► ISR Count
│   │   │   │   └─► DPC Count
│   │   │   │
│   │   │   ├─► [IF !stats.endToEndLatencies.empty()]
│   │   │   │   │
│   │   │   │   ├─► [CONVERT TO MICROSECONDS]
│   │   │   │   │   │
│   │   │   │   │   ├─► latencyUs = (stats.avgLatency * 1000000.0) / m_perfFreq.QuadPart
│   │   │   │   │   ├─► p95Us = (stats.p95 * 1000000.0) / m_perfFreq.QuadPart
│   │   │   │   │   └─► p99Us = (stats.p99 * 1000000.0) / m_perfFreq.QuadPart
│   │   │   │   │       │
│   │   │   │   │       └─► [CONVERSION] → QPC ticks to microseconds
│   │   │   │   │
│   │   │   │   ├─► [DISPLAY LATENCY METRICS]
│   │   │   │   │   │
│   │   │   │   │   ├─► Min, Max, Avg
│   │   │   │   │   ├─► P95, P99
│   │   │   │   │   ├─► Standard Deviation
│   │   │   │   │   └─► EWMA
│   │   │   │   │
│   │   │   │   └─► [IF stats.anomalyDetected]
│   │   │   │       │
│   │   │   │       └─► std::cout << "*** ANOMALY DETECTED ***"
│   │   │   │
│   │   │   └─► [CPU DISPLAY COMPLETE]
│   │   │
│   │   └─► [UNLOCK] m_statsMutex.unlock()
│   │
│   └─► ExportToCSV(filename)
│       │
│       ├─► [LOCK] m_statsMutex.lock()
│       │   │
│       │   └─► [THREAD-SAFE ACCESS]
│       │
│       ├─► std::ofstream file(filename)
│       │   │
│       │   ├─► [SUCCESS] → File opened
│       │   │   │
│       │   │   ├─► file << "CPU,TotalEvents,LostEvents,..."
│       │   │   │   │
│       │   │   │   └─► [CSV HEADER] → Column names
│       │   │   │
│       │   │   └─► For each CPU:
│       │   │       │
│       │   │       └─► file << cpu << "," << stats.totalEvents << ",..."
│       │   │           │
│       │   │           └─► [CSV ROW] → Statistics data
│       │   │
│       │   └─► [FAILURE] → File open failed
│       │       │
│       │       └─► [SOLUTION] → Check file path, permissions
│       │
│       └─► [EXPORT COMPLETE]
│
│
└─► [SHUTDOWN] Cleanup
    │
    ├─► [USERSPACE] Daemon Shutdown
    │   │
    │   ├─► Stop()
    │   │   │
    │   │   ├─► [IF !m_running] → Already stopped
    │   │   │   │
    │   │   │   └─► [RETURN] → No action
    │   │   │
    │   │   ├─► m_running = false
    │   │   │   │
    │   │   │   └─► [SIGNAL STOP] → Thread will exit
    │   │   │
    │   │   └─► [IF m_collectionThread.joinable()]
    │   │       │
    │   │       └─► m_collectionThread.join()
    │   │           │
    │   │           └─► [WAIT] → Thread completes
    │   │
    │   └─► CloseDevice()
    │       │
    │       └─► [IF m_deviceHandle != INVALID_HANDLE_VALUE]
    │           │
    │           └─► CloseHandle(m_deviceHandle)
    │               │
    │               └─► [DEVICE CLOSED]
    │
    └─► [KERNEL] Driver Unload
        │
        └─► [KMDF AUTOMATIC CLEANUP]
            │
            ├─► WdfObjectDelete() → Device object
            ├─► WdfObjectDelete() → Queue object
            └─► CleanupPerCpuBuffers()
                │
                └─► [IF g_PerCpuRings != NULL]
                    │
                    └─► ExFreePoolWithTag(g_PerCpuRings, 'ILMR')
                        │
                        └─► [MEMORY FREED] → All buffers deallocated
                            │
                            └─► [SHUTDOWN COMPLETE]

┌──────────────────────────────────────────────────────────────────────────┐
│                      END OF LIFECYCLE TREE                                │
└──────────────────────────────────────────────────────────────────────────┘
```
