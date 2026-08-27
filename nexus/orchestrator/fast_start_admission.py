"""Deterministic Fast Start Admission evaluator and launch fence.

G14 hard-enforcement gate: executes deterministic admission before any Codex
worker subprocess or provider session is created.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, Callable

from nexus.contracts.fast_start_admission import (
    FastStartAdmissionRequest,
    FastStartAdmissionResult,
    FastStartDecision,
    _sha256_json,
)

SCHEMA = "nexus.fast_start_admission.v1"
CACHE_SCHEMA = "nexus.fast_start_cache.v1"

_ISSUE_TASK_PATTERN = re.compile(
    r"(?:github[-_]issue[-_]|issue[-_]|#)(\d+)",
    re.IGNORECASE,
)


def extract_issue_number(
    task_id: str | None = None,
    prompt: str | None = None,
    context: Mapping[str, Any] | None = None,
) -> int | None:
    """Extract a GitHub issue number from task_id, context, or prompt."""
    if context and "issue" in context:
        try:
            return int(context["issue"])
        except (TypeError, ValueError):
            pass
    if context and "issue_number" in context:
        try:
            return int(context["issue_number"])
        except (TypeError, ValueError):
            pass

    for candidate in (task_id, prompt):
        if not candidate:
            continue
        match = _ISSUE_TASK_PATTERN.search(str(candidate))
        if match:
            try:
                return int(match.group(1))
            except (TypeError, ValueError):
                continue
    return None


def canonical_fast_start_registry_fetcher(
    token: str | None = None,
    opener: Callable[..., Any] | None = None,
) -> Mapping[str, Any] | None:
    """Canonical fetcher for #549 advisory cache registry."""
    import os

    from scripts.ops.fast_start_v2 import (
        REGISTRY_ISSUE,
        REPOSITORY,
        GitHubReadClient,
        _extract_header_hash,
        parse_registry_body,
        registry_payload_hash,
    )

    auth_token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if not auth_token:
        return None

    try:
        client = GitHubReadClient(auth_token, opener=opener)
        registry_issue = client.get(f"/repos/{REPOSITORY}/issues/{REGISTRY_ISSUE}")
        body = str(registry_issue.get("body") or "")
        payload = parse_registry_body(body)
        expected_hash = _extract_header_hash(body)
        actual_hash = registry_payload_hash(payload)
        if expected_hash != actual_hash:
            return None
        return payload
    except Exception:
        return None


def canonical_fast_start_metadata_fetcher(
    pr: int | None = None,
    issue: int | None = None,
    token: str | None = None,
    opener: Callable[..., Any] | None = None,
) -> Mapping[str, Any]:
    """Canonical metadata-only fetcher for blocker PR/Issue."""
    import os

    from scripts.ops.fast_start_v2 import REPOSITORY, GitHubReadClient

    auth_token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if not auth_token:
        return {}

    evidence: dict[str, Any] = {}
    try:
        client = GitHubReadClient(auth_token, opener=opener)
        if pr is not None:
            pr_data = client.get(f"/repos/{REPOSITORY}/pulls/{pr}")
            evidence["pr_state"] = pr_data.get("state")
            evidence["pr_merged"] = bool(pr_data.get("merged", False))
            head = pr_data.get("head") if isinstance(pr_data.get("head"), Mapping) else {}
            evidence["pr_head_sha"] = head.get("sha")
        if issue is not None:
            issue_data = client.get(f"/repos/{REPOSITORY}/issues/{issue}")
            evidence["issue_state"] = issue_data.get("state")
    except Exception as exc:
        evidence["rebind_error"] = str(exc)
    return evidence


