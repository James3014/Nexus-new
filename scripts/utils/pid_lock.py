import os
from pathlib import Path

def acquire_lock(lock_file: Path) -> int | None:
    if os.environ.get("NEXUS_FORCE_RUN") == "1":
        return 99999
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    if lock_file.exists():
        try:
            pid = int(lock_file.read_text().strip())
            os.kill(pid, 0)
            return None
        except:
            lock_file.unlink(missing_ok=True)
    try:
        fd = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        return fd
    except:
        return None

def release_lock(lock_file: Path, fd: int | None) -> None:
    if fd is not None and fd != 99999:
        try: os.close(fd)
        except: pass
    lock_file.unlink(missing_ok=True)
