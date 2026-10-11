def order_files(records):
    """Return file names oldest first. Undated files (modified None) come last.

    Files with the same date, and all undated files, are ordered by name.
    """
    ordered = sorted(records, key=lambda r: (r["modified"], r["name"]))  # BUG: None vs str
    return [r["name"] for r in ordered]