def evaluate_fast_start_admission(
    request: FastStartAdmissionRequest,
    *,
    registry_fetcher: Callable[[], Mapping[str, Any] | None] | None = None,
    metadata_fetcher: Callable[..., Mapping[str, Any]] | None = None,
) -> FastStartAdmissionResult:
    """Deterministically evaluate Fast Start admission for a managed Codex task.

    Precedence:
    fresh current main/source identity > latest durable Issue contract > direct dependency / PR metadata > #549 advisory cache
    """
    issue_number = request.issue_number

    # Step 1: Non-issue tasks proceed via standard discovery
    if issue_number is None:
        return FastStartAdmissionResult(
            schema=SCHEMA,
            issue=None,
            decision=FastStartDecision.ALLOW_FULL_DISCOVERY,
            codex_launch_allowed=True,
            reason="Non-issue task - standard full discovery permitted",
            cache_disposition="NON_ISSUE_TASK",
            observed_main_sha=request.current_main_sha,
            observed_main_tree=request.current_main_tree,
        )

    # Step 2: Obtain registry snapshot (mandatory preflight for Issue-backed tasks)
    snapshot: Mapping[str, Any] | None = request.registry_snapshot
    if snapshot is None:
        fetcher = (
            registry_fetcher
            if registry_fetcher is not None
            else canonical_fast_start_registry_fetcher
        )
        try:
            snapshot = fetcher()
        except Exception:
            snapshot = None

    if snapshot is None:
        return FastStartAdmissionResult(
            schema=SCHEMA,
            issue=issue_number,
            decision=FastStartDecision.DENY_EVIDENCE_BLOCKED,
            codex_launch_allowed=False,
            reason="Fast Start registry preflight failed or cache unavailable for GitHub Issue task - fail closed to prevent ungated execution",
            cache_disposition="CACHE_UNAVAILABLE",
            observed_main_sha=request.current_main_sha,
            observed_main_tree=request.current_main_tree,
        )

    # Validate snapshot schema & payload
    if not isinstance(snapshot, Mapping) or snapshot.get("schema") != CACHE_SCHEMA:
        return FastStartAdmissionResult(
            schema=SCHEMA,
            issue=issue_number,
            decision=FastStartDecision.ALLOW_FULL_DISCOVERY,
            codex_launch_allowed=True,
            reason="Fast Start cache payload malformed or unsupported schema - fallback to full discovery",
            cache_disposition="CACHE_MALFORMED",
            observed_main_sha=request.current_main_sha,
            observed_main_tree=request.current_main_tree,
        )

    reg_hash = _sha256_json(snapshot)
    reg_revision = snapshot.get("registry_revision")
    if not isinstance(reg_revision, int):
        reg_revision = None

    # Step 3: Find entry for this issue
    entries = snapshot.get("entries")
    if not isinstance(entries, Sequence):
        entries = []
    entry = next(
        (e for e in entries if isinstance(e, Mapping) and e.get("issue") == issue_number), None
    )

    if entry is None:
        return FastStartAdmissionResult(
            schema=SCHEMA,
            issue=issue_number,
            decision=FastStartDecision.ALLOW_FULL_DISCOVERY,
            codex_launch_allowed=True,
            reason=f"Issue #{issue_number} not in Fast Start advisory cache - fallback to full discovery",
            registry_revision=reg_revision,
            registry_hash=reg_hash,
            cache_disposition="CACHE_MISS",
            observed_main_sha=request.current_main_sha,
            observed_main_tree=request.current_main_tree,
        )

    # Step 4: Evaluate entry dispatch state
    dispatch_state = str(entry.get("dispatch_state") or "").upper()
    blocker_val = entry.get("blocker")
    blocker_dict: Mapping[str, Any] = blocker_val if isinstance(blocker_val, Mapping) else {}
    observed_blockers: list[dict[str, Any]] = []
    fresh_evidence: dict[str, Any] = {}

    decision = FastStartDecision.ALLOW_FULL_DISCOVERY
    codex_allowed = True
    reason = ""
    disposition = "CACHE_HIT"

    if dispatch_state in {"BLOCKED_UPSTREAM", "BLOCKED_PR", "BLOCKED"}:
        blocker_pr = blocker_dict.get("pr")
        blocker_issue = blocker_dict.get("issue")
        if blocker_pr is None and blocker_issue is None:
            decision = FastStartDecision.DENY_BLOCKED
            codex_allowed = False
            reason = "Entry marked BLOCKED without specific rebind targets"
        else:
            observed_b: dict[str, Any] = {}
            if blocker_pr is not None:
                observed_b["pr"] = blocker_pr
            if blocker_issue is not None:
                observed_b["issue"] = blocker_issue

            # Metadata-only fresh rebind. Cache cannot prove a blocker is gone.
            meta_fetcher = (
                metadata_fetcher
                if metadata_fetcher is not None
                else canonical_fast_start_metadata_fetcher
            )
            rebind_failed = False
            try:
                rebound = meta_fetcher(pr=blocker_pr, issue=blocker_issue)
                if isinstance(rebound, Mapping):
                    fresh_evidence.update(rebound)
                    if rebound.get("pr_state") is not None:
                        observed_b["state"] = rebound["pr_state"]
                    if rebound.get("pr_merged") is not None:
                        observed_b["merged"] = rebound["pr_merged"]
                    if rebound.get("pr_head_sha") is not None:
                        observed_b["head_sha"] = rebound["pr_head_sha"]
                    if rebound.get("issue_state") is not None:
                        observed_b["issue_state"] = rebound["issue_state"]
                else:
                    rebind_failed = True
                    fresh_evidence["rebind_error"] = "metadata_fetcher returned non-mapping"
            except Exception as exc:
                rebind_failed = True
                fresh_evidence["rebind_error"] = str(exc)

            if "rebind_error" in fresh_evidence:
                rebind_failed = True

            observed_blockers.append(observed_b)

            has_pr_state = fresh_evidence.get("pr_state") not in (None, "")
            has_pr_merged = fresh_evidence.get("pr_merged") is not None
            has_issue_state = fresh_evidence.get("issue_state") not in (None, "")
            sufficient = (
                (has_pr_state or has_pr_merged) if blocker_pr is not None else has_issue_state
            )

            if rebind_failed or not sufficient:
                decision = FastStartDecision.DENY_EVIDENCE_BLOCKED
                codex_allowed = False
                reason = (
                    "Blocked Fast Start entry requires fresh metadata-only rebind; "
                    "blocker evidence missing or rebind failed"
                )
                disposition = "CACHE_HIT"
            else:
                pr_state = str(fresh_evidence.get("pr_state") or "").lower()
                pr_merged = bool(fresh_evidence.get("pr_merged", False))
                issue_state = str(fresh_evidence.get("issue_state") or "").lower()
                pr_terminal = blocker_pr is not None and (
                    pr_merged or pr_state in {"closed", "merged"}
                )
                issue_terminal = (
                    blocker_pr is None and blocker_issue is not None and issue_state == "closed"
                )
                if pr_terminal or issue_terminal:
                    decision = FastStartDecision.ALLOW_FULL_DISCOVERY
                    codex_allowed = True
                    reason = (
                        "Upstream blocker resolved in fresh metadata - "
                        "proceeding to authoritative full discovery"
                    )
                    disposition = "TARGETED_REBIND"
                elif blocker_pr is not None:
                    decision = FastStartDecision.DENY_BLOCKED
                    codex_allowed = False
                    reason = (
                        f"Upstream blocker PR #{blocker_pr} is still "
                        f"{pr_state.upper() or 'OPEN'} (head {observed_b.get('head_sha')})"
                    )
                    disposition = "LIGHT_REBIND"
                else:
                    decision = FastStartDecision.DENY_BLOCKED
                    codex_allowed = False
                    reason = (
                        f"Upstream blocker Issue #{blocker_issue} is still "
                        f"{issue_state.upper() or 'OPEN'}"
                    )
                    disposition = "LIGHT_REBIND"

    elif dispatch_state in {"HOST_REBIND_REQUIRED", "HOST_BOUND"}:
        decision = FastStartDecision.DENY_HOST_BOUND
        codex_allowed = False
        reason = (
            "Task requires host-bound local authority/OAuth session - GitHub Codex dispatch denied"
        )
        disposition = "CACHE_HIT"

    elif dispatch_state == "NEEDS_DECISION":
        decision = FastStartDecision.DENY_NEEDS_DECISION
        codex_allowed = False
        reason = "Task requires explicit Owner decision before implementation"
        disposition = "CACHE_HIT"

    elif dispatch_state == "EVIDENCE_BLOCKED":
        decision = FastStartDecision.DENY_EVIDENCE_BLOCKED
        codex_allowed = False
        reason = "Required governance or runtime evidence incomplete - dispatch denied"
        disposition = "CACHE_HIT"

    elif dispatch_state == "READY_CANDIDATE":
        cached_main = snapshot.get("snapshot", {}).get("main_sha")

        # Check for main drift
        if request.current_main_sha and cached_main and request.current_main_sha != cached_main:
            decision = FastStartDecision.ALLOW_FULL_DISCOVERY
            codex_allowed = True
            reason = f"Main SHA drifted ({cached_main[:8]} -> {request.current_main_sha[:8]}) - targeted discovery required"
            disposition = "TARGETED_REBIND"
        else:
            decision = FastStartDecision.ALLOW_READY
            codex_allowed = True
            reason = "Fresh evidence compatible and ready for execution"
            disposition = "CACHE_HIT"

    else:
        decision = FastStartDecision.ALLOW_FULL_DISCOVERY
        codex_allowed = True
        reason = f"Unknown dispatch state '{dispatch_state}' - fallback to full discovery"
        disposition = "CACHE_HIT"

    # Step 5: Compute launch fence digest
    fence_digest = _sha256_json({
        "issue": issue_number,
        "main_sha": request.current_main_sha,
        "main_tree": request.current_main_tree,
        "registry_revision": reg_revision,
        "registry_hash": reg_hash,
        "blockers": observed_blockers,
        "decision": decision.value,
    })

    return FastStartAdmissionResult(
        schema=SCHEMA,
        issue=issue_number,
        decision=decision,
        codex_launch_allowed=codex_allowed,
        reason=reason,
        registry_revision=reg_revision,
        registry_hash=reg_hash,
        observed_main_sha=request.current_main_sha,
        observed_main_tree=request.current_main_tree,
        observed_blockers=tuple(observed_blockers),
        cache_disposition=disposition,
        dispatch_state=dispatch_state,
        fresh_rebind_evidence=fresh_evidence,
        fence_digest=fence_digest,
    )


