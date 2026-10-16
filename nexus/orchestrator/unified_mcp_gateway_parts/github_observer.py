"""GitHub observer and in-process Core provenance helpers of the unified MCP gateway.

Big-file split G3 (Issue #2441). Moved from ``nexus/orchestrator/unified_mcp_gateway.py``
with AST-identical bodies, except that ``_resolve_github_cli``, ``CANONICAL_SOURCE_ROOT``,
``SERVER_INSTANCE_ID`` and ``_SHA_RE`` are resolved at call time through ``_gateway()``,
so patches of those names on the gateway module keep taking effect. The gateway
re-exports every name; ``_core_provenance_cache`` and ``_core_provenance_lock`` are the
same objects through either module.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from nexus.orchestrator.mutation_admission import CANONICAL_REPOSITORIES


def _gateway():
    # Late binding: the gateway imports this module at its top level, so its own
    # (and its patched) names are only resolved once a helper is called.
    return importlib.import_module("nexus.orchestrator.unified_mcp_gateway")


_GITHUB_CLI_ENV = "NEXUS_GITHUB_CLI"


def _resolve_github_cli() -> tuple[str | None, str | None]:
    """Resolve the GitHub CLI to one executable absolute path before use."""
    configured = os.environ.get(_GITHUB_CLI_ENV, "").strip()
    if configured:
        candidate = Path(configured)
        if not candidate.is_absolute():
            return None, f"{_GITHUB_CLI_ENV} must be an absolute path"
    else:
        discovered = shutil.which("gh")
        if not discovered:
            return None, "GitHub CLI executable could not be resolved"
        candidate = Path(discovered)

    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        return None, f"GitHub CLI executable could not be resolved: {exc}"
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        return None, "GitHub CLI resolved path is not an executable file"
    return str(resolved), None


CORE_PROVENANCE_RECHECK_SECONDS = 300.0
_CORE_PROVENANCE_PUBLIC_FIELDS = (
    "status",
    "expected_revision",
    "observed_commit",
    "fail_closed",
    "identity_source",
)
_core_provenance_cache: dict[str, Any] = {}
_core_provenance_lock = threading.Lock()


def preload_core_transport() -> bool:
    """Bind ``product`` to the configured Core checkout before anything else can.

    With ``NEXUS_CORE_REPO_ROOT`` set, the Core transport is imported at
    Gateway startup, so the in-tree ``product`` package can never be imported
    first (for example by an EIA call) and shadow Core for the rest of this
    long-lived process (#2181). From then on every ``product.*`` import in
    this process resolves to Core. Without the variable nothing is imported.
    """
    if not os.environ.get("NEXUS_CORE_REPO_ROOT", "").strip():
        return False
    import nexus.orchestrator.canonical_core_transport  # noqa: F401

    return True


def gateway_core_provenance(*, refresh: bool = False) -> dict[str, Any]:
    """Core provenance observed inside this running Gateway process (#2181).

    Evaluated once per process and cached; the checkout identity is re-read
    at most every ``CORE_PROVENANCE_RECHECK_SECONDS``. A deploy probe reads it
    from the live process instead of a fresh subprocess. Any failure to
    evaluate it is reported fail-closed, never raised.
    """
    with _core_provenance_lock:
        cached = _core_provenance_cache.get("value")
        checked_at = float(_core_provenance_cache.get("checked_at", 0.0))
        if (
            not refresh
            and cached is not None
            and time.monotonic() - checked_at < CORE_PROVENANCE_RECHECK_SECONDS
        ):
            return dict(cached)
        try:
            from nexus.orchestrator.canonical_core_transport import core_provenance_status

            result = json.loads(json.dumps(dict(core_provenance_status()), default=str))
        except Exception as exc:  # reported, never raised: status must stay readable
            result = {
                "status": "CORE_PROVENANCE_PROBE_FAILED",
                "fail_closed": True,
                "reason": f"{type(exc).__name__}: {exc}",
            }
        result["observed_in_pid"] = os.getpid()
        result["server_instance_id"] = _gateway().SERVER_INSTANCE_ID
        _core_provenance_cache.update(value=result, checked_at=time.monotonic())
        return dict(result)


def public_core_provenance() -> dict[str, Any]:
    """The unauthenticated projection: no paths and no error text."""
    full = gateway_core_provenance()
    return {field: full.get(field) for field in _CORE_PROVENANCE_PUBLIC_FIELDS}


def github_observer_runtime_identity() -> dict[str, Any]:
    """Expose the non-secret executable identity required by Project Entry."""
    executable, _error = _gateway()._resolve_github_cli()
    if executable is None:
        return {
            "schema": "nexus.github_observer_dependency.v1",
            "ready": False,
            "executable_path": None,
            "executable_sha256": None,
            "failure_code": "GITHUB_OBSERVER_EXECUTABLE_UNAVAILABLE",
        }
    try:
        digest = hashlib.sha256(Path(executable).read_bytes()).hexdigest()
    except OSError:
        return {
            "schema": "nexus.github_observer_dependency.v1",
            "ready": False,
            "executable_path": executable,
            "executable_sha256": None,
            "failure_code": "GITHUB_OBSERVER_EXECUTABLE_UNAVAILABLE",
        }
    return {
        "schema": "nexus.github_observer_dependency.v1",
        "ready": True,
        "executable_path": executable,
        "executable_sha256": digest,
        "failure_code": None,
    }


def observe_github_issue(repository: str, issue_number: int) -> dict[str, Any]:
    """Fresh, bounded GitHub observation; never writes or infers missing state."""
    github_cli, resolution_error = _gateway()._resolve_github_cli()
    if github_cli is None:
        return {
            "ok": False,
            "blocker": "GITHUB_OBSERVER_EXECUTABLE_UNAVAILABLE",
            "detail": resolution_error or "GitHub CLI executable unavailable",
        }
    try:
        result = subprocess.run(
            [
                github_cli,
                "issue",
                "view",
                str(issue_number),
                "--repo",
                repository,
                "--json",
                "number,state,updatedAt,url",
            ],
            cwd=_gateway().CANONICAL_SOURCE_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "blocker": "GITHUB_OBSERVER_TIMEOUT",
            "detail": str(exc),
        }
    except OSError as exc:
        return {
            "ok": False,
            "blocker": "GITHUB_OBSERVER_EXECUTABLE_UNAVAILABLE",
            "detail": str(exc),
        }
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        lowered = detail.lower()
        auth_failure = any(
            marker in lowered
            for marker in (
                "auth login",
                "authentication",
                "not logged into",
                "gh_token",
                "github_token",
            )
        )
        return {
            "ok": False,
            "blocker": (
                "GITHUB_OBSERVER_AUTH_UNAVAILABLE"
                if auth_failure
                else "GITHUB_OBSERVER_REQUEST_FAILED"
            ),
            "detail": detail,
        }
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "blocker": "GITHUB_OBSERVER_MALFORMED_RESPONSE",
            "detail": str(exc),
        }
    if not isinstance(payload, Mapping) or str(payload.get("number")) != str(issue_number):
        return {
            "ok": False,
            "blocker": "GITHUB_OBSERVER_MALFORMED_RESPONSE",
            "detail": "issue identity mismatch",
        }
    return {
        "ok": True,
        "issue": dict(payload),
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }


def observe_github_repository_default_head(repository: str) -> dict[str, Any]:
    """Freshly observe one canonical repository default-branch head."""

    if repository not in CANONICAL_REPOSITORIES:
        return {
            "ok": False,
            "blocker": "MUTATION_ADMISSION_REPOSITORY_NOT_CANONICAL",
            "detail": repository,
        }
    github_cli, resolution_error = _gateway()._resolve_github_cli()
    if github_cli is None:
        return {
            "ok": False,
            "blocker": "GITHUB_OBSERVER_EXECUTABLE_UNAVAILABLE",
            "detail": resolution_error or "GitHub CLI executable unavailable",
        }

    def api(path: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        try:
            result = subprocess.run(
                [github_cli, "api", path],
                cwd=_gateway().CANONICAL_SOURCE_ROOT,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return None, {
                "ok": False,
                "blocker": "GITHUB_OBSERVER_TIMEOUT",
                "detail": str(exc),
            }
        except OSError as exc:
            return None, {
                "ok": False,
                "blocker": "GITHUB_OBSERVER_EXECUTABLE_UNAVAILABLE",
                "detail": str(exc),
            }
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            lowered = detail.lower()
            auth_failure = any(
                marker in lowered
                for marker in (
                    "auth login",
                    "authentication",
                    "not logged into",
                    "gh_token",
                    "github_token",
                )
            )
            return None, {
                "ok": False,
                "blocker": (
                    "GITHUB_OBSERVER_AUTH_UNAVAILABLE"
                    if auth_failure
                    else "GITHUB_OBSERVER_REQUEST_FAILED"
                ),
                "detail": detail,
            }
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            return None, {
                "ok": False,
                "blocker": "GITHUB_OBSERVER_MALFORMED_RESPONSE",
                "detail": str(exc),
            }
        if not isinstance(payload, dict):
            return None, {
                "ok": False,
                "blocker": "GITHUB_OBSERVER_MALFORMED_RESPONSE",
                "detail": "GitHub response must be an object",
            }
        return payload, None

    repo_payload, error = api(f"repos/{repository}")
    if error is not None:
        return error
    assert repo_payload is not None
    if repo_payload.get("full_name") != repository:
        return {
            "ok": False,
            "blocker": "GITHUB_OBSERVER_MALFORMED_RESPONSE",
            "detail": "repository identity mismatch",
        }
    default_branch = str(repo_payload.get("default_branch") or "").strip()
    if not default_branch:
        return {
            "ok": False,
            "blocker": "GITHUB_OBSERVER_MALFORMED_RESPONSE",
            "detail": "default branch missing",
        }
    branch_payload, error = api(f"repos/{repository}/branches/{default_branch}")
    if error is not None:
        return error
    assert branch_payload is not None
    commit = branch_payload.get("commit")
    head_sha = str(commit.get("sha") or "") if isinstance(commit, Mapping) else ""
    if branch_payload.get("name") != default_branch or not _gateway()._SHA_RE.fullmatch(head_sha):
        return {
            "ok": False,
            "blocker": "GITHUB_OBSERVER_MALFORMED_RESPONSE",
            "detail": "default branch head identity mismatch",
        }
    return {
        "ok": True,
        "repository": repository,
        "default_branch": default_branch,
        "head_sha": head_sha,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }


def _canonical_remote_matches(origin: str, repository: str) -> bool:
    value = str(origin).strip()
    if value.startswith("git@"):
        host_path = value[4:]
        host, sep, path = host_path.partition(":")
        return (
            sep == ":" and host.lower() == "github.com" and path.removesuffix(".git") == repository
        )
    parsed = urlsplit(value)
    return (  # pyright: ignore[reportReturnType]
        parsed.scheme.lower() == "https"
        and parsed.hostname
        and parsed.hostname.lower() == "github.com"
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
        and parsed.path.removesuffix("/").removesuffix(".git").lstrip("/") == repository
    )
