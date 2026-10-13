"""Shared helper for the scripts/effects entry points (#1928)."""

from __future__ import annotations

import functools
import os


def scoped_feature_flags(fn, keys):
    """Restore the process environment after an in-process run (#1928).

    The run toggles NEXUS_ENABLE_* feature flags on os.environ; left set, they
    changed later behaviour in the same process (full-suite nightly: the P5
    diversity selector stayed enabled for tests/unit/local_heal).
    """

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        saved = {key: os.environ.get(key) for key in keys}
        try:
            return fn(*args, **kwargs)
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    return wrapper
