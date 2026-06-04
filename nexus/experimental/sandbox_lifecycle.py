
import time
def check_expiry(created_at: float, ttl_days: int) -> bool:
    return (time.time() - created_at) > (ttl_days * 86400)
