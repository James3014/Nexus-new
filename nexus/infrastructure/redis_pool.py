import os
import logging

logger = logging.getLogger(__name__)

class RedisPool:
    _pool = None

    @classmethod
    def get_client(cls):
        try:
            import redis
            if cls._pool is None:
                host = os.getenv("REDIS_HOST", "localhost")
                port = int(os.getenv("REDIS_PORT", 6379))
                cls._pool = redis.ConnectionPool(host=host, port=port, db=0, decode_responses=True)
            return redis.Redis(connection_pool=cls._pool)
        except ImportError:
            # Redis is not installed, fail gracefully to Local State
            return None
