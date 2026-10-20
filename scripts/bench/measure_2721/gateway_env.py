"""Run the harness with the measurement Gateway's own measurement settings.

``load_gateway_env(path)`` reads the Gateway's ``start.sh`` (or a plain
``KEY=VALUE`` env file) WITHOUT executing it: only variable assignments
(``export K=V`` / ``K=V``) are taken, ``$VAR`` / ``${VAR}`` are expanded from
the values seen so far (then the current environment), every other command is
ignored, and reading stops at the first ``exec`` so the Gateway is never
started.  Values are never printed.

Only the measurement whitelist (``NEXUS_MEASUREMENT_*``, ``NEXUS_MEASURE_*``)
is kept, and it is held here -- ``os.environ`` of the harness is never
changed, so harness git keeps its hardened env.  ``measurement_env()`` is what
the measurement code (venv checks, the BARE adapter env) reads.

``require_read_roots()`` fails fast when ``NEXUS_MEASUREMENT_READ_ROOTS`` is
empty: the adapter would then refuse the task venv and every row would be void.
"""

from __future__ import annotations

import hashlib
import os
import re
import shlex
from pathlib import Path
from typing import Mapping, Optional

READ_ROOTS_ENV = "NEXUS_MEASUREMENT_READ_ROOTS"
WHITELIST_PREFIXES = ("NEXUS_MEASUREMENT_", "NEXUS_MEASURE_")
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_VAR = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")
_LOADED: dict[str, str] = {}


class GatewayEnvError(RuntimeError):
    pass


def whitelisted(name: str) -> bool:
    return name.startswith(WHITELIST_PREFIXES)


def _expand(value: str, known: Mapping[str, str], base: Mapping[str, str]) -> str:
    return _VAR.sub(lambda m: known.get(m.group(1) or m.group(2), base.get(m.group(1) or m.group(2), "")), value)


def load_gateway_env(path: Path | str, base: Optional[Mapping[str, str]] = None) -> dict[str, str]:
    """The whitelisted assignments of ``path`` (never executed)."""
    base = dict(os.environ if base is None else base)
    values: dict[str, str] = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            tokens = shlex.split(line, comments=True)
        except ValueError:
            continue
        if not tokens:
            continue
        if tokens[0] == "exec":
            break
        if tokens[0] == "export":
            tokens = tokens[1:]
        if not tokens or not all("=" in t and _NAME.match(t.split("=", 1)[0]) for t in tokens):
            continue  # a command, not an assignment: never run
        for token in tokens:
            name, value = token.split("=", 1)
            values[name] = _expand(value, values, base)
    return {name: value for name, value in values.items() if whitelisted(name)}


def use_gateway_env(path: Path | str) -> list[str]:
    """Hold the Gateway's whitelisted settings for this process; returns the names only."""
    _LOADED.clear()
    _LOADED.update(load_gateway_env(path))
    return sorted(_LOADED)


def reset() -> None:
    _LOADED.clear()


def measurement_env() -> dict[str, str]:
    """Whitelisted measurement settings: the loaded Gateway values over the process ones."""
    own = {name: value for name, value in os.environ.items() if whitelisted(name)}
    return {**own, **_LOADED}


def read_roots_sha256(env: Optional[Mapping[str, str]] = None) -> str:
    value = str((measurement_env() if env is None else env).get(READ_ROOTS_ENV) or "")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def require_read_roots(env: Optional[Mapping[str, str]] = None) -> list[str]:
    value = str((measurement_env() if env is None else env).get(READ_ROOTS_ENV) or "")
    roots = [r for r in value.split(":") if r.strip()]
    if not roots:
        raise GatewayEnvError(f"{READ_ROOTS_ENV} is empty: load the Gateway env (--gateway-env start.sh)")
    return roots
