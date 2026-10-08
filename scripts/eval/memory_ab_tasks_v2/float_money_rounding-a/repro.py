from checkout import checkout_total

def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


check("accumulated cents", lambda: checkout_total(["0.10", "0.20"], "0"), "0.30")
check("half-even on exact decimal", lambda: checkout_total(["2.675"], "0"), "2.68")
check("tax then round", lambda: checkout_total(["10.00"], "0.0825"), "10.82")
check("tiny half-cent", lambda: checkout_total(["0.005"], "0"), "0.00")
check("repeated prices", lambda: checkout_total(["19.99"] * 3, "0"), "59.97")
