"""Run the harness with the measurement Gateway's own environment.

``load_gateway_env(path)`` reads the Gateway's ``start.sh`` (or a plain
``KEY=VALUE`` env file) WITHOUT executing it: only variable assignments
(``export K=V`` / ``K=V``) are taken, ``$VAR`` / ``${VAR}`` are expanded from
the values seen so far (then the current environment), every other command is
ignored, and reading stops at the first ``exec`` so the Gateway is never
started.  Values are never printed.

``require_read_roots()`` fails fast when ``NEXUS_MEASUREMENT_READ_ROOTS`` is
empty: the adapter would then refuse the task venv and every row would be void.
"""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from typing import Mapping, MutableMapping, Optional

READ_ROOTS_ENV = "NEXUS_MEASUREMENT_READ_ROOTS"
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_VAR = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")


class GatewayEnvError(RuntimeError):
    pass


def _expand(value: str, known: Mapping[str, str], base: Mapping[str, str]) -> str:
    return _VAR.sub(lambda m: known.get(m.group(1) or m.group(2), base.get(m.group(1) or m.group(2), "")), value)


def load_gateway_env(path: Path | str, base: Optional[Mapping[str, str]] = None) -> dict[str, str]:
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
    return values


def apply_gateway_env(path: Path | str, environ: Optional[MutableMapping[str, str]] = None) -> list[str]:
    """Load ``path`` into ``environ`` (default os.environ); returns the variable names only."""
    target = os.environ if environ is None else environ
    values = load_gateway_env(path, target)
    target.update(values)
    return sorted(values)


def require_read_roots(environ: Optional[Mapping[str, str]] = None) -> list[str]:
    env = os.environ if environ is None else environ
    roots = [r for r in str(env.get(READ_ROOTS_ENV) or "").split(os.pathsep) if r.strip()]
    if not roots:
        raise GatewayEnvError(f"{READ_ROOTS_ENV} is empty: load the Gateway env (--gateway-env start.sh)")
    return roots
