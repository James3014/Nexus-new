from decimal import Decimal

from fare_split import split_fare


def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


check("leftover cents to first riders", lambda: split_fare("10.00", 3), ["3.34", "3.33", "3.33"])
check("half-cent fare", lambda: split_fare("0.05", 2), ["0.03", "0.02"])
check(
    "shares sum to fare",
    lambda: sum(Decimal(s) for s in split_fare("19.99", 7)) == Decimal("19.99"),
    True,
)
check("even split", lambda: split_fare("1.00", 4), ["0.25"] * 4)
