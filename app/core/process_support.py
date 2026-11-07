"""Platform-specific lifetime and advisory lock helpers."""
import os
import sys

def acquire_lock(path):
    handle=path.open('a+b')
    if sys.platform=='win32':
        import msvcrt
        handle.seek(0);handle.write(b'0');handle.flush();handle.seek(0)
        try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:handle.close();raise BlockingIOError('Collector already running')
    else:
        import fcntl
        try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:handle.close();raise
    return handle


def parent_alive(pid):
    if sys.platform!='win32':return os.getppid()==pid
    import ctypes as C
    kernel=C.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[C.c_uint32,C.c_int,C.c_uint32];kernel.OpenProcess.restype=C.c_void_p
    kernel.WaitForSingleObject.argtypes=[C.c_void_p,C.c_uint32];kernel.WaitForSingleObject.restype=C.c_uint32
    kernel.CloseHandle.argtypes=[C.c_void_p]
    handle=kernel.OpenProcess(0x100000,False,pid)
    if not handle:return False
    try:return kernel.WaitForSingleObject(handle,0)==258
    finally:kernel.CloseHandle(handle)
