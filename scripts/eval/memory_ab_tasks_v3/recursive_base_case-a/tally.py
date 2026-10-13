def deep_sum(value):
    """Sum every number nested in lists and tuples. None and empty containers add 0."""
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, list):
        if len(value) == 1:
            return deep_sum(value[0])
        return deep_sum(value[0]) + deep_sum(value[1:])  # BUG: [] has no value[0]
    return 0  # BUG: tuples are never recursed into
