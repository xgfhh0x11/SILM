//
// Interrupt Latency Monitor - Userspace Trace Recorder
//
// This binary is a thin trace recorder: it opens the kernel device, enables
// instrumentation, drains per-CPU event rings via IOCTL_GET_EVENTS, and writes
// the raw event stream to a binary trace file. All analytics (percentiles,
// EWMA, CUSUM, policy) live in the Python GUI (gui/) to keep a single source
// of truth for statistical computation.
//
// Trace file format:
//   silm_trace_header  (32 bytes)
//   { silm_trace_record } *  (variable-length stream)
//

#include <windows.h>
#include <iostream>
#include <vector>
#include <fstream>
#include <chrono>
#include <thread>
#include <mutex>
#include <atomic>
#include <cstdint>

#include "InterruptLatencyMonitor.h"

// On-disk format (packed for stable binary layout)
#pragma pack(push, 1)
struct silm_trace_header {
    char     magic[4];           // 'S','I','L','M'
    uint32_t version;            // 1
    uint64_t qpc_frequency;      // QueryPerformanceFrequency value
    uint32_t cpu_count;          // number of CPUs being recorded
    uint32_t reserved;           // zero
    uint64_t start_time_qpc;     // QPC counter at recording start
};

struct silm_trace_record {
    uint32_t  cpu;               // source CPU (matches event.Cpu, kept for trace integrity)
    IRQ_EVENT event;             // raw event as delivered by the kernel
};
#pragma pack(pop)

class InterruptLatencyDaemon {
private:
    static constexpr ULONG kMaxEventsPerRead = 1000;

    HANDLE          m_deviceHandle;
    ULONG           m_processorCount;
    std::atomic<bool> m_running;
    std::thread     m_collectionThread;
    LARGE_INTEGER   m_perfFreq;

    std::ofstream   m_traceFile;
    std::mutex      m_traceMutex;
    std::atomic<uint64_t> m_recordsWritten;
    std::atomic<uint64_t> m_lostEventsTotal;

    // Configuration
    bool            m_enableRdtsc;
    ULONG           m_samplingRate;

public:
    InterruptLatencyDaemon()
        : m_deviceHandle(INVALID_HANDLE_VALUE)
        , m_processorCount(0)
        , m_running(false)
        , m_recordsWritten(0)
        , m_lostEventsTotal(0)
        , m_enableRdtsc(false)
        , m_samplingRate(1)
    {
        QueryPerformanceFrequency(&m_perfFreq);
    }

    ~InterruptLatencyDaemon() {
        Stop();
        CloseTraceFile();
        CloseDevice();
    }

    bool Initialize(const std::string& tracePath) {
        if (!OpenDevice()) {
            std::cerr << "Failed to open device" << std::endl;
            return false;
        }

        SYSTEM_INFO sysInfo;
        GetSystemInfo(&sysInfo);
        m_processorCount = sysInfo.dwNumberOfProcessors;

        IOCTL_CONFIG config = {};
        config.EnableInstrumentation = TRUE;
        config.UseRdtsc              = m_enableRdtsc;
        config.SamplingRate          = m_samplingRate;

        DWORD bytesReturned;
        if (!DeviceIoControl(m_deviceHandle, IOCTL_SET_CONFIG,
                             &config, sizeof(config),
                             NULL, 0, &bytesReturned, NULL)) {
            std::cerr << "Failed to set driver configuration (err="
                      << GetLastError() << ")" << std::endl;
            return false;
        }

        if (!OpenTraceFile(tracePath)) {
            return false;
        }

        return true;
    }

    void Start() {
        if (m_running.exchange(true)) {
            return;
        }
        m_collectionThread = std::thread(&InterruptLatencyDaemon::CollectionLoop, this);
    }

    void Stop() {
        if (!m_running.exchange(false)) {
            return;
        }
        if (m_collectionThread.joinable()) {
            m_collectionThread.join();
        }
    }

