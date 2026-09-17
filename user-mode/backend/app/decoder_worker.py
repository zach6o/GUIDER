"""One image per resource-limited process. No credentials are inherited."""

import ctypes
import json
import os
import sys
from pathlib import Path

MEMORY = 512 * 1024 * 1024


def limits():
    if os.name != "nt":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (MEMORY, MEMORY))
        resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
        return None
    from ctypes import wintypes as w

    class Basic(ctypes.Structure):
        _fields_ = [
            ("process_time", ctypes.c_longlong),
            ("job_time", ctypes.c_longlong),
            ("flags", w.DWORD),
            ("min_working", ctypes.c_size_t),
            ("max_working", ctypes.c_size_t),
            ("active", w.DWORD),
            ("affinity", ctypes.c_size_t),
            ("priority", w.DWORD),
            ("scheduling", w.DWORD),
        ]

    class Extended(ctypes.Structure):
        _fields_ = [
            ("basic", Basic),
            ("io", ctypes.c_ulonglong * 6),
            ("process_memory", ctypes.c_size_t),
            ("job_memory", ctypes.c_size_t),
            ("peak_process", ctypes.c_size_t),
            ("peak_job", ctypes.c_size_t),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    job = kernel.CreateJobObjectW(None, None)
    info = Extended()
    info.basic.flags = 0x2 | 0x8 | 0x100  # process CPU, one process, committed memory
    info.basic.process_time = 5 * 10_000_000
    info.basic.active = 1
    info.process_memory = MEMORY
    if not job or not kernel.SetInformationJobObject(
        job, 9, ctypes.byref(info), ctypes.sizeof(info)
    ):
        raise OSError("Decoder limits unavailable")
    if not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()):
        raise OSError("Decoder isolation unavailable")
    return job


def main():
    job = limits()  # retained until process exit
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.errors import GuideError
    from app.media import MAX_BYTES, normalize

    try:
        clean = normalize(sys.stdin.buffer.read(MAX_BYTES + 1))
        header = json.dumps({"width": clean.width, "height": clean.height}).encode()
        sys.stdout.buffer.write(header + b"\n" + clean.pixels)
    except GuideError as error:
        sys.stdout.buffer.write(json.dumps({"status": error.status, **error.body}).encode())
        return 2
    except (MemoryError, OSError, ValueError):
        return 3
    del job
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
