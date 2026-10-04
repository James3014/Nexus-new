"""Read-only cross-session workflow status projection for Nexus operators."""

from __future__ import annotations

import argparse
import json
import re
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from nexus.orchestrator.canonical_source_root import (
    CANONICAL_SOURCE_ROOT,
    resolve_rdc_repo_root,
)
from nexus.services.direct_operation_journal import (
    ACTIVE_STATES,
    TERMINAL_STATES,
    public_operation_view,
)

SCHEMA = "nexus.workflow_doctor.v1"
RESUME_DISPOSITIONS = frozenset({"SAFE", "RECONCILE", "WAIT", "BLOCKED"})
_EXTERNAL_PREFIXES = {
    "clineop_": "cline",
    "opencodeop_": "opencode",
    "codexop_": "codex",
    "grokop_": "grok",
}
CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


class WorkflowDoctorError(RuntimeError):
    """The doctor could not build a trustworthy minimum projection."""


def resolve_workflow_repo_root(
    repo_root: str | Path | None,
    repository: str | None,
) -> Path:
    """Return the validated repo root for workflow doctor operations.

    Parameters
    ----------
    repo_root:
        Explicit path supplied by the caller, or ``None``.  When ``None``,
        ``CANONICAL_SOURCE_ROOT`` is used as the candidate — ``os.getcwd()``
        is never a fallback.
    repository:
        Optional GitHub ``OWNER/REPO`` identity.  When supplied the candidate
        is validated against the repository's origin remote via
        ``resolve_rdc_repo_root``.  When omitted the candidate is returned
        as-is without inventing a repository slug.

    Returns
    -------
    Path
        The resolved, optionally validated repository root.

    Raises
    ------
    RuntimeError
        Propagated from ``resolve_rdc_repo_root`` when the remote identity
        does not match *repository* or the path is not a valid git repo.
    """
    candidate: Path = Path(repo_root) if repo_root is not None else CANONICAL_SOURCE_ROOT
    if repository is not None:
        return resolve_rdc_repo_root(
            expected_repository=repository,
            canonical_root=candidate,
        )
    return candidate.expanduser().resolve()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    runner: CommandRunner = subprocess.run,
    timeout: float = 10.0,
) -> subprocess.CompletedProcess[str]:
    return runner(
        list(argv),
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def _json_command(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    runner: CommandRunner = subprocess.run,
    timeout: float = 10.0,
) -> tuple[Any | None, str | None]:
    try:
        proc = _run(argv, cwd=cwd, runner=runner, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"{type(exc).__name__}:{exc}"
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        return None, f"exit={proc.returncode}:{detail[:500]}"
    try:
        return json.loads(proc.stdout), None
    except json.JSONDecodeError as exc:
        return None, f"JSONDecodeError:{exc}"


def _text_command(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    runner: CommandRunner = subprocess.run,
) -> str | None:
    try:
        proc = _run(argv, cwd=cwd, runner=runner)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def _repository_from_remote(remote_url: str | None) -> str | None:
    value = str(remote_url or "").strip()
    for pattern in (
        r"^https://github\.com/([^/]+/[^/]+?)(?:\.git)?$",
        r"^git@github\.com:([^/]+/[^/]+?)(?:\.git)?$",
        r"^ssh://git@github\.com/([^/]+/[^/]+?)(?:\.git)?$",
    ):
        match = re.match(pattern, value)
        if match:
            return match.group(1)
    return None


def _git_value(repo_root: Path, *args: str, runner: CommandRunner) -> str | None:
    return _text_command(["git", "-C", str(repo_root), *args], runner=runner)


def _collect_source(
    repo_root: Path,
    *,
    repository: str | None,
    runner: CommandRunner,
) -> tuple[dict[str, Any], str | None]:
    root = repo_root.expanduser().resolve()
    head = _git_value(root, "rev-parse", "HEAD", runner=runner)
    top = _git_value(root, "rev-parse", "--show-toplevel", runner=runner)
    if not head or not top:
        return {"status": "UNAVAILABLE", "repo_root": str(root)}, repository

    remote = _git_value(root, "remote", "get-url", "origin", runner=runner)
    repo_name = repository or _repository_from_remote(remote)
    porcelain = _git_value(root, "status", "--porcelain=v1", runner=runner) or ""
    source = {
        "status": "OBSERVED",
        "repo_root": top,
        "repository": repo_name,
        "branch": _git_value(root, "branch", "--show-current", runner=runner) or None,
        "head": head,
        "dirty": bool(porcelain),
        "dirty_entry_count": len(porcelain.splitlines()),
        "origin_main": _git_value(root, "rev-parse", "refs/remotes/origin/main", runner=runner),
        "github_main": None,
        "default_branch": None,
        "github_observation_error": None,
    }
    if repo_name:
        meta, error = _json_command(["gh", "api", f"repos/{repo_name}"], cwd=root, runner=runner)
        source["github_observation_error"] = error
        if isinstance(meta, dict):
            default_branch = meta.get("default_branch")
            source["default_branch"] = default_branch
            if isinstance(default_branch, str) and default_branch:
                branch_data, branch_error = _json_command(
                    ["gh", "api", f"repos/{repo_name}/branches/{default_branch}"],
                    cwd=root,
                    runner=runner,
                )
                if isinstance(branch_data, dict) and isinstance(branch_data.get("commit"), dict):
                    source["github_main"] = branch_data["commit"].get("sha")
                if branch_error and source["github_observation_error"] is None:
                    source["github_observation_error"] = branch_error
    source["head_is_github_main"] = bool(
        source["github_main"] and source["head"] == source["github_main"]
    )
    return source, repo_name


def _collect_task(
    repository: str | None,
    issue_number: int | None,
    *,
    repo_root: Path,
    runner: CommandRunner,
) -> dict[str, Any]:
    if issue_number is None:
        return {"issue_number": None, "status": "NOT_REQUESTED"}
    if not repository:
        return {
            "issue_number": issue_number,
            "status": "UNKNOWN",
            "error": "REPOSITORY_IDENTITY_UNAVAILABLE",
        }
    data, error = _json_command(
        ["gh", "api", f"repos/{repository}/issues/{issue_number}"],
        cwd=repo_root,
        runner=runner,
    )
    if not isinstance(data, dict):
        return {
            "issue_number": issue_number,
            "status": "UNKNOWN",
            "error": error or "ISSUE_READ_FAILED",
        }
    return {
        "issue_number": issue_number,
        "status": "OBSERVED",
        "state": data.get("state"),
        "title": data.get("title"),
        "updated_at": data.get("updated_at"),
        "url": data.get("html_url"),
    }


def _required_check_names(rules: Any) -> tuple[set[str], str]:
    if not isinstance(rules, list):
        return set(), "UNKNOWN"
    required: set[str] = set()
    observed = False
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("type") != "required_status_checks":
            continue
        observed = True
        params = rule.get("parameters")
        rows = params.get("required_status_checks") if isinstance(params, dict) else None
        for row in rows if isinstance(rows, list) else []:
            context = row.get("context") if isinstance(row, dict) else None
            if isinstance(context, str) and context:
                required.add(context)
    return required, "OBSERVED" if observed else "OBSERVED_NO_REQUIRED_CHECKS"


def _collect_pr(
    repository: str | None,
    pr_number: int | None,
    *,
    repo_root: Path,
    runner: CommandRunner,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if pr_number is None:
        return {"pr_number": None, "status": "NOT_REQUESTED"}, [], [], []
    if not repository:
        return (
            {
                "pr_number": pr_number,
                "status": "UNKNOWN",
                "error": "REPOSITORY_IDENTITY_UNAVAILABLE",
            },
            [],
            [],
            [],
        )

    pr, error = _json_command(
        ["gh", "api", f"repos/{repository}/pulls/{pr_number}"],
        cwd=repo_root,
        runner=runner,
    )
    if not isinstance(pr, dict):
        return (
            {"pr_number": pr_number, "status": "UNKNOWN", "error": error or "PR_READ_FAILED"},
            [],
            [],
            [],
        )

    head = pr.get("head") if isinstance(pr.get("head"), dict) else {}
    base = pr.get("base") if isinstance(pr.get("base"), dict) else {}
    head_sha = head.get("sha")
    base_ref = base.get("ref") or "main"
    checks_payload, checks_error = _json_command(
        ["gh", "api", f"repos/{repository}/commits/{head_sha}/check-runs?per_page=100"],
        cwd=repo_root,
        runner=runner,
    )
    latest: dict[str, dict[str, Any]] = {}
    rows = checks_payload.get("check_runs", []) if isinstance(checks_payload, dict) else []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            continue
        name = row["name"]
        if name not in latest or int(row.get("id") or 0) >= int(latest[name].get("id") or 0):
            latest[name] = row

    rules, rules_error = _json_command(
        ["gh", "api", f"repos/{repository}/rules/branches/{base_ref}"],
        cwd=repo_root,
        runner=runner,
    )
    required_names, policy_state = _required_check_names(rules)
    required = []
    for name in sorted(required_names):
        row = latest.get(name)
        required.append({
            "name": name,
            "policy_role": "REQUIRED_GATE",
            "status": row.get("status") if row else "missing",
            "conclusion": row.get("conclusion") if row else None,
            "details_url": row.get("details_url") if row else None,
        })

    advisory, unknown = [], []
    for name, row in sorted(latest.items()):
        item = {
            "name": name,
            "status": row.get("status"),
            "conclusion": row.get("conclusion"),
            "details_url": row.get("details_url"),
        }
        if policy_state == "UNKNOWN":
            item["policy_role"] = "UNKNOWN_POLICY_ROLE"
            unknown.append(item)
        elif name not in required_names:
            item["policy_role"] = "ADVISORY_CHECK"
            status = str(row.get("status") or "").strip().lower()
            conclusion = str(row.get("conclusion") or "").strip().lower()
            if status in {
                "in_progress",
                "queued",
                "pending",
                "requested",
                "waiting",
            } or conclusion in {
                "timed_out",
                "action_required",
            }:
                item["observer_state"] = "ADVISORY_INCOMPLETE"
            elif conclusion in {"failure", "cancelled"}:
                item["observer_state"] = "ADVISORY_FAILED"
            elif conclusion in {"success", "neutral", "skipped"}:
                item["observer_state"] = "OK"
            else:
                item["observer_state"] = "OBSERVED"
            advisory.append(item)

    return (
        {
            "pr_number": pr_number,
            "status": "OBSERVED",
            "state": pr.get("state"),
            "draft": bool(pr.get("draft")),
            "mergeable": pr.get("mergeable"),
            "mergeable_state": pr.get("mergeable_state"),
            "url": pr.get("html_url"),
            "head_sha": head_sha,
            "head_ref": head.get("ref"),
            "base_sha": base.get("sha"),
            "base_ref": base_ref,
            "gate_policy_state": policy_state,
            "check_observation_error": checks_error,
            "gate_policy_error": rules_error,
        },
        required,
        advisory,
        unknown,
    )


def _collect_runtime(*, home: Path, runner: CommandRunner) -> dict[str, Any]:
    binary = home / ".local/bin/nexus-host-sync"
    if not binary.exists() and not binary.is_symlink():
        return {
            "status": "UNAVAILABLE",
            "entrypoint": str(binary),
            "error": "NEXUS_HOST_SYNC_NOT_FOUND",
        }
    payload, error = _json_command([str(binary), "status"], runner=runner, timeout=20.0)
    if not isinstance(payload, dict):
        return {
            "status": "UNKNOWN",
            "entrypoint": str(binary),
            "error": error or "HOST_SYNC_STATUS_FAILED",
        }
    return {
        "status": "OBSERVED",
        "entrypoint": str(binary),
        "host": payload.get("host"),
        "state": payload.get("state"),
        "installed_revision": payload.get("installed_revision"),
        "installed_bundle_sha256": payload.get("installed_bundle_sha256"),
        "desired_revision": payload.get("desired_revision"),
        "source_revision_match": payload.get("source_revision_match"),
        "components": payload.get("components", {}),
        "last_sync": payload.get("last_sync"),
    }


def _collect_quota_snapshot(home: Path) -> dict[str, Any]:
    path = home / ".nexus/agy-account-pool/quota-snapshot.json"
    if not path.is_file():
        return {
            "status": "UNAVAILABLE",
            "path": str(path),
            "checked_at": None,
            "age_seconds": None,
            "account_count": 0,
            "accounts": [],
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "UNKNOWN",
            "path": str(path),
            "checked_at": None,
            "age_seconds": None,
            "account_count": 0,
            "accounts": [],
            "error": "QUOTA_SNAPSHOT_INVALID",
        }
    if not isinstance(payload, dict):
        return {
            "status": "UNKNOWN",
            "path": str(path),
            "checked_at": None,
            "age_seconds": None,
            "account_count": 0,
            "accounts": [],
            "error": "QUOTA_SNAPSHOT_INVALID",
        }

    checked_at = payload.get("checked_at")
    age_seconds = None
    if isinstance(checked_at, str):
        try:
            observed = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
            age_seconds = max(
                0.0,
                (datetime.now(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds(),
            )
        except ValueError:
            age_seconds = None

    accounts = []
    rows = payload.get("accounts")
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("account"), str):
                continue
            accounts.append({
                "account": row.get("account"),
                "ok": row.get("ok"),
                "checked_at": row.get("checked_at"),
                "error": row.get("error"),
                "groups": row.get("groups", {}),
            })
    return {
        "status": "OBSERVED",
        "path": str(path),
        "checked_at": checked_at,
        "age_seconds": age_seconds,
        "account_count": len(accounts),
        "accounts": accounts,
    }


def _runtime_main_alignment(
    runtime: dict[str, Any],
    github_main: str | None,
) -> dict[str, Any]:
    if runtime.get("status") != "OBSERVED" or not github_main:
        return {
            "status": "UNKNOWN",
            "basis": None,
            "current_main": github_main,
        }

    installed_revision = runtime.get("installed_revision")
    if installed_revision == github_main:
        return {
            "status": "ALIGNED",
            "basis": "EXACT_REVISION",
            "current_main": github_main,
        }

    installed_bundle = runtime.get("installed_bundle_sha256")
    last_sync = runtime.get("last_sync")
    if (
        isinstance(last_sync, dict)
        and last_sync.get("state") == "ALIGNED"
        and last_sync.get("desired_revision") == github_main
        and installed_bundle
        and last_sync.get("desired_bundle_sha256") == installed_bundle
        and last_sync.get("installed_bundle_sha256") == installed_bundle
    ):
        return {
            "status": "ALIGNED",
            "basis": "CONTENT_EQUIVALENT_LAST_SYNC",
            "current_main": github_main,
            "installed_revision": installed_revision,
            "installed_bundle_sha256": installed_bundle,
        }

    return {
        "status": "DRIFT",
        "basis": "NO_CURRENT_MAIN_BINDING",
        "current_main": github_main,
        "installed_revision": installed_revision,
        "installed_bundle_sha256": installed_bundle,
    }


def _operation_path(home: Path, operation_id: str) -> Path | None:
    if operation_id.startswith("agyop_"):
        return (
            home / ".local/state/nexus-agy-operations/operations" / operation_id / "operation.json"
        )
    for prefix, provider in _EXTERNAL_PREFIXES.items():
        if operation_id.startswith(prefix):
            return (
                home
                / ".local/state/nexus-external-worker"
                / provider
                / "operations"
                / operation_id
                / "operation.json"
            )
    return None


def _read_operation(path: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return public_operation_view(raw) if isinstance(raw, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _collect_operations(
    home: Path,
    operation_id: str | None,
    *,
    repo_root: Path,
) -> dict[str, Any]:
    selected, selected_error = None, None
    if operation_id:
        path = _operation_path(home, operation_id)
        if path is None:
            selected_error = "OPERATION_PROVIDER_UNKNOWN"
        else:
            selected = _read_operation(path)
            if selected is None:
                selected_error = "OPERATION_NOT_FOUND_OR_INVALID"

    roots = [home / ".local/state/nexus-agy-operations/operations"]
    external_root = home / ".local/state/nexus-external-worker"
    if external_root.is_dir():
        roots.extend(path / "operations" for path in external_root.iterdir() if path.is_dir())
    rows: list[dict[str, Any]] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.glob("*/operation.json"):
            row = _read_operation(path)
            if row is not None:
                rows.append(row)
    rows.sort(
        key=lambda row: (str(row.get("created_at") or ""), str(row.get("operation_id") or "")),
        reverse=True,
    )
    active_all = [row for row in rows if row.get("status") in ACTIVE_STATES]
    repo_root_text = str(repo_root.resolve())
    active = [row for row in active_all if row.get("repo_root") == repo_root_text]
    terminal = [
        row
        for row in rows
        if row.get("status") in TERMINAL_STATES and row.get("repo_root") == repo_root_text
    ]
    return {
        "requested_id": operation_id,
        "selected": selected,
        "selected_error": selected_error,
        "active": active[:20],
        "all_active_count": len(active_all),
        "latest_terminal": terminal[0] if terminal else None,
    }


def _marker_view(path: Path, keys: tuple[str, ...]) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"path": str(path), "status": "UNREADABLE"}
    result = {"path": str(path), "status": "OBSERVED"}
    if isinstance(payload, dict):
        for key in keys:
            if key in payload:
                result[key] = payload.get(key)
    return result


def _collect_leases(home: Path) -> dict[str, Any]:
    root = home / ".nexus/agy-account-pool/leases"
    if not root.is_dir():
        return {"root": str(root), "active": [], "family_unavailable": [], "quarantined": []}
    active = [
        _marker_view(
            path,
            (
                "account_alias_hash",
                "lease_id_hash",
                "consumer_id",
                "pid",
                "acquired_at",
                "claimed_at",
            ),
        )
        for path in sorted(root.glob("*.receipt.json"))
    ]
    family = [
        _marker_view(
            path,
            (
                "account_alias_hash",
                "model_family",
                "reason",
                "unavailable_at",
                "unavailable_until",
                "lease_id_hash",
                "consumer_id",
                "pid",
            ),
        )
        for path in sorted(root.glob("*.family-unavailable.*.json"))
    ]
    quarantined = [
        _marker_view(
            path,
            (
                "account_alias_hash",
                "reason",
                "quarantined_at",
                "lease_id_hash",
                "consumer_id",
                "pid",
            ),
        )
        for path in sorted(root.glob("*.quarantine.json"))
    ]
    return {
        "root": str(root),
        "active": active,
        "family_unavailable": family,
        "quarantined": quarantined,
    }


def _derive_next_gate(
    *,
    source: dict[str, Any],
    runtime: dict[str, Any],
    task: dict[str, Any],
    operation: dict[str, Any],
    pr: dict[str, Any],
    required_gates: list[dict[str, Any]],
    leases: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    if source.get("status") != "OBSERVED":
        return "BLOCKED", {
            "code": "SOURCE_IDENTITY_UNAVAILABLE",
            "reason": "Git source identity could not be observed.",
        }

    selected = operation.get("selected")
    active = operation.get("active") or []
    if isinstance(selected, dict) and (
        selected.get("status") == "OUTCOME_UNKNOWN" or selected.get("phase") == "RECONCILE_REQUIRED"
    ):
        return "RECONCILE", {
            "code": "RECONCILE_OPERATION",
            "reason": "Requested operation has outcome-unknown or reconcile-required state; do not replay blindly.",
            "operation_id": selected.get("operation_id"),
        }
    reconcile_active = [
        row
        for row in active
        if row.get("status") == "OUTCOME_UNKNOWN" or row.get("phase") == "RECONCILE_REQUIRED"
    ]
    if reconcile_active:
        return "RECONCILE", {
            "code": "RECONCILE_OPERATION",
            "reason": "At least one durable operation requires reconciliation before continuing.",
            "operation_ids": [
                str(row["operation_id"]) for row in reconcile_active if row.get("operation_id")
            ],
        }
    if operation.get("requested_id") and selected is None:
        return "BLOCKED", {
            "code": "REQUESTED_OPERATION_UNAVAILABLE",
            "reason": operation.get("selected_error")
            or "Requested operation evidence is unavailable.",
        }
    if isinstance(selected, dict) and selected.get("status") in ACTIVE_STATES:
        return "WAIT", {
            "code": "OBSERVE_REQUESTED_OPERATION",
            "reason": "Requested durable operation is still active.",
            "operation_ids": [selected.get("operation_id")],
        }
    if active:
        return "WAIT", {
            "code": "OBSERVE_ACTIVE_OPERATION",
            "reason": "At least one durable operation for this repository is still active.",
            "operation_ids": [row.get("operation_id") for row in active],
        }

    if source.get("repository") and not source.get("github_main"):
        return "BLOCKED", {
            "code": "GITHUB_MAIN_UNAVAILABLE",
            "reason": "Current GitHub default-branch identity could not be observed.",
            "error": source.get("github_observation_error"),
        }

    pr_status = pr.get("status")
    pr_open = pr_status == "OBSERVED" and pr.get("state") == "open"

    if pr.get("pr_number") is not None and pr_status == "UNKNOWN":
        return "BLOCKED", {
            "code": "PR_EVIDENCE_UNAVAILABLE",
            "reason": pr.get("error") or "Pull-request evidence is unavailable.",
        }

    if pr_open:
        if pr.get("gate_policy_state") == "UNKNOWN":
            return "BLOCKED", {
                "code": "VERIFY_REQUIRED_GATE_POLICY",
                "reason": "Required-check policy is unknown; merge readiness cannot be inferred.",
                "error": pr.get("gate_policy_error"),
            }
        if pr.get("check_observation_error"):
            return "BLOCKED", {
                "code": "VERIFY_PR_CHECK_EVIDENCE",
                "reason": "Exact-head check evidence could not be observed.",
                "error": pr.get("check_observation_error"),
            }

        failed = [
            row
            for row in required_gates
            if row.get("conclusion") not in {None, "success", "neutral", "skipped"}
        ]
        if failed:
            return "BLOCKED", {
                "code": "FIX_REQUIRED_GATE",
                "reason": "At least one authoritative required gate failed.",
                "checks": [row.get("name") for row in failed],
            }
        waiting = [
            row
            for row in required_gates
            if row.get("status") != "completed" or row.get("conclusion") is None
        ]
        if waiting:
            return "WAIT", {
                "code": "WAIT_REQUIRED_GATES",
                "reason": "Authoritative required gates are not terminal-success yet.",
                "checks": [row.get("name") for row in waiting],
            }
        if pr.get("draft"):
            return "BLOCKED", {
                "code": "PR_DRAFT",
                "reason": "Pull request is still draft.",
            }
        if pr.get("mergeable") is False:
            return "BLOCKED", {
                "code": "RESOLVE_PR_MERGEABILITY",
                "reason": "GitHub reports the pull request is not mergeable.",
            }
        if (
            source.get("github_main")
            and pr.get("base_sha")
            and source["github_main"] != pr["base_sha"]
        ):
            return "RECONCILE", {
                "code": "REQUALIFY_MAIN_MOVEMENT",
                "reason": "PR base differs from current main; apply main-movement requalification before merge.",
                "pr_base": pr.get("base_sha"),
                "github_main": source.get("github_main"),
            }
        return "SAFE", {
            "code": "EXACT_HEAD_MERGE_GATE",
            "reason": "PR required gates are successful; merge still requires current Owner confirmation and expected-head/CAS.",
            "pr_number": pr.get("pr_number"),
            "head_sha": pr.get("head_sha"),
        }

    issue_open = task.get("status") == "OBSERVED" and task.get("state") == "open"
    if task.get("issue_number") is not None and task.get("status") == "UNKNOWN":
        return "BLOCKED", {
            "code": "ISSUE_EVIDENCE_UNAVAILABLE",
            "reason": task.get("error") or "Issue evidence is unavailable.",
        }

    # Issue-only source work may proceed while an unrelated host runtime is older.
    # If a PR was requested and is now terminal, runtime alignment becomes the next
    # physical closeout gate before returning to remaining Issue work.
    if issue_open and pr.get("pr_number") is None:
        return "SAFE", {
            "code": "CONTINUE_BOUNDED_ISSUE_WORK",
            "reason": "Issue is open and no stronger source-work blocker was observed.",
            "issue_number": task.get("issue_number"),
        }

    if runtime.get("status") == "OBSERVED":
        components = runtime.get("components")
        drifted = (
            [
                name
                for name, row in components.items()
                if isinstance(components, dict)
                and isinstance(row, dict)
                and row.get("status") != "VERIFIED"
            ]
            if isinstance(components, dict)
            else []
        )
        if runtime.get("state") in {"INVALID", "DEPENDENCY_DRIFT", "STALE"} or drifted:
            return "RECONCILE", {
                "code": "RECONCILE_RUNTIME",
                "reason": "Host runtime status reports drift or invalid state.",
                "components": drifted,
            }
        alignment = _runtime_main_alignment(runtime, source.get("github_main"))
        if alignment.get("status") == "DRIFT":
            return "RECONCILE", {
                "code": "SYNC_RUNTIME_TO_CURRENT_MAIN",
                "reason": "Host runtime has no exact or content-equivalent binding to current GitHub main.",
                "github_main": source.get("github_main"),
                "installed_revision": runtime.get("installed_revision"),
                "installed_bundle_sha256": runtime.get("installed_bundle_sha256"),
            }

    if pr_status == "OBSERVED" and pr.get("state") != "open":
        return "SAFE", {
            "code": "PR_TERMINAL",
            "reason": "Observed pull request is no longer open and runtime alignment is not blocking.",
        }

    if issue_open:
        return "SAFE", {
            "code": "CONTINUE_BOUNDED_ISSUE_WORK",
            "reason": "Issue is open and no stronger blocker was observed.",
            "issue_number": task.get("issue_number"),
        }

    return "SAFE", {
        "code": "NO_PENDING_GATE",
        "reason": "No non-terminal workflow blocker was observed.",
    }


def collect_workflow_doctor(
    *,
    repo_root: Path,
    repository: str | None = None,
    issue_number: int | None = None,
    pr_number: int | None = None,
    operation_id: str | None = None,
    home: Path | None = None,
    runner: CommandRunner = subprocess.run,
) -> dict[str, Any]:
    home = (home or Path.home()).expanduser().resolve()
    repo_root = repo_root.expanduser().resolve()
    source, repository = _collect_source(repo_root, repository=repository, runner=runner)
    task = _collect_task(repository, issue_number, repo_root=repo_root, runner=runner)
    pr, required, advisory, unknown = _collect_pr(
        repository, pr_number, repo_root=repo_root, runner=runner
    )
    runtime = _collect_runtime(home=home, runner=runner)
    runtime["current_main_alignment"] = _runtime_main_alignment(
        runtime,
        source.get("github_main"),
    )
    quota = _collect_quota_snapshot(home)
    operation = _collect_operations(
        home,
        operation_id,
        repo_root=repo_root,
    )
    leases = _collect_leases(home)
    disposition, next_gate = _derive_next_gate(
        source=source,
        runtime=runtime,
        task=task,
        operation=operation,
        pr=pr,
        required_gates=required,
        leases=leases,
    )
    if disposition not in RESUME_DISPOSITIONS:
        raise WorkflowDoctorError("INVALID_RESUME_DISPOSITION")
    return {
        "schema": SCHEMA,
        "generated_at": utc_now(),
        "host": socket.gethostname(),
        "task": task,
        "operation": operation,
        "source": source,
        "runtime": runtime,
        "quota": quota,
        "pr": pr,
        "required_gates": required,
        "advisory_observers": advisory,
        "unknown_policy_checks": unknown,
        "leases": leases,
        "next_gate": next_gate,
        "resume_disposition": disposition,
        "claim_ceiling": "READ_ONLY_WORKFLOW_OBSERVATION",
    }


def render_text(payload: dict[str, Any]) -> str:
    source = payload.get("source", {})
    runtime = payload.get("runtime", {})
    task = payload.get("task", {})
    pr = payload.get("pr", {})
    operation = payload.get("operation", {})
    gate = payload.get("next_gate", {})
    return "\n".join([
        f"resume={payload.get('resume_disposition')} next={gate.get('code')}",
        f"source head={source.get('head')} github_main={source.get('github_main')} dirty={source.get('dirty')}",
        f"runtime state={runtime.get('state')} installed={runtime.get('installed_revision')}",
        f"quota status={(payload.get('quota') or {}).get('status')} accounts={(payload.get('quota') or {}).get('account_count')}",
        f"issue={task.get('issue_number')} state={task.get('state')}",
        f"pr={pr.get('pr_number')} state={pr.get('state')} head={pr.get('head_sha')}",
        f"required_gates={len(payload.get('required_gates') or [])} advisory={len(payload.get('advisory_observers') or [])}",
        f"active_operations={len(operation.get('active') or [])} active_leases={len((payload.get('leases') or {}).get('active') or [])}",
    ])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--repository")
    parser.add_argument("--issue", dest="issue_number", type=int)
    parser.add_argument("--pr", dest="pr_number", type=int)
    parser.add_argument("--operation-id")
    parser.add_argument("--json", dest="as_json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    resolved_root = resolve_workflow_repo_root(args.repo_root, args.repository)
    payload = collect_workflow_doctor(
        repo_root=resolved_root,
        repository=args.repository,
        issue_number=args.issue_number,
        pr_number=args.pr_number,
        operation_id=args.operation_id,
    )
    print(json.dumps(payload, indent=2, sort_keys=True) if args.as_json else render_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
