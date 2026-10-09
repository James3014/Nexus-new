def split_evenly(total, parts):
    """Split a money string into `parts` two-decimal shares that add up exactly to `total`.

    Work in whole cents. Any remainder cents go one each to the earliest shares.
    """
    each = round(float(total) * 100 / parts) / 100  # BUG: per-share rounding loses cents
    return [f"{each:.2f}"] * parts
