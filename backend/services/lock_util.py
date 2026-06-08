import os
import time
import contextlib

try:
    import fcntl
except ImportError:
    fcntl = None

try:
    import msvcrt
except ImportError:
    msvcrt = None


class ProcessFileLock:
    """
    A process-level file lock that automatically releases when the process dies
    or the file descriptor/handle is closed.
    Uses fcntl on Unix (inside Docker) and msvcrt on Windows.
    """
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.fd = None

    def acquire(self) -> bool:
        try:
            # Ensure the directory exists
            parent_dir = os.path.dirname(self.filepath)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
                
            self.fd = os.open(self.filepath, os.O_CREAT | os.O_WRONLY)
            if fcntl:
                # Unix non-blocking exclusive lock
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            elif msvcrt:
                # Windows non-blocking lock on 1 byte
                msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)
                return True
        except (IOError, OSError):
            self.close()
            return False
        return False

    def release(self):
        self.close()

    def close(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except Exception:
                pass
            self.fd = None


@contextlib.contextmanager
def file_lock(lock_path: str, timeout: float = 10.0):
    """
    A simple directory-creation-based lock (atomic on Unix and Windows).
    Suitable for short-lived thread/process-safe operations (e.g. updating a cache file).
    Automatically cleans up on completion.
    """
    lock_dir = lock_path + ".lockdir"
    
    # Ensure the parent directory exists
    parent_dir = os.path.dirname(lock_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
        
    start_time = time.time()
    acquired = False
    while time.time() - start_time < timeout:
        try:
            os.makedirs(lock_dir)
            acquired = True
            break
        except FileExistsError:
            time.sleep(0.05)
    
    try:
        yield acquired
    finally:
        if acquired:
            try:
                os.rmdir(lock_dir)
            except OSError:
                pass
