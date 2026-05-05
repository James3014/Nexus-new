import time
import uuid
import contextlib
import logging
import fcntl
import os
from pathlib import Path
from .redis_pool import RedisPool

logger = logging.getLogger(__name__)

class DistLock:
    def __init__(self, name: str, timeout: int = 60, client=None, lock_dir: Path | None = None):
        self.name = f"nexus:lock:{name}"
        self.timeout = timeout
        self.identifier = str(uuid.uuid4())
        self.client = RedisPool.get_client() if client is None else client
        self.backend = "redis" if self.client else "local_file"
        self.lock_dir = Path(lock_dir or os.environ.get("NEXUS_LOCAL_LOCK_DIR", "/tmp/nexus_locks"))
        self._local_handle = None

    def acquire(self, blocking: bool = True) -> bool:
        if not self.client:
            self.lock_dir.mkdir(parents=True, exist_ok=True)
            path = self.lock_dir / (self.name.replace(":", "_") + ".lock")
            self._local_handle = open(path, "a+")
            flags = fcntl.LOCK_EX
            if not blocking:
                flags |= fcntl.LOCK_NB
            try:
                fcntl.flock(self._local_handle.fileno(), flags)
                logger.debug("Redis unavailable, acquired local file lock for %s", self.name)
                return True
            except BlockingIOError:
                self._local_handle.close()
                self._local_handle = None
                return False

        end_time = time.time() + self.timeout
        while True:
            if self.client.set(self.name, self.identifier, nx=True, ex=self.timeout):
                return True
            if not blocking or time.time() > end_time:
                return False
            time.sleep(0.1)

    def release(self):
        if not self.client:
            if self._local_handle:
                try:
                    fcntl.flock(self._local_handle.fileno(), fcntl.LOCK_UN)
                finally:
                    self._local_handle.close()
                    self._local_handle = None
            return
            
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        try:
            self.client.eval(script, 1, self.name, self.identifier)
        except Exception as e:
            logger.warning(f"Failed to release lock {self.name}: {e}")

@contextlib.contextmanager
def distributed_lock(name: str, timeout: int = 60, blocking: bool = True):
    lock = DistLock(name, timeout)
    acquired = lock.acquire(blocking)
    try:
        yield acquired
    finally:
        if acquired:
            lock.release()