def validate_admission_fence(
    receipt: FastStartAdmissionResult,
    *,
    current_main_sha: str | None = None,
    current_main_tree: str | None = None,
    current_blockers: Sequence[Mapping[str, Any]] | None = None,
) -> bool:
    """Validate that a Fast Start admission receipt has not suffered TOCTOU drift."""
    if receipt.observed_main_sha is not None and current_main_sha is not None:
        if receipt.observed_main_sha != current_main_sha:
            return False
    if receipt.observed_main_tree is not None and current_main_tree is not None:
        if receipt.observed_main_tree != current_main_tree:
            return False

    if current_blockers is not None and receipt.observed_blockers:
        # Check that blockers have not drifted
        receipt_blocker_map = {b.get("pr"): b for b in receipt.observed_blockers if "pr" in b}
        for cb in current_blockers:
            pr = cb.get("pr")
            if pr in receipt_blocker_map:
                rb = receipt_blocker_map[pr]
                if cb.get("state") != rb.get("state") or cb.get("head_sha") != rb.get("head_sha"):
                    return False

    # Check fence digest integrity
    expected_digest = _sha256_json({
        "issue": receipt.issue,
        "main_sha": receipt.observed_main_sha,
        "main_tree": receipt.observed_main_tree,
        "registry_revision": receipt.registry_revision,
        "registry_hash": receipt.registry_hash,
        "blockers": list(receipt.observed_blockers),
        "decision": receipt.decision.value
        if isinstance(receipt.decision, FastStartDecision)
        else str(receipt.decision),
    })
    return receipt.fence_digest == expected_digest
