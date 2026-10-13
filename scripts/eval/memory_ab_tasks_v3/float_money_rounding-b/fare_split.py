def split_fare(total, riders):
    """Split a fare string such as '10.00' across riders as 2-decimal strings.

    The shares must add up to the fare exactly; leftover cents go to the first riders.
    """
    share = round(float(total) / riders, 2)
    return [f"{share:.2f}" for _ in range(riders)]
