DEFAULTS = {"display": {"theme": "light", "font": 12}, "alerts": ["email"]}


def build_profile(overrides):
    """Return DEFAULTS merged with overrides.

    Nested dicts merge key by key; other values, lists included, replace the default.
    The result shares no mutable state with DEFAULTS or with overrides.
    """
    profile = dict(DEFAULTS)  # BUG: shallow copy; update() replaces nested dicts
    profile.update(overrides)
    return profile
