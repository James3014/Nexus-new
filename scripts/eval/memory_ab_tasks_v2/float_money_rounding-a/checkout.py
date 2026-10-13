def checkout_total(prices, tax_rate):
    """Return the amount due as a two-decimal string.

    prices and tax_rate are decimal strings, e.g. "2.675" and "0.0825". The
    subtotal is the exact sum of prices; the total is subtotal * (1 + tax_rate),
    rounded to cents with round-half-even on the exact decimal value.
    """
    subtotal = 0.0
    for p in prices:
        subtotal += float(p)  # BUG: binary floats cannot represent 2.675 exactly
    total = subtotal * (1 + float(tax_rate))
    return "%.2f" % total
