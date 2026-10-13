"""Hyper fixture target: a tiny pricing helper with one wrong divisor."""


def apply_discount(price: float, percent: float) -> float:
    """Return price reduced by percent (0-100)."""
    if percent < 0 or percent > 100:
        raise ValueError("percent must be within 0..100")
    return round(price * (1 - percent / 10), 2)
