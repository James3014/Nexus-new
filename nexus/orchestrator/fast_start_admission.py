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
    """Extract a GitHub issue number from task_id, context, or prompt.

    Launch choke points must use resolve_issue_identity(); this helper remains
    for legacy text/context lookup and does not grant launch authority.
    """
    if context:
        for key in ("github_issue_number", "issue_number", "issue"):
            if key not in context:
                continue
            parsed = _parse_structured_issue(context.get(key), fail_closed=False)
            if parsed is not None:
                return parsed

    return extract_issue_number_from_text(task_id, prompt)


def extract_issue_number_from_text(
    task_id: str | None = None,
    prompt: str | None = None,
) -> int | None:
    """Legacy text-only Issue number extraction. Not launch authority."""
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


def parse_strict_github_issue_number(value: Any) -> int:
    """Strict Issue identity parser. Rejects bool/float/zero/truncation."""
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError("invalid structured GitHub issue identity")
    if isinstance(value, int):
        if value < 1:
            raise ValueError("invalid structured GitHub issue identity")
        return value
    if isinstance(value, str):
        if not value.isdigit() or value != str(int(value)):
            raise ValueError("invalid structured GitHub issue identity")
        parsed = int(value)
        if parsed < 1:
            raise ValueError("invalid structured GitHub issue identity")
        return parsed
    raise ValueError("invalid structured GitHub issue identity")


def _parse_structured_issue(value: Any, *, fail_closed: bool = True) -> int | None:
    if value is None or value == "":
        return None
    try:
        return parse_strict_github_issue_number(value)
    except ValueError:
        if fail_closed:
            raise
        return None


def structured_issue_from_context(context: Mapping[str, Any] | None) -> Any:
    if not isinstance(context, Mapping):
        return None
    for key in ("github_issue_number", "issue_number", "issue"):
        if key in context and context.get(key) not in (None, ""):
            return context.get(key)
    return None


_GITHUB_ISSUE_ORIGIN_RE = re.compile(r"github[-_]issue(?:-(\d+))?", re.IGNORECASE)


def _origin_issue_from_text(value: Any) -> tuple[bool, int | None]:
    if value is None:
        return False, None
    text = str(value).strip()
    if not text:
        return False, None
    match = _GITHUB_ISSUE_ORIGIN_RE.search(text)
    if not match:
        return False, None
    if match.group(1):
        return True, int(match.group(1))
    return True, None


def bind_trusted_github_issue_identity(request: Mapping[str, Any]) -> int | None:
    """Bind Issue identity from durable origin, not caller field names."""
    origin_values: list[Any] = [
        request.get("task_card_path"),
        request.get("campaign_id"),
    ]
    identity = request.get("task_card_identity")
    if isinstance(identity, Mapping):
        origin_values.extend((
            identity.get("task_card_path"),
            identity.get("canonical_task_card_path"),
        ))

    trusted: list[int] = []
    origin_present = False
    missing_origin_number = False
    for raw in origin_values:
        is_origin, number = _origin_issue_from_text(raw)
        if not is_origin:
            continue
        origin_present = True
        if number is None:
            missing_origin_number = True
            continue
        trusted.append(number)
    if trusted and len(set(trusted)) > 1:
        raise ValueError("GITHUB_ISSUE_IDENTITY_CONFLICT")
    if origin_present and not trusted:
        raise ValueError("GITHUB_ISSUE_IDENTITY_MISSING")
    if missing_origin_number and not trusted:
        raise ValueError("GITHUB_ISSUE_IDENTITY_MISSING")

    aliases: list[int] = []
    for key in ("github_issue_number", "issue_number", "issue"):
        if key not in request or request.get(key) in (None, ""):
            continue
        aliases.append(parse_strict_github_issue_number(request.get(key)))
    if aliases and len(set(aliases)) > 1:
        raise ValueError("GITHUB_ISSUE_IDENTITY_CONFLICT")

    trusted_issue = trusted[0] if trusted else None
    alias_issue = aliases[0] if aliases else None
    if trusted_issue is not None and alias_issue is not None and trusted_issue != alias_issue:
        raise ValueError("GITHUB_ISSUE_IDENTITY_CONFLICT")
    if origin_present and trusted_issue is None:
        raise ValueError("GITHUB_ISSUE_IDENTITY_MISSING")
    return trusted_issue


def resolve_issue_identity(
    *,
    structured_issue: Any = None,
    task_id: str | None = None,
    prompt: str | None = None,
) -> tuple[int | None, str, int | None, int | None]:
    """Resolve current Issue identity.

    Returns (issue_number, source, structured_issue, text_issue).
    source is STRUCTURED, TEXT_FALLBACK, NON_ISSUE, or CONFLICT.
    """
    try:
        structured = _parse_structured_issue(structured_issue)
    except ValueError:
        text = extract_issue_number_from_text(task_id, prompt)
        return None, "CONFLICT", None, text

    text = extract_issue_number_from_text(task_id, prompt)
    if structured is not None and text is not None and structured != text:
        return None, "CONFLICT", structured, text
    if structured is not None:
        return structured, "STRUCTURED", structured, text
    if text is not None:
        return text, "TEXT_FALLBACK", None, text
    return None, "NON_ISSUE", None, None


def issue_identity_conflict_result(
    *,
    structured_issue: int | None,
    text_issue: int | None,
    current_main_sha: str | None = None,
    task_id: str | None = None,
) -> FastStartAdmissionResult:
    return FastStartAdmissionResult(
        schema=SCHEMA,
        issue=structured_issue,
        decision=FastStartDecision.DENY_EVIDENCE_BLOCKED,
        codex_launch_allowed=False,
        reason=(
            f"Structured Issue #{structured_issue} conflicts with text Issue #{text_issue} "
            "- fail closed"
        ),
        cache_disposition="IDENTITY_CONFLICT",
        observed_main_sha=current_main_sha,
    )


