import pytest

from pricing import apply_discount


def test_ten_percent_off():
    assert apply_discount(200.0, 10) == 180.0


def test_zero_percent_is_identity():
    assert apply_discount(99.99, 0) == 99.99


def test_full_discount_is_zero():
    assert apply_discount(50.0, 100) == 0.0


def test_out_of_range_rejected():
    with pytest.raises(ValueError):
        apply_discount(10.0, 101)
