"""Temporary self-hosting bootstrap for the trusted verifier repair.

The default-branch trusted verifier currently builds a deliberately minimal
runtime.  After TG6 dependency slimming, ``tests/conftest.py`` still needs
``numpy``/``pandas`` merely to construct its optional-dependency stubs.  This
root conftest supplies tiny collection-safe fallbacks only when those packages
are genuinely unavailable.  It must be removed immediately after the trusted
runtime builder starts exporting the ``legacy`` extra.
"""

from __future__ import annotations

import importlib.util
import math
import sys
import types
from importlib.machinery import ModuleSpec


def _map(value, fn):
    if isinstance(value, (list, tuple, _Array)):
        return _Array(_map(item, fn) for item in value)
    return fn(value)


class _Array(list):
    @property
    def shape(self):
        if self and isinstance(self[0], (list, tuple, _Array)):
            return (len(self), len(self[0]))
        return (len(self),)

    def tolist(self):
        return [item.tolist() if isinstance(item, _Array) else item for item in self]

    def _binary(self, other, fn):
        if isinstance(other, (list, tuple, _Array)):
            return _Array(fn(left, right) for left, right in zip(self, other))
        return _Array(fn(left, other) for left in self)

    def __add__(self, other):
        return self._binary(other, lambda left, right: left + right)

    __radd__ = __add__

    def __sub__(self, other):
        return self._binary(other, lambda left, right: left - right)

    def __mul__(self, other):
        return self._binary(other, lambda left, right: left * right)

    __rmul__ = __mul__

    def __truediv__(self, other):
        return self._binary(other, lambda left, right: left / right)

    def __neg__(self):
        return _Array(-value for value in self)


def _install_numpy_fallback() -> None:
    if importlib.util.find_spec("numpy") is not None:
        return
    module = types.ModuleType("numpy")
    module.__spec__ = ModuleSpec("numpy", loader=None)
    module.pi = math.pi
    module.array = lambda value, dtype=None: _Array(value) if isinstance(value, (list, tuple)) else value
    module.asarray = module.array
    module.sqrt = lambda value: _map(value, math.sqrt)
    module.exp = lambda value: _map(value, math.exp)

    def vectorize(fn):
        return lambda value: _map(value, fn)

    module.vectorize = vectorize
    sys.modules["numpy"] = module


def _install_pandas_fallback() -> None:
    if importlib.util.find_spec("pandas") is not None:
        return
    module = types.ModuleType("pandas")
    module.__spec__ = ModuleSpec("pandas", loader=None)

    class DataFrame:
        def __init__(self, rows=None, *args, **kwargs):
            self._rows = list(rows or [])

        def to_dict(self, orient="dict"):
            if orient == "records":
                return list(self._rows)
            return {}

    module.DataFrame = DataFrame
    sys.modules["pandas"] = module


_install_numpy_fallback()
_install_pandas_fallback()
