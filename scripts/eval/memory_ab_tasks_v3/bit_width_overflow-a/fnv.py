FNV_OFFSET_BASIS = 2166136261
FNV_PRIME = 16777619


def fnv1a32(data):
    """Return the 32-bit FNV-1a hash of bytes data as an unsigned int (0 .. 2**32 - 1)."""
    h = FNV_OFFSET_BASIS
    for byte in data:
        h ^= byte
        h *= FNV_PRIME  # BUG: never wrapped to 32 bits
    return h
