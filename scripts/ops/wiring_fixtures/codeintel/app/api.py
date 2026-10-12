"""Fixture api module: the only caller of compute_total."""

from app.models import Item
from app.service import compute_total


def checkout(prices: list[float]) -> float:
    return compute_total([Item(f"i{idx}", price) for idx, price in enumerate(prices)])
