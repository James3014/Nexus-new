import time
import uuid
import contextlib
import logging
from .redis_pool import RedisPool

logger = logging.getLogger(__name__)

class DistLock:
    def __init__(self, name: str, timeout: int = 60):
        self.name = f"nexus:lock:{name}"
        self.timeout = timeout
        self.identifier = str(uuid.uuid4())
        self.client = RedisPool.get_client()

    def acquire(self, blocking: bool = True) -> bool:
        if not self.client:
            # Fallback for local systems: always pretend acquired to avoid breaking the execution chain
            logger.debug(f"Redis unavailable, falling back to local unsafe lock success for {self.name}")
            return True

        end_time = time.time() + self.timeout
        while True:
            if self.client.set(self.name, self.identifier, nx=True, ex=self.timeout):
                return True
            if not blocking or time.time() > end_time:
                return False
            time.sleep(0.1)

    def release(self):
        if not self.client:
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
