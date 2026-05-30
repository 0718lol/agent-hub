import sys
import asyncio
import ctypes
import logging

logger = logging.getLogger("subprocess_security")

# ---- Windows Job Objects Declarations ----
JOBOBJECT_EXTENDED_LIMIT_INFORMATION = 9
JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200

# We declare wintypes locally or conditionally to support clean imports on Unix
if sys.platform == "win32":
    from ctypes import wintypes
    
    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION_STRUCT(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]
else:
    # Stand-in classes for non-Windows compilation safety
    class IO_COUNTERS: pass
    class JOBOBJECT_BASIC_LIMIT_INFORMATION: pass
    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION_STRUCT: pass

_windows_job_handles = set()


def limit_windows_process(pid: int, memory_limit_bytes: int) -> bool:
    """Utilizes Windows Job Objects to strictly constrain the virtual/physical memory limit of the target process."""
    if sys.platform != "win32":
        return False

    try:
        kernel32 = ctypes.windll.kernel32
        
        # 1. Create Job Object container
        h_job = kernel32.CreateJobObjectW(None, None)
        if not h_job:
            return False
            
        # 2. Open process handle with quota and termination access
        PROCESS_SET_QUOTA = 0x0100
        PROCESS_TERMINATE = 0x0001
        h_process = kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, pid)
        if not h_process:
            kernel32.CloseHandle(h_job)
            return False
            
        # 3. Populate Extended Limit structures
        limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION_STRUCT()
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_PROCESS_MEMORY | JOB_OBJECT_LIMIT_JOB_MEMORY
        limits.ProcessMemoryLimit = memory_limit_bytes
        limits.JobMemoryLimit = memory_limit_bytes
        
        res = kernel32.SetInformationJobObject(
            h_job,
            JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits)
        )
        if not res:
            kernel32.CloseHandle(h_process)
            kernel32.CloseHandle(h_job)
            return False
            
        # 4. Securely assign process to Job Object container
        assigned = kernel32.AssignProcessToJobObject(h_job, h_process)
        kernel32.CloseHandle(h_process)
        
        if assigned:
            _windows_job_handles.add(h_job)
        else:
            kernel32.CloseHandle(h_job)
        return bool(assigned)
    except Exception as e:
        logger.error(f"[Subprocess Security] Failed to apply memory limit to Windows pid {pid}: {e}")
        return False


async def safe_terminate_process_tree(proc: asyncio.subprocess.Process):
    """Teardown standard processes and child subprocesses cleanly across platforms."""
    if not proc:
        return
    try:
        if sys.platform == "win32":
            # Windows: forcefully kill the entire subprocess tree using taskkill
            kill_proc = await asyncio.create_subprocess_exec(
                "taskkill", "/F", "/T", "/PID", str(proc.pid),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=0x08000000  # CREATE_NO_WINDOW
            )
            try:
                await asyncio.wait_for(kill_proc.communicate(), timeout=2.0)
            except Exception:
                pass
        else:
            # Unix: kill single process
            proc.kill()
        await proc.wait()
    except Exception as e:
        logger.warning(f"[Subprocess Security] Failed process tree termination for pid {proc.pid}: {e}")
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
