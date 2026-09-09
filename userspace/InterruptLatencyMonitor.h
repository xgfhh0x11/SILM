//
// Interrupt Latency Monitor — user-mode header.
//
// Wire-format types (IRQ_EVENT, IOCTL codes, IOCTL_* request/response
// structures) live in ../shared/InterruptLatencyMonitor_abi.h and are
// shared verbatim with the kernel driver. Do not duplicate them here.
//

#pragma once

#include <windows.h>
#include <winioctl.h>   // CTL_CODE, METHOD_BUFFERED, FILE_DEVICE_UNKNOWN

#include "../shared/InterruptLatencyMonitor_abi.h"

// FIELD_OFFSET is normally supplied by <ntdef.h> / <winnt.h>; keep
// this fallback for tool-chains that don't expose it through
// <windows.h>.
#ifndef FIELD_OFFSET
#define FIELD_OFFSET(type, field) ((LONG)(LONG_PTR)&(((type *)0)->field))
#endif
