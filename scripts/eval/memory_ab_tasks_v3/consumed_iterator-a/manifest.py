def summarize(parcels):
    """Return (count, total_kg, heaviest_id) for an iterable of parcel dicts.

    Each parcel has an 'id' and a 'kg' number. An empty input gives (0, 0.0, None).
    On a tie for heaviest, the first parcel wins.
    """
    count = 0
    total_kg = 0.0
    for parcel in parcels:
        count += 1
        total_kg += parcel["kg"]
    heaviest = max(parcels, key=lambda p: p["kg"], default=None)
    return count, total_kg, heaviest["id"] if heaviest else None