    void PrintSummary() const {
        std::cout << "\n=== Recording Summary ===" << std::endl;
        std::cout << "  QPC frequency : " << m_perfFreq.QuadPart << " Hz" << std::endl;
        std::cout << "  CPUs recorded : " << m_processorCount << std::endl;
        std::cout << "  Records written: " << m_recordsWritten.load() << std::endl;
        std::cout << "  Lost events    : " << m_lostEventsTotal.load() << std::endl;
    }

private:
    bool OpenDevice() {
        m_deviceHandle = CreateFileW(
            L"\\\\.\\InterruptLatencyMonitor",
            GENERIC_READ | GENERIC_WRITE,
            0, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
        return m_deviceHandle != INVALID_HANDLE_VALUE;
    }

    void CloseDevice() {
        if (m_deviceHandle != INVALID_HANDLE_VALUE) {
            CloseHandle(m_deviceHandle);
            m_deviceHandle = INVALID_HANDLE_VALUE;
        }
    }

    bool OpenTraceFile(const std::string& path) {
        m_traceFile.open(path, std::ios::out | std::ios::binary | std::ios::trunc);
        if (!m_traceFile.is_open()) {
            std::cerr << "Failed to open trace file: " << path << std::endl;
            return false;
        }

        LARGE_INTEGER startQpc;
        QueryPerformanceCounter(&startQpc);

        silm_trace_header hdr{};
        hdr.magic[0] = 'S'; hdr.magic[1] = 'I'; hdr.magic[2] = 'L'; hdr.magic[3] = 'M';
        hdr.version       = 1;
        hdr.qpc_frequency = static_cast<uint64_t>(m_perfFreq.QuadPart);
        hdr.cpu_count     = m_processorCount;
        hdr.reserved      = 0;
        hdr.start_time_qpc = static_cast<uint64_t>(startQpc.QuadPart);

        m_traceFile.write(reinterpret_cast<const char*>(&hdr), sizeof(hdr));
        m_traceFile.flush();
        std::cout << "Recording to " << path << std::endl;
        return true;
    }

    void CloseTraceFile() {
        std::lock_guard<std::mutex> lock(m_traceMutex);
        if (m_traceFile.is_open()) {
            m_traceFile.flush();
            m_traceFile.close();
        }
    }

    void CollectionLoop() {
        std::vector<IRQ_EVENT> events;
        events.reserve(kMaxEventsPerRead);

        while (m_running.load()) {
            for (ULONG cpu = 0; cpu < m_processorCount; cpu++) {
                if (!m_running.load()) break;
                CollectEventsFromCpu(cpu, events);
                if (!events.empty()) {
                    WriteEventsToTrace(cpu, events);
                }
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
    }

    void CollectEventsFromCpu(ULONG cpu, std::vector<IRQ_EVENT>& events) {
        events.clear();

        IOCTL_GET_EVENTS_IN input = {};
        input.CpuNumber  = cpu;
        input.MaxEvents  = kMaxEventsPerRead;
        input.StartIndex = 0;

        const size_t outputSize = FIELD_OFFSET(IOCTL_GET_EVENTS_OUT, Events)
                                + (kMaxEventsPerRead * sizeof(IRQ_EVENT));
        std::vector<BYTE> outputBuffer(outputSize);
        PIOCTL_GET_EVENTS_OUT output = reinterpret_cast<PIOCTL_GET_EVENTS_OUT>(outputBuffer.data());

        DWORD bytesReturned = 0;
        if (!DeviceIoControl(m_deviceHandle, IOCTL_GET_EVENTS,
                             &input, sizeof(input),
                             output, static_cast<DWORD>(outputSize),
                             &bytesReturned, NULL)) {
            return;
        }

        events.assign(output->Events, output->Events + output->EventCount);
    }

    void WriteEventsToTrace(ULONG cpu, const std::vector<IRQ_EVENT>& events) {
        std::lock_guard<std::mutex> lock(m_traceMutex);
        if (!m_traceFile.is_open()) {
            return;
        }

        uint64_t lastSeq = 0;
        bool seenSeq = false;
        for (const auto& ev : events) {
            // Detect lost-event gaps in the per-CPU monotonic sequence.
            if (seenSeq && ev.SequenceId > lastSeq + 1) {
                m_lostEventsTotal.fetch_add(ev.SequenceId - lastSeq - 1);
            }
            lastSeq = ev.SequenceId;
            seenSeq = true;

            silm_trace_record rec{};
            rec.cpu   = cpu;
            rec.event = ev;
            m_traceFile.write(reinterpret_cast<const char*>(&rec), sizeof(rec));
            m_recordsWritten.fetch_add(1);
        }
    }
};

static std::string DefaultTracePath() {
    using clock = std::chrono::system_clock;
    const auto t = clock::to_time_t(clock::now());
    char buf[32];
    std::tm tm{};
    localtime_s(&tm, &t);
    std::strftime(buf, sizeof(buf), "%Y%m%d_%H%M%S", &tm);
    return std::string("silm_trace_") + buf + ".bin";
}

int main(int argc, char* argv[]) {
    std::cout << "SILM Trace Recorder" << std::endl;
    std::cout << "===================" << std::endl;

    const std::string tracePath = (argc > 1) ? argv[1] : DefaultTracePath();

    InterruptLatencyDaemon daemon;
    if (!daemon.Initialize(tracePath)) {
        std::cerr << "Failed to initialize daemon" << std::endl;
        return 1;
    }

    daemon.Start();
    std::cout << "Recording. Press Enter to stop." << std::endl;
    std::cin.get();

    daemon.Stop();
    daemon.PrintSummary();
    return 0;
}
