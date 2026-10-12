"""Fixture service module: compute_total is the known audit symbol."""

from app.models import Item


def compute_total(items: list[Item], discount: float = 0.0) -> float:
    subtotal = sum(item.price * item.qty for item in items)
    return round(subtotal * (1.0 - discount), 2)
