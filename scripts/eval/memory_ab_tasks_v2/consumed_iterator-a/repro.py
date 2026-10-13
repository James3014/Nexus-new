from ledger_report import summarize, top_category


def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


DATA = [
    {"category": "food", "amount": 100},
    {"category": "rent", "amount": 300},
    {"category": "food", "amount": 250},
]

check(
    "summarize generator",
    lambda: summarize(iter(DATA[:2])),
    {"count": 2, "total": 400, "mean": 200.0},
)
check(
    "summarize empty generator", lambda: summarize(iter([])), {"count": 0, "total": 0, "mean": 0.0}
)
check("top_category generator", lambda: top_category(iter(DATA)), "food")
check("top_category list", lambda: top_category(DATA), "food")
