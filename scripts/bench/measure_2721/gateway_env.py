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


def _assignments(path: Path | str, base: Optional[Mapping[str, str]] = None) -> dict[str, str]:
    """Every variable assignment of ``path`` up to the first ``exec`` (never executed)."""
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


def load_gateway_env(path: Path | str, base: Optional[Mapping[str, str]] = None) -> dict[str, str]:
    """The whitelisted assignments of ``path`` (never executed)."""
    values = _assignments(path, base)
    kept = {name: value for name, value in values.items() if whitelisted(name)}
    for name, value in kept.items():
        if "${" in value or "$(" in value or "`" in value:
            # ${VAR:-default}, command substitution etc. are not expanded here:
            # fail closed instead of passing a literal through (use a fully
            # expanded env file, e.g. 35's run/make_env.sh output).
            raise GatewayEnvError(f"{name}: unexpanded shell expression in {Path(path).name}")
    return kept


STATE_PATH_NAMES = ("NEXUS_STATE_ROOT", "NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR")


def gateway_state_paths(
    path: Path | str, base: Optional[Mapping[str, str]] = None
) -> dict[str, str]:
    """The Gateway's state locations (``NEXUS_STATE_ROOT``, the self-hosted state
    dir) from ``path``, read like ``load_gateway_env`` (never executed).

    Only these two path names are taken; they are not held for the process.
    The driver refuses to start when one of them lies inside the Controller
    worktree (its per-row ``clean -fdx`` would wipe the state).
    """
    values = _assignments(path, base)
    kept = {name: values[name] for name in STATE_PATH_NAMES if values.get(name, "").strip()}
    for name, value in kept.items():
        if "${" in value or "$(" in value or "`" in value:
            raise GatewayEnvError(f"{name}: unexpanded shell expression in {Path(path).name}")
    return kept


# GATE 6 (#2721 final audit, 77c6): the measurement Gateway must not switch in an
# extra model.  Defence in depth behind workspace-35's ``run/start.sh`` (exit 66),
# which refuses exactly GATE6_START_SH_SWITCHES; this check uses the same list
# (``NEXUS_LOCAL_MODEL*`` is a prefix) and refuses when one is set to anything but
# an explicit off value (empty, 0, false, no, off).
GATE6_START_SH_SWITCHES = (
    "NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "NEXUS_EXTERNAL_WORKER_OPERATION_ROOT", "NEXUS_LOCAL_MODEL*",
    "NEXUS_LLM_JUDGE_PROVIDERS", "NEXUS_LEARNING_REFLECT_JUDGE", "NEXUS_USE_COMMITTEE",
    "NEXUS_COMMITTEE_BUDGET_REMAINING", "NEXUS_CORE_EXTERNAL_VERIFICATION", "NEXUS_DOC_SCOUT_EXTERNAL_ROWS_JSON",
)
# Extra names found in Nexus-new ``nexus/`` (read sites in brackets), refused the same way:
# * NEXUS_MSA_ENABLED: model routing in the core router [core/router]; an
#   "external" flag in services/live_semantic_readiness.
# * NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL: the committee-routed tool
#   [services/local_heal/committee_activation_gate].
# * NEXUS_ENABLE_LOCAL_SWARM_EXECUTOR, NEXUS_ONLINE_LOCAL_ASSIST: local-model swarm
#   and assist [research/sprint_service, research/flow/capability_evidence].
# * NEXUS_OLLAMA_ENABLED: local Ollama retries [services/local_heal].
# * NEXUS_SHADOW_ADVISOR_ENABLED: a shadow model advisor [gate/experimental_gate].
# Not listed: model-name / endpoint settings (they switch nothing on), and the
# default-on S2T 3B advisor (services/s2t_strict), which nothing on the P1 path imports.
GATE6_EXTRA_SWITCHES = (
    "NEXUS_MSA_ENABLED", "NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL", "NEXUS_ENABLE_LOCAL_SWARM_EXECUTOR",
    "NEXUS_ONLINE_LOCAL_ASSIST", "NEXUS_OLLAMA_ENABLED", "NEXUS_SHADOW_ADVISOR_ENABLED",
)
# Warned, not refused (a pending decision): it authorizes the Agy (Gemini) worker
# [executors/worker_registry].
GATE6_WARN_SWITCHES = ("NEXUS_AGY_RUNTIME_AUTHORIZED",)
_OFF = frozenset({"", "0", "false", "no", "off"})


def _gate6_match(names: tuple[str, ...], values: Mapping[str, str]) -> list[str]:
    found = []
    for pattern in names:
        prefix = pattern[:-1] if pattern.endswith("*") else None
        for name in sorted(values):
            if (name == pattern or (prefix is not None and name.startswith(prefix))) and \
                    values[name].strip().lower() not in _OFF:
                found.append(name)
    return found


def gate6_switches(path: Path | str, base: Optional[Mapping[str, str]] = None, *,
                   warnings: Optional[list[str]] = None) -> list[str]:
    """Extra-model switches enabled in the Gateway env file ``path`` (never executed); [] = clean.

    Every assignment is read (not only the measurement whitelist); only names
    are returned, never values.  ``warnings`` (if given) receives the enabled
    GATE6_WARN_SWITCHES.
    """
    values = _assignments(path, {} if base is None else base)
    if warnings is not None:
        warnings.extend(_gate6_match(GATE6_WARN_SWITCHES, values))
    return _gate6_match(GATE6_START_SH_SWITCHES + GATE6_EXTRA_SWITCHES, values)


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
