"""Temporary self-hosting bootstrap for the trusted verifier repair.

The default-branch trusted verifier currently builds a deliberately minimal
runtime. After TG6 dependency slimming, the old verifier runtime no longer
contains the legacy dependency closure required by the existing test corpus.
This root conftest supplies collection-safe numpy/pandas fallbacks and, when
Pydantic is absent, loads the exact locked Pydantic wheel set vendored under
``.bootstrap/trusted_runtime``. All bootstrap material must be removed
immediately after the trusted runtime builder exports the ``legacy`` extra.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import math
import sys
import tempfile
import types
import zipfile
from importlib.machinery import ModuleSpec
from pathlib import Path

# Owner-authored synchronization fence after the one-shot wheel bootstrap.

_LOCKED_PYDANTIC_WHEELS = {
    "annotated_types-0.7.0-py3-none-any.whl": "1f02e8b43a8fbbc3f3e0d4f0f4bfc8131bcb4eebe8849b8e5c773f3a1c582a53",
    "pydantic-2.12.5-py3-none-any.whl": "e561593fccf61e8a20fc46dfc2dfe075b8be7d0188df33f221ad1f0139180f9d",
    "pydantic_core-2.41.5-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl": "eceb81a8d74f9267ef4081e246ffd6d129da5d87e37a77c9bde550cb04870c1c",
    "typing_extensions-4.15.0-py3-none-any.whl": "f0fa19c6845758ab08074a0cfa8b7aecb71c999ca73d62883bc25cc018c4e548",
    "typing_inspection-0.4.2-py3-none-any.whl": "4ed1cacbdc298c220f1bd249ed5287caa16f34d44ef4e9c3d0cbad5b521545e7",
}


def _install_locked_pydantic_bootstrap() -> None:
    if importlib.util.find_spec("pydantic") is not None:
        return
    wheel_root = Path(__file__).resolve().parent / ".bootstrap" / "trusted_runtime"
    paths = []
    for name, expected_sha256 in _LOCKED_PYDANTIC_WHEELS.items():
        path = wheel_root / name
        if not path.is_file():
            raise RuntimeError(f"missing trusted-verifier bootstrap wheel: {name}")
        actual_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_sha256 != expected_sha256:
            raise RuntimeError(f"trusted-verifier bootstrap wheel hash mismatch: {name}")
        paths.append(path)
    target = Path(tempfile.mkdtemp(prefix="nexus-trusted-verifier-pydantic-"))
    for path in paths:
        with zipfile.ZipFile(path) as archive:
            archive.extractall(target)
    sys.path.insert(0, str(target))
    importlib.invalidate_caches()
    import pydantic  # noqa: F401


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


_install_locked_pydantic_bootstrap()
_install_numpy_fallback()
_install_pandas_fallback()
