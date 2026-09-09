#
# Driver Interface Module
# Wrapper for communication with the Windows driver
#

import ctypes
from ctypes import wintypes, Structure, POINTER, byref
import struct

# Windows API constants
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x80
INVALID_HANDLE_VALUE = -1

# IOCTL codes (must match driver)
FILE_DEVICE_UNKNOWN = 0x00000022
METHOD_BUFFERED = 0
FILE_ANY_ACCESS = 0

def CTL_CODE(DeviceType, Function, Method, Access):
    return (DeviceType << 16) | (Access << 14) | (Function << 2) | Method

IOCTL_BASE = 0x8000
IOCTL_GET_EVENTS = CTL_CODE(FILE_DEVICE_UNKNOWN, IOCTL_BASE + 0x01, METHOD_BUFFERED, FILE_ANY_ACCESS)
IOCTL_GET_STATISTICS = CTL_CODE(FILE_DEVICE_UNKNOWN, IOCTL_BASE + 0x02, METHOD_BUFFERED, FILE_ANY_ACCESS)
IOCTL_RESET_BUFFERS = CTL_CODE(FILE_DEVICE_UNKNOWN, IOCTL_BASE + 0x03, METHOD_BUFFERED, FILE_ANY_ACCESS)
IOCTL_SET_CONFIG = CTL_CODE(FILE_DEVICE_UNKNOWN, IOCTL_BASE + 0x04, METHOD_BUFFERED, FILE_ANY_ACCESS)

# Windows API functions
kernel32 = ctypes.windll.kernel32

kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.LPVOID,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE
]
kernel32.CreateFileW.restype = wintypes.HANDLE

kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

kernel32.DeviceIoControl.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPVOID,
    wintypes.DWORD,
    wintypes.LPVOID,
    wintypes.DWORD,
    POINTER(wintypes.DWORD),
    wintypes.LPVOID
]
kernel32.DeviceIoControl.restype = wintypes.BOOL

kernel32.GetLastError.argtypes = []
kernel32.GetLastError.restype = wintypes.DWORD

# Structures
class LARGE_INTEGER(Structure):
    _fields_ = [("QuadPart", ctypes.c_longlong)]

class IRQ_EVENT(Structure):
    _fields_ = [
        ("Vector", ctypes.c_ushort),
        ("Cpu", ctypes.c_ubyte),
        ("Phase", ctypes.c_ubyte),
        ("QueueDepth", ctypes.c_ulong),
        ("Timestamp", LARGE_INTEGER),
        ("TscValue", ctypes.c_ulonglong),
        ("SequenceId", ctypes.c_ulonglong)  # Monotonic sequence number for lost event detection
    ]
    _pack_ = 1

class IOCTL_GET_EVENTS_IN(Structure):
    _fields_ = [
        ("CpuNumber", ctypes.c_ulong),
        ("MaxEvents", ctypes.c_ulong),
        ("StartIndex", ctypes.c_ulong)
    ]

class IOCTL_GET_EVENTS_OUT(Structure):
    _fields_ = [
        ("EventCount", ctypes.c_ulong),
        ("Events", IRQ_EVENT * 1000)  # Variable length, max 1000
    ]

class IOCTL_STATISTICS(Structure):
    _fields_ = [
        ("CpuNumber", ctypes.c_ulong),
        ("TotalEvents", ctypes.c_ulonglong),
        ("LostEvents", ctypes.c_ulonglong),
        ("MinLatency", ctypes.c_longlong),
        ("MaxLatency", ctypes.c_longlong),
        ("AvgLatency", ctypes.c_longlong),
        ("P95Latency", ctypes.c_longlong),
        ("P99Latency", ctypes.c_longlong),
        ("IsrCount", ctypes.c_ulonglong),
        ("DpcCount", ctypes.c_ulonglong)
    ]

class IOCTL_CONFIG(Structure):
    _fields_ = [
        ("EnableInstrumentation", wintypes.BOOL),
        ("UseRdtsc", wintypes.BOOL),
        ("SamplingRate", ctypes.c_ulong)
    ]


