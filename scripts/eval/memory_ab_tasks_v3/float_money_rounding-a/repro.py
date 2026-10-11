from invoice import invoice_total


def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


# Tax 0.015 rounds half-to-even to 0.02, so the total is 0.05 (not 0.045 -> 0.04).
check("tax rounded before adding", lambda: invoice_total(["0.03"], "0.5"), "0.05")
check("tax of half a cent rounds to zero", lambda: invoice_total(["0.01"], "0.5"), "0.01")
check("repeated float prices", lambda: invoice_total(["0.10", "0.10", "0.10"], "0"), "0.30")
check("multi-line with sales tax", lambda: invoice_total(["19.99", "5.01"], "0.0825"), "27.06")
check("no lines", lambda: invoice_total([], "0.08"), "0.00")
