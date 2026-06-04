
def check_expiry(ttl_days: int, age_days: int) -> bool:
    return age_days > ttl_days
