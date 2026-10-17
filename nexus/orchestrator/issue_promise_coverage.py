"""Project a durable Core verdict onto an Issue's declared promises (#2532).

Pure function over immutable inputs: the card's ``nexus-issue-promises``
binding, the receipt's ``core_verdict`` (``ambient_core.build_core_verdict``)
and the head and Issue identity the reader expects now. It reads only Core
coverage entries; flags such as ``coverage_complete`` or ``claimed_items`` are
never evidence. It grants nothing: there is no approve, merge or close field,
and #2453's closer (not this module) decides what an incomplete result blocks.

Per promise:

- ``COVERED``: every mapped subject is satisfied, and at least one REQUIRED /
  APPLICABLE subject was observed with a PASS.
- ``NOT_COVERED``: a mapped subject was not observed, was observed without a
  PASS, or the evidence is not trustworthy (no verdict, unpinned Core).
- ``FAILED``: a mapped subject was observed with a FAIL.
- ``STALE``: the evidence is for another commit, universe, Issue contract or
  promise generation, or the live Issue binding was not confirmed.
- ``PENDING_EXTERNAL_WITNESS``: a POST_MERGE or HIGH-risk promise whose
  pre-merge part holds; only a #2453 live witness can finish it.

Overall: ``BLOCKED`` when the binding is invalid or any promise is FAILED or
STALE, ``COMPLETE`` when every promise is COVERED, otherwise ``PARTIAL``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from nexus.orchestrator.task_contract import (
    IssuePromiseBinding,
    IssuePromisePhase,
    IssuePromiseRisk,
)

ISSUE_PROMISE_COVERAGE_SCHEMA = "nexus.issue_promise_coverage.v1"
CLAIM_CEILING = "ISSUE_PROMISE_COVERAGE_PROJECTION_ONLY"

COVERED = "COVERED"
NOT_COVERED = "NOT_COVERED"
FAILED = "FAILED"
STALE = "STALE"
PENDING_EXTERNAL_WITNESS = "PENDING_EXTERNAL_WITNESS"

COMPLETE = "COMPLETE"
PARTIAL = "PARTIAL"
BLOCKED = "BLOCKED"

_PINNED = "CORE_REVISION_PINNED"
_HEAD_RE = re.compile(r"^[0-9a-f]{40}$")


def _stale_reasons(
    binding: IssuePromiseBinding,
    verdict: Mapping[str, Any] | None,
    expected_head: Any,
    evidence_head: Any,
    live_issue: Mapping[str, Any] | None,
) -> list[str]:
    reasons: list[str] = []
    if not isinstance(live_issue, Mapping):
        reasons.append("LIVE_ISSUE_BINDING_UNCONFIRMED")
    else:
        if live_issue.get("issue_contract_hash") != binding.issue_contract_hash:
            reasons.append("ISSUE_CONTRACT_CHANGED")
        if live_issue.get("promise_set_identity") != binding.promise_set.identity:
            reasons.append("PROMISE_SET_CHANGED")
    if verdict is not None:
        if evidence_head != expected_head:
            reasons.append("EVIDENCE_HEAD_MISMATCH")
        if verdict.get("core_universe_identity_matches") is not True:
            reasons.append("CORE_UNIVERSE_IDENTITY_MISMATCH")
    return reasons


def _untrusted_reasons(verdict: Mapping[str, Any] | None) -> list[str]:
    if verdict is None:
        return ["CORE_VERDICT_MISSING"]
    reasons: list[str] = []
    provenance = verdict.get("core_provenance")
    if not isinstance(provenance, Mapping) or provenance.get("status") != _PINNED:
        reasons.append("CORE_PROVENANCE_NOT_PINNED")
    coverage = verdict.get("coverage")
    entries = coverage.get("entries") if isinstance(coverage, Mapping) else None
    if not isinstance(entries, list) or not all(isinstance(e, Mapping) for e in entries):
        reasons.append("CORE_COVERAGE_MISSING")
    return reasons


def _entries_by_subject(verdict: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    coverage = verdict.get("coverage")
    entries = coverage.get("entries") if isinstance(coverage, Mapping) else None
    found: dict[str, Mapping[str, Any]] = {}
    duplicated: set[str] = set()
    for entry in entries if isinstance(entries, list) else ():
        if not isinstance(entry, Mapping):
            continue
        sid = entry.get("logical_subject_id")
        if not isinstance(sid, str):
            continue
        if sid in found:
            duplicated.add(sid)
        found[sid] = entry
    # A duplicated subject is ambiguous evidence; it never covers.
    for sid in duplicated:
        found.pop(sid, None)
    return found


def _pre_merge_status(
    subject_ids: list[str], entries: Mapping[str, Mapping[str, Any]]
) -> tuple[str, list[str]]:
    failed: list[str] = []
    missing: list[str] = []
    required_pass = False
    for sid in subject_ids:
        entry = entries.get(sid)
        if entry is None:
            missing.append(sid)
            continue
        category = entry.get("category")
        observed = entry.get("observed_status")
        if category == "COVERED" and observed == "FAIL":
            failed.append(sid)
        elif category == "COVERED" and observed == "PASS":
            if (
                entry.get("requirement_mode") == "REQUIRED"
                and entry.get("applicability") == "APPLICABLE"
            ):
                required_pass = True
        elif category == "CONDITIONALLY_NOT_APPLICABLE":
            # Neutral: it neither proves nor blocks the promise.
            continue
        else:
            missing.append(sid)
    if failed:
        return FAILED, [f"SUBJECT_FAILED:{sid}" for sid in failed]
    if missing:
        return NOT_COVERED, [f"SUBJECT_NOT_COVERED:{sid}" for sid in missing]
    if not required_pass:
        return NOT_COVERED, ["NO_REQUIRED_SUBJECT_PASSED"]
    return COVERED, []


def _overall(statuses: list[str]) -> str:
    if any(status in (FAILED, STALE) for status in statuses):
        return BLOCKED
    if statuses and all(status == COVERED for status in statuses):
        return COMPLETE
    return PARTIAL


def project_issue_promise_coverage(
    promise_block: Mapping[str, Any] | None,
    core_verdict: Mapping[str, Any] | None,
    expected_head: str,
    *,
    evidence_head: str | None,
    live_issue: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Per-promise coverage of one Issue at ``expected_head``.

    ``promise_block`` is the card's parsed ``nexus-issue-promises`` block,
    ``core_verdict`` the durable receipt verdict (None when nothing ran),
    ``evidence_head`` the commit that verdict was produced for, and
    ``live_issue`` the reader's current ``issue_contract_hash`` and
    ``promise_set_identity`` from the live Issue.
    """
    result: dict[str, Any] = {
        "schema": ISSUE_PROMISE_COVERAGE_SCHEMA,
        "claim_ceiling": CLAIM_CEILING,
        "expected_head": expected_head if isinstance(expected_head, str) else None,
        "evidence_head": evidence_head if isinstance(evidence_head, str) else None,
        "repository": None,
        "issue_number": None,
        "issue_contract_hash": None,
        "promise_set_generation": None,
        "promise_set_identity": None,
        "promises": [],
        "pending_external_witness": [],
        "reason_codes": [],
        "overall": BLOCKED,
    }
    if not isinstance(promise_block, Mapping):
        result["reason_codes"] = ["ISSUE_PROMISES_MISSING"]
        return result
    try:
        binding = IssuePromiseBinding.model_validate(dict(promise_block))
    except ValueError:
        result["reason_codes"] = ["ISSUE_PROMISES_INVALID"]
        return result
    result.update({
        "repository": binding.repository,
        "issue_number": binding.issue_number,
        "issue_contract_hash": binding.issue_contract_hash,
        "promise_set_generation": binding.promise_set.promise_set_generation,
        "promise_set_identity": binding.promise_set.identity,
    })
    if not isinstance(expected_head, str) or not _HEAD_RE.fullmatch(expected_head):
        result["reason_codes"] = ["EXPECTED_HEAD_INVALID"]
        return result
    verdict = core_verdict if isinstance(core_verdict, Mapping) else None
    stale = _stale_reasons(binding, verdict, expected_head, evidence_head, live_issue)
    untrusted = [] if stale else _untrusted_reasons(verdict)
    entries = _entries_by_subject(verdict) if verdict is not None and not untrusted else {}

    promises: list[dict[str, Any]] = []
    for promise in binding.promise_set.promises:
        subject_ids = binding.subject_ids_for(promise.promise_id)
        if stale:
            status, reasons = STALE, list(stale)
        elif untrusted:
            status, reasons = NOT_COVERED, list(untrusted)
        else:
            status, reasons = _pre_merge_status(subject_ids, entries)
            needs_witness = (
                promise.phase is IssuePromisePhase.POST_MERGE
                or promise.risk is IssuePromiseRisk.HIGH
            )
            if needs_witness and status != FAILED:
                # POST_MERGE: tests are never enough. HIGH: pre-merge evidence
                # must hold first, then a live witness is still required.
                if promise.phase is IssuePromisePhase.POST_MERGE or status == COVERED:
                    status = PENDING_EXTERNAL_WITNESS
                    reasons = [*reasons, "LIVE_WITNESS_REQUIRED"]
        promises.append({
            "promise_id": promise.promise_id,
            "phase": promise.phase.value,
            "risk": promise.risk.value,
            "subject_ids": subject_ids,
            "status": status,
            "reason_codes": reasons,
        })
    statuses = [item["status"] for item in promises]
    result["promises"] = promises
    result["pending_external_witness"] = [
        item["promise_id"] for item in promises if item["status"] == PENDING_EXTERNAL_WITNESS
    ]
    result["reason_codes"] = sorted({code for item in promises for code in item["reason_codes"]})
    result["overall"] = _overall(statuses)
    return result
