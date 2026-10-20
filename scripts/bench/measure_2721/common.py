"""Small shared helpers: git, diff capture, JSON(L) IO."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

# Provider/model-side infra markers in a worker error (pool busy, credentials,
# the adapter's ``claude_infra:*`` such as a 429, the measurement CLI missing).
# Shared by the NEXUS driver and blind.py's symmetric-infra rule.
INFRA_ERROR_MARKERS = ("agy_pool_busy", "AGY_POOL_BUSY", "POOL_EXHAUSTED", "agy_pool_exhausted",
                       "credentials_unavailable", "MODEL_PROBE_REQUIRED", "claude_infra:",
                       "MEASUREMENT_CLAUDE_PROBE_FAILED", "MEASUREMENT_CLAUDE_BINARY_UNAVAILABLE")

_GIT_ENV = {
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_AUTHOR_NAME": "measure-2721",
    "GIT_AUTHOR_EMAIL": "measure-2721@invalid",
    "GIT_COMMITTER_NAME": "measure-2721",
    "GIT_COMMITTER_EMAIL": "measure-2721@invalid",
}


def git(cwd: Path | str, *args: str, env: Mapping[str, str] | None = None, check: bool = True) -> str:
    merged = {**os.environ, **_GIT_ENV, **(env or {})}
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), env=merged, capture_output=True, text=True, check=False
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {cwd}: {result.stderr.strip()[-500:]}")
    return result.stdout


def sha256_text(text: str) -> str:
    # surrogateescape: a byte-exact diff read with errors="surrogateescape"
    # round-trips to the same bytes (and so the same hash).
    return hashlib.sha256(text.encode("utf-8", errors="surrogateescape")).hexdigest()


# The shared measurement diff rule (#2761, used by P1's
# ``measurement_worktree_diff`` and by the BARE arm): attributes only from the
# base tree, no textconv/attributes file, no system/global config, no
# fsmonitor/hooks/transports, no inherited GIT_* variables, byte-exact output.
_SHARED_GIT_CONFIG = (
    "-c", "core.fsmonitor=false",
    "-c", "core.hooksPath=/dev/null",
    "-c", "protocol.allow=never",
    "-c", "core.attributesFile=/dev/null",
    "-c", "core.splitIndex=false",
    "-c", "core.untrackedCache=false",
    "-c", "index.threads=1",
)  # fmt: skip


def _shared_rule_env(index_file: Path) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(
        GIT_INDEX_FILE=str(index_file),
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_ATTR_NOSYSTEM="1",
        GIT_TERMINAL_PROMPT="0",
    )
    return env


def capture_diff_bytes(worktree: Path | str, base: str) -> bytes:
    """Byte-exact diff of the working tree (tracked + untracked) against ``base``
    under the shared rule; a throwaway index leaves the worktree's own index alone."""
    worktree = Path(worktree)
    with tempfile.TemporaryDirectory(prefix="m2721-index-") as tmp:
        env = _shared_rule_env(Path(tmp) / "index")
        attr = f"--attr-source={base}"

        def run(*args: str) -> bytes:
            result = subprocess.run(
                ["git", *_SHARED_GIT_CONFIG, attr, *args], cwd=str(worktree), env=env,
                capture_output=True, stdin=subprocess.DEVNULL, check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(f"git {args[0]} failed: {result.stderr.decode(errors='replace')[-300:]}")
            return result.stdout

        run("read-tree", base)
        run("add", "-A", "--", ".")
        return run("diff", "--cached", "--binary", "--no-color", "--no-ext-diff", "--no-textconv", base)


def capture_diff(worktree: Path | str, base: str) -> str:
    """``capture_diff_bytes`` as text that round-trips byte for byte."""
    return capture_diff_bytes(worktree, base).decode("utf-8", errors="surrogateescape")


def write_diff(path: Path, diff: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(diff.encode("utf-8", errors="surrogateescape"))


def read_diff(path: Path) -> str:
    return Path(path).read_bytes().decode("utf-8", errors="surrogateescape")


_GIT_META = ("config", "info", "hooks")


def git_meta_fingerprint(repo: Path | str, worktree: Path | str | None = None) -> str:
    """sha256 over ``.git/config``, ``.git/info/*`` and ``.git/hooks/*`` of the
    repository (and the worktree's ``.git`` file, when given) (#2749).

    Taken at materialize time and again before capture: a mismatch means the
    git configuration was changed, and no git command is run."""
    root = Path(repo) / ".git"
    digest = hashlib.sha256()
    if worktree is not None:
        dot_git = Path(worktree) / ".git"
        digest.update(b"W " + (dot_git.read_bytes() if dot_git.is_file() else b"<not a file>") + b"\n")
    for name in _GIT_META:
        entry = root / name
        paths = sorted(p for p in entry.rglob("*") if p.is_file() or p.is_symlink()) if entry.is_dir() else [entry]
        for path in paths:
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                digest.update(f"L {rel} {os.readlink(path)}\n".encode())
            elif path.is_file():
                digest.update(f"F {rel} ".encode() + hashlib.sha256(path.read_bytes()).hexdigest().encode() + b"\n")
            else:
                digest.update(f"- {rel}\n".encode())
    return digest.hexdigest()


def diff_paths(diff: str) -> list[str]:
    paths: list[str] = []
    for line in diff.splitlines():
        if line.startswith("diff --git a/"):
            rest = line[len("diff --git a/") :]
            path = rest.split(" b/", 1)[0]
            if path not in paths:
                paths.append(path)
    return paths


def write_json(path: Path, value: Any, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    if mode is not None:
        os.chmod(path, mode)


def append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def read_jsonl(path: Path | str) -> Iterator[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


# -- row classification (re-review #6: one pure function of immutable facts) ----------
#
# The NEXUS driver records FACTS on ``row["facts"]`` as they happen, with sticky setters
# (``set_fact``: a True flag is never cleared, a text keeps its first value, a list only
# grows).  ``classify_row(facts)`` is called once, at the very end of the row (after the
# cancel and clean-up in ``finally``); blind.py, runner.recover() and the driver all use
# it, so no code path rewrites ``outcome`` along the way.  PREREG v0.9.4 / amendment 10.
#
# Precedence (first matching rule wins):
#   1. interrupted (KeyboardInterrupt / SystemExit, at any time) -> INTERRUPTED, infra,
#      never a finished row (rule INTERRUPTED).
#   2. not accepted: a harness pre-check failed -> infra, HARNESS_NOT_SUBMITTED;
#      else (the Gateway/Nexus refused, or was unreachable) -> infra, NEXUS_NOT_ACCEPTED
#      (Nexus reliability).
#   3. accepted + a watchdog event for the row (the watchdog killed the run or the
#      Gateway, incl. a lost connection) -> infra, SYMMETRIC_INFRA.
#   4. accepted + model-side infra BARE has too (attempt INFRA e.g. a 429, provider
#      infra marker, CLI time-limit mismatch, unusable venv) -> infra, SYMMETRIC_INFRA.
#   5. accepted + the harness's own bounded polling found the task never terminal
#      (GATEWAY_STUCK) -> infra, SYMMETRIC_INFRA (PREREG §3.3).
#   6. accepted + a Gateway-side error (HTTP error, non-JSON/malformed reply, tool
#      error, a lost connection WITHOUT a watchdog event, any other exception after
#      acceptance) -> GATEWAY_ERROR, not infra (RUN_INVALID_NOT_SOLVED).
#   7. accepted + LB state changed / snapshot missing or invalid / trace missing ->
#      void (void_reason), not infra (RUN_INVALID_NOT_SOLVED).
#   8. otherwise the model outcome (OK / TIMEOUT / MODEL_FAILED), not infra.

LIST_FACTS = frozenset({"model_infra", "void"})


def set_fact(row: dict[str, Any], key: str, value: Any = True) -> None:
    """Sticky: True is never cleared, a text keeps its first value, a list only grows."""
    facts = row.setdefault("facts", {})
    if key in LIST_FACTS:
        values = facts.setdefault(key, [])
        if value not in values:
            values.append(value)
    elif isinstance(value, bool):
        if value:
            facts[key] = True
        else:
            facts.setdefault(key, False)
    elif value is not None:
        facts.setdefault(key, value)


def classify_row(facts: Mapping[str, Any]) -> dict[str, Any]:
    """The one classification of a NEXUS row from its facts (see the precedence above)."""
    def result(outcome: str, infra: bool, void: Any = None, rule: Any = None, reason: Any = None,
               reliability: bool = False, symmetric: Any = ()) -> dict[str, Any]:
        return {"outcome": outcome, "infra": infra, "void_reason": void,
                "exclusion": (rule, reason) if rule else None, "nexus_reliability": reliability,
                "symmetric_infra_reasons": list(symmetric)}

    first_void = facts.get("void_reason")
    if facts.get("interrupted"):
        void = f"INTERRUPTED:{facts['interrupted']}"
        return result("INTERRUPTED", True, void, "INTERRUPTED", void, symmetric=["INTERRUPTED"])
    if not facts.get("accepted"):
        if facts.get("harness_error"):
            reason = str(facts["harness_error"])
            return result("INFRA", True, reason, "HARNESS_NOT_SUBMITTED", reason)
        reason = str(facts.get("nexus_refusal") or "NOT_ACCEPTED")
        return result(str(facts.get("refusal_outcome") or "INFRA"), True, first_void or reason,
                      "NEXUS_NOT_ACCEPTED", first_void or reason, reliability=True)
    symmetric = [*(["WATCHDOG_EVENT"] if facts.get("watchdog_event") else []), *(facts.get("model_infra") or []),
                 *(["GATEWAY_STUCK"] if facts.get("stuck_by_harness_timeout") else [])]
    if symmetric:
        return result("INFRA", True, first_void, "SYMMETRIC_INFRA", ",".join(symmetric), symmetric=symmetric)
    if facts.get("gateway_error") or facts.get("connection_lost"):
        return result("GATEWAY_ERROR", False, first_void)
    if facts.get("void"):
        return result(str(facts.get("model_outcome") or "OK"), False, first_void or facts["void"][0])
    return result(str(facts.get("model_outcome") or "OK"), False, first_void)


NEXUS_REFUSAL_PREFIXES = ("PRE_SUBMIT_FAILURE:", "WORKER_NOT_ACCEPTED:", "DUPLICATE_TASK", "GATEWAY_CONNECTION_LOST")
GATEWAY_ANSWER_STUCK_PREFIXES = ("connection_lost:", "status_error:")
SYMMETRIC_INFRA_FLAGS = ("CLI_TIMEOUT_MISMATCH", "VENV_NOT_USABLE")


def row_facts(row: Mapping[str, Any]) -> dict[str, Any]:
    """``row["facts"]``; for a row written without facts (hand-built or older rows) the
    same facts derived from its fields, so every NEXUS row goes through classify_row."""
    if isinstance(row.get("facts"), Mapping):
        return dict(row["facts"])
    void = str(row.get("void_reason") or "")
    outcome = str(row.get("outcome") or "")
    stuck = str(row.get("gateway_stuck") or "")
    facts: dict[str, Any] = {"accepted": bool(row.get("worker_accepted")), "void_reason": void or None}
    if outcome == "INTERRUPTED" or void.startswith("INTERRUPTED:"):
        facts["interrupted"] = void.split(":", 1)[1] if ":" in void else "unknown"
    if not facts["accepted"]:
        if void.startswith(NEXUS_REFUSAL_PREFIXES) or outcome == "BLOCKED_EXTERNAL_TARGET_UNSUPPORTED":
            facts.update(nexus_refusal=void or outcome, refusal_outcome=outcome or None)
        else:
            facts["harness_error"] = void or outcome or "NOT_ACCEPTED"
    if row.get("watchdog_event") is not None:
        facts["watchdog_event"] = True
    model_infra = []
    if row.get("attempt_status") == "INFRA":
        model_infra.append("MODEL_ATTEMPT_INFRA")
    if any(marker in str(row.get("error") or "") for marker in INFRA_ERROR_MARKERS):
        model_infra.append("PROVIDER_INFRA_MARKER")
    model_infra += [flag for flag in SYMMETRIC_INFRA_FLAGS if flag in (row.get("flags") or [])]
    facts["model_infra"] = model_infra
    if stuck and not stuck.startswith(GATEWAY_ANSWER_STUCK_PREFIXES):
        facts["stuck_by_harness_timeout"] = True
    if row.get("gateway_connection_lost") or stuck.startswith("connection_lost:"):
        facts["connection_lost"] = True
    if outcome == "GATEWAY_ERROR" or stuck.startswith("status_error:"):
        facts["gateway_error"] = void or "GATEWAY_ERROR"
    if void:
        facts["void"] = [void]
    if outcome in ("OK", "TIMEOUT", "MODEL_FAILED"):
        facts["model_outcome"] = outcome
    return facts
