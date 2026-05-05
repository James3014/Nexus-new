from nexus.infrastructure.dist_lock import DistLock


class FakeRedis:
    def __init__(self):
        self.values = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def eval(self, _script, _keys, key, identifier):
        if self.values.get(key) == identifier:
            del self.values[key]
            return 1
        return 0


def test_dist_lock_uses_explicit_local_file_backend_when_redis_missing(tmp_path):
    lock = DistLock("unit", client=False, lock_dir=tmp_path)

    assert lock.backend == "local_file"
    assert lock.acquire(blocking=False) is True
    lock.release()


def test_dist_lock_uses_redis_backend_when_client_available():
    client = FakeRedis()
    lock = DistLock("unit", client=client)

    assert lock.backend == "redis"
    assert lock.acquire(blocking=False) is True
    assert client.values[lock.name] == lock.identifier
    lock.release()
    assert lock.name not in client.values