class DriverInterface:
    """Interface for communication with the Windows driver"""
    
    def __init__(self):
        self.handle = INVALID_HANDLE_VALUE
        self.device_path = r"\\.\InterruptLatencyMonitor"
        self.connected = False
        
    def connect(self):
        """Connect to the driver"""
        try:
            self.handle = kernel32.CreateFileW(
                self.device_path,
                GENERIC_READ | GENERIC_WRITE,
                0,
                None,
                OPEN_EXISTING,
                FILE_ATTRIBUTE_NORMAL,
                None
            )
            
            if self.handle == INVALID_HANDLE_VALUE:
                error = kernel32.GetLastError()
                raise Exception(f"Failed to open device. Error: {error}")
            
            self.connected = True
            return True
        except Exception as e:
            print(f"Connection error: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Close the driver connection"""
        if self.handle != INVALID_HANDLE_VALUE:
            kernel32.CloseHandle(self.handle)
            self.handle = INVALID_HANDLE_VALUE
            self.connected = False
    
    def get_events(self, cpu_number, max_events=1000, start_index=0):
        """Fetch events from a CPU"""
        if not self.connected:
            return []
        
        try:
            input_data = IOCTL_GET_EVENTS_IN()
            input_data.CpuNumber = cpu_number
            input_data.MaxEvents = max_events
            input_data.StartIndex = start_index
            
            output_size = ctypes.sizeof(IOCTL_GET_EVENTS_OUT)
            output_data = IOCTL_GET_EVENTS_OUT()
            bytes_returned = wintypes.DWORD()
            
            success = kernel32.DeviceIoControl(
                self.handle,
                IOCTL_GET_EVENTS,
                byref(input_data),
                ctypes.sizeof(input_data),
                byref(output_data),
                output_size,
                byref(bytes_returned),
                None
            )
            
            if not success:
                error = kernel32.GetLastError()
                raise Exception(f"DeviceIoControl failed. Error: {error}")
            
            events = []
            for i in range(output_data.EventCount):
                event = output_data.Events[i]
                events.append({
                    'vector': event.Vector,
                    'cpu': event.Cpu,
                    'phase': event.Phase,
                    'queue_depth': event.QueueDepth,
                    'timestamp': event.Timestamp.QuadPart,
                    'tsc_value': event.TscValue,
                    'sequence_id': event.SequenceId  # Monotonic sequence ID for lost event detection
                })
            
            return events
        except Exception as e:
            print(f"Get events error: {e}")
            return []
    
    def get_statistics(self, cpu_number):
        """Fetch statistics for a CPU"""
        if not self.connected:
            return None
        
        try:
            output_data = IOCTL_STATISTICS()
            bytes_returned = wintypes.DWORD()
            
            success = kernel32.DeviceIoControl(
                self.handle,
                IOCTL_GET_STATISTICS,
                None,
                0,
                byref(output_data),
                ctypes.sizeof(output_data),
                byref(bytes_returned),
                None
            )
            
            if not success:
                error = kernel32.GetLastError()
                raise Exception(f"DeviceIoControl failed. Error: {error}")
            
            return {
                'cpu_number': output_data.CpuNumber,
                'total_events': output_data.TotalEvents,
                'lost_events': output_data.LostEvents,
                'min_latency': output_data.MinLatency,
                'max_latency': output_data.MaxLatency,
                'avg_latency': output_data.AvgLatency,
                'p95_latency': output_data.P95Latency,
                'p99_latency': output_data.P99Latency,
                'isr_count': output_data.IsrCount,
                'dpc_count': output_data.DpcCount
            }
        except Exception as e:
            print(f"Get statistics error: {e}")
            return None
    
    def set_config(self, enable_instrumentation=True, use_rdtsc=False, sampling_rate=1):
        """Set driver configuration"""
        if not self.connected:
            return False
        
        try:
            config = IOCTL_CONFIG()
            config.EnableInstrumentation = enable_instrumentation
            config.UseRdtsc = use_rdtsc
            config.SamplingRate = sampling_rate
            
            bytes_returned = wintypes.DWORD()
            
            success = kernel32.DeviceIoControl(
                self.handle,
                IOCTL_SET_CONFIG,
                byref(config),
                ctypes.sizeof(config),
                None,
                0,
                byref(bytes_returned),
                None
            )
            
            if not success:
                error = kernel32.GetLastError()
                raise Exception(f"DeviceIoControl failed. Error: {error}")
            
            return True
        except Exception as e:
            print(f"Set config error: {e}")
            return False
    
    def reset_buffers(self):
        """Reset ring buffers"""
        if not self.connected:
            return False
        
        try:
            bytes_returned = wintypes.DWORD()
            
            success = kernel32.DeviceIoControl(
                self.handle,
                IOCTL_RESET_BUFFERS,
                None,
                0,
                None,
                0,
                byref(bytes_returned),
                None
            )
            
            if not success:
                error = kernel32.GetLastError()
                raise Exception(f"DeviceIoControl failed. Error: {error}")
            
            return True
        except Exception as e:
            print(f"Reset buffers error: {e}")
            return False

