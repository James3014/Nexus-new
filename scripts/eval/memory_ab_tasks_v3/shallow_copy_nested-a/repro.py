from profiles import DEFAULTS, build_profile


def check(label, got_fn, want):
    try:
        got = got_fn()
    except Exception as exc:
        raise AssertionError(f"{label}: raised {type(exc).__name__}: {exc}") from exc
    assert got == want, f"{label}: got {got!r} want {want!r}"


ORIGINAL = {"display": {"theme": "light", "font": 12}, "alerts": ["email"]}

check(
    "partial nested override merges",
    lambda: build_profile({"display": {"font": 14}}),
    {"display": {"theme": "light", "font": 14}, "alerts": ["email"]},
)
check(
    "list override replaces",
    lambda: build_profile({"alerts": ["sms"]}),
    {"display": {"theme": "light", "font": 12}, "alerts": ["sms"]},
)

first = build_profile({})
first["display"]["theme"] = "dark"
first["alerts"].append("sms")
check("defaults untouched by caller", lambda: DEFAULTS, ORIGINAL)
check("fresh profile matches defaults", lambda: build_profile({}), ORIGINAL)

overrides = {"display": {"font": 14}}
built = build_profile(overrides)
built["display"]["font"] = 99
check("overrides untouched by caller", lambda: overrides, {"display": {"font": 14}})
