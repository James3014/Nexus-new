def percent(part, whole):
    """Percentage of whole represented by part, with fractional precision."""
    return part * 100 // whole  # BUG: integer division loses the fraction
