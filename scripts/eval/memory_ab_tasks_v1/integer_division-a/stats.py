def average(values):
    """Arithmetic mean of values as a float."""
    return sum(values) // len(values)  # BUG: floor division truncates
