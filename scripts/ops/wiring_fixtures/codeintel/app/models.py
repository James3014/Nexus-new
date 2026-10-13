"""Fixture model module for the codeintel wiring audit."""


class Item:
    def __init__(self, name: str, price: float, qty: int = 1) -> None:
        self.name = name
        self.price = price
        self.qty = qty