def _main_unavailable_result(
    *,
    issue: int | None,
    current_main_sha: str | None = None,
    current_main_tree: str | None = None,
) -> FastStartAdmissionResult:
    return FastStartAdmissionResult(
        schema=SCHEMA,
        issue=issue,
        decision=FastStartDecision.DENY_EVIDENCE_BLOCKED,
        codex_launch_allowed=False,
        reason="Fresh canonical main SHA/tree unavailable for GitHub Issue-backed Codex admission",
        cache_disposition="MAIN_UNAVAILABLE",
        observed_main_sha=current_main_sha,
        observed_main_tree=current_main_tree,
    )


def admit_managed_codex_launch(
    *,
    structured_issue: Any = None,
    task_id: str | None = None,
    prompt: str | None = None,
    current_main_sha: str | None = None,
    current_main_tree: str | None = None,
) -> FastStartAdmissionResult:
    """Production Fast Start admission. Caller snapshot/fetchers/main are not accepted."""
    _ = (current_main_sha, current_main_tree)
    issue_number, source, structured, text = resolve_issue_identity(
        structured_issue=structured_issue,
        task_id=task_id,
        prompt=prompt,
    )
    if source == "CONFLICT":
        return issue_identity_conflict_result(
            structured_issue=structured,
            text_issue=text,
            task_id=task_id,
        )
    if issue_number is None:
        return evaluate_fast_start_admission(
            FastStartAdmissionRequest(
                issue_number=None,
                task_id=task_id,
                registry_snapshot=None,
            )
        )
    main = canonical_current_main_identity()
    if main is None:
        return _main_unavailable_result(issue=issue_number)
    return evaluate_fast_start_admission(
        FastStartAdmissionRequest(
            issue_number=issue_number,
            current_main_sha=main[0],
            current_main_tree=main[1],
            task_id=task_id,
            registry_snapshot=None,
        )
    )


def revalidate_managed_codex_admission_at_launch(
    admission: FastStartAdmissionResult,
    *,
    structured_issue: Any = None,
    task_id: str | None = None,
    prompt: str | None = None,
) -> FastStartAdmissionResult:
    """TOCTOU fence immediately before physical Codex launch."""
    if admission.cache_disposition == "NON_ISSUE_TASK" or admission.issue is None:
        return admission
    if not admission.codex_launch_allowed:
        return admission
    fresh = canonical_current_main_identity()
    if fresh is None:
        return _main_unavailable_result(issue=admission.issue)
    current_blockers: list[dict[str, Any]] | None = None
    if admission.observed_blockers:
        current_blockers = []
        for blocker in admission.observed_blockers:
            rebound = canonical_fast_start_metadata_fetcher(
                pr=blocker.get("pr"),
                issue=blocker.get("issue"),
            )
            if not isinstance(rebound, Mapping) or rebound.get("rebind_error"):
                return FastStartAdmissionResult(
                    schema=SCHEMA,
                    issue=admission.issue,
                    decision=FastStartDecision.DENY_EVIDENCE_BLOCKED,
                    codex_launch_allowed=False,
                    reason="Launch-time blocker metadata rebind failed",
                    cache_disposition="CACHE_UNAVAILABLE",
                    observed_main_sha=fresh[0],
                    observed_main_tree=fresh[1],
                )
            current_blockers.append({
                "pr": blocker.get("pr"),
                "state": rebound.get("pr_state", blocker.get("state")),
                "head_sha": rebound.get("pr_head_sha", blocker.get("head_sha")),
                "merged": rebound.get("pr_merged", blocker.get("merged")),
                "issue": blocker.get("issue"),
            })
    if validate_admission_fence(
        admission,
        current_main_sha=fresh[0],
        current_main_tree=fresh[1],
        current_blockers=current_blockers,
    ):
        return admission
    return admit_managed_codex_launch(
        structured_issue=structured_issue,
        task_id=task_id,
        prompt=prompt,
    )


def canonical_current_main_identity(
    token: str | None = None,
    opener: Callable[..., Any] | None = None,
) -> tuple[str, str] | None:
    """Fresh canonical main SHA/tree for James3014/Nexus-new. Not caller evidence."""
    import os

    from scripts.ops.fast_start_v2 import REPOSITORY, GitHubReadClient

    auth_token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if not auth_token:
        return None
    try:
        client = GitHubReadClient(auth_token, opener=opener)
        branch = client.get(f"/repos/{REPOSITORY}/branches/main")
        commit = branch.get("commit") if isinstance(branch, Mapping) else None
        if not isinstance(commit, Mapping):
            return None
        sha = str(commit.get("sha") or "")
        nested_commit = commit.get("commit")
        if not isinstance(nested_commit, Mapping):
            return None
        tree = nested_commit.get("tree")
        if not isinstance(tree, Mapping):
            return None
        tree_sha = str(tree.get("sha") or "")
        if not sha or not tree_sha:
            return None
        return sha, tree_sha
    except Exception:
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
        if not request.current_main_sha:
            decision = FastStartDecision.DENY_EVIDENCE_BLOCKED
            codex_allowed = False
            reason = "READY_CANDIDATE requires fresh canonical main SHA"
            disposition = "MAIN_UNAVAILABLE"
        elif cached_main and request.current_main_sha != cached_main:
            decision = FastStartDecision.ALLOW_FULL_DISCOVERY
            codex_allowed = True
            reason = (
                f"Main SHA drifted ({cached_main[:8]} -> {request.current_main_sha[:8]}) "
                "- targeted discovery required"
            )
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
