from decimal import Decimal

from bill_split import split_evenly

def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


check("remainder to earliest shares", lambda: split_evenly("10.00", 3), ["3.34", "3.33", "3.33"])
check("even split", lambda: split_evenly("1.00", 4), ["0.25"] * 4)
check("one cent over two", lambda: split_evenly("0.05", 2), ["0.03", "0.02"])
check("sum is exact", lambda: sum(Decimal(s) for s in split_evenly("99.99", 7)), Decimal("99.99"))
check("zero total", lambda: split_evenly("0.00", 3), ["0.00"] * 3)
