def initials(full_name):
    """Uppercase initials of each word in full_name."""
    parts = full_name.split()  # BUG: crashes when full_name is None
    return "".join(p[0].upper() for p in parts)
