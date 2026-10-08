"""Repository Intelligence knowledge-applicability adapter for ``codeintel`` (#1579).

G1 producer adapter + G2 bounded projection.

* The RIE engine is invoked ONLY as a subprocess (``python -m
  repository_intelligence.cli --operation knowledge --input -``). The engine is
  never imported into ``nexus/`` (canonical_owner_guard).
* The engine checkout must be exactly ``PINNED_RIE_ENGINE_REVISION``.
* The report is verified (schema, content hash, claim ceiling, exact revision
  identity) before any projection. Failures are fail-closed.
* No model call. No route/model/approval/merge/release/policy authority.
* Missing knowledge claims => explicit ``NOT_APPLICABLE`` evidence; ``CURRENT``
  is only ever reported when the verified engine report says so for a
  declared relation.
* The projection is a bounded, fixed-schema view; no document or source text.

This module adds no Planner capability. It produces fields that ride the
existing ``codeintel`` evidence path (``capability_evidence_bundle``
``consumer_payload``) once CapabilityPlanner has selected ``codeintel``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

PINNED_RIE_ENGINE_REVISION = "88285acf570688befbc8e36eb73f46987171bd4e"
RIE_KNOWLEDGE_REPORT_SCHEMA = "reviewer.knowledge_applicability.v1"
RIE_KNOWLEDGE_CLAIM_CEILING = "REPOSITORY_KNOWLEDGE_APPLICABILITY_EVIDENCE_ONLY"
PLANNER_SELECTED_CODEINTEL_CLAIM_CEILING = (
    "PLANNER_SELECTED_CODEINTEL_KNOWLEDGE_APPLICABILITY_CONTEXT_ONLY"
)
PROJECTION_SCHEMA = "nexus.codeintel_knowledge_applicability.v1"

ENV_ENGINE_ROOT = "NEXUS_RIE_ENGINE_ROOT"
ENV_PYTHON_BIN = "NEXUS_RIE_PYTHON_BIN"
DEFAULT_PYTHON_BIN = "python3"
ENGINE_TIMEOUT_SECONDS = 30

STATUSES = ("CURRENT", "STALE_EXACT_SOURCE", "AFFECTED_BY_COVERAGE", "UNKNOWN")
_REVIEW_NEEDED_ORDER = ("STALE_EXACT_SOURCE", "AFFECTED_BY_COVERAGE", "UNKNOWN")

MAX_REFS = 4
MAX_REF_CHARS = 90
MAX_GAPS = 4
MAX_GAP_CHARS = 80

SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
_IDENTITY_KEYS = ("repository", "pr_number", "head_sha", "base_sha", "current_main_sha")

Runner = Callable[..., Any]


class RieKnowledgeApplicabilityError(ValueError):
    """Fail-closed adapter error carrying a stable machine code."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code = code


def canonical_hash(value: Mapping[str, Any]) -> str:
    """Hash identical to the RIE report content hash (``ensure_ascii`` JSON)."""
    return hashlib.sha256(
        json.dumps(
            dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
    ).hexdigest()


def _bound(text: Any, limit: int) -> str:
    value = str(text if text is not None else "")
    return value if len(value) <= limit else value[: limit - 3] + "..."


# --------------------------------------------------------------------------- #
# G1: engine invocation
# --------------------------------------------------------------------------- #
def resolve_engine_config(env: Mapping[str, str] | None = None) -> tuple[Path, str]:
    source = os.environ if env is None else env
    root = str(source.get(ENV_ENGINE_ROOT) or "").strip()
    if not root:
        raise RieKnowledgeApplicabilityError("RIE_ENGINE_ROOT_NOT_CONFIGURED")
    python_bin = str(source.get(ENV_PYTHON_BIN) or "").strip() or DEFAULT_PYTHON_BIN
    return Path(root), python_bin


def verify_engine_revision(root: Path, *, runner: Runner = subprocess.run) -> str:
    """Require the engine checkout HEAD to equal the pinned revision."""
    try:
        proc = runner(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=ENGINE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RieKnowledgeApplicabilityError(
            "RIE_ENGINE_REVISION_UNREADABLE", type(exc).__name__
        ) from exc
    head = str(getattr(proc, "stdout", "") or "").strip().lower()
    if getattr(proc, "returncode", 1) != 0 or not SHA40.fullmatch(head):
        raise RieKnowledgeApplicabilityError("RIE_ENGINE_REVISION_UNREADABLE")
    if head != PINNED_RIE_ENGINE_REVISION:
        raise RieKnowledgeApplicabilityError("RIE_ENGINE_REVISION_MISMATCH", head)
    return head


def run_knowledge_operation(
    evidence: Mapping[str, Any],
    *,
    env: Mapping[str, str] | None = None,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    """Run the pinned engine ``knowledge`` operation; return the raw report dict."""
    root, python_bin = resolve_engine_config(env)
    verify_engine_revision(root, runner=runner)
    child_env = {
        k: v
        for k, v in (os.environ if env is None else env).items()
        if k in {"PATH", "HOME", "LANG", "LC_ALL", "SYSTEMROOT"}
    }
    child_env["PYTHONPATH"] = str(root)
    child_env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        stdin = json.dumps(dict(evidence), ensure_ascii=True, allow_nan=False)
        proc = runner(
            [python_bin, "-m", "repository_intelligence.cli",
             "--operation", "knowledge", "--input", "-"],
            input=stdin,
            capture_output=True,
            text=True,
            cwd=str(root),
            env=child_env,
            timeout=ENGINE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, TypeError, ValueError) as exc:
        raise RieKnowledgeApplicabilityError(
            "RIE_ENGINE_INVOCATION_FAILED", type(exc).__name__
        ) from exc
    if getattr(proc, "returncode", 1) != 0:
        raise RieKnowledgeApplicabilityError("RIE_ENGINE_NONZERO_EXIT")
    try:
        envelope = json.loads(proc.stdout)
    except (TypeError, ValueError) as exc:
        raise RieKnowledgeApplicabilityError("RIE_ENGINE_OUTPUT_MALFORMED") from exc
    if (
        not isinstance(envelope, Mapping)
        or envelope.get("operation") != "knowledge"
        or not isinstance(envelope.get("result"), Mapping)
    ):
        raise RieKnowledgeApplicabilityError("RIE_ENGINE_OUTPUT_MALFORMED")
    if envelope.get("claim_ceiling") != RIE_KNOWLEDGE_CLAIM_CEILING:
        raise RieKnowledgeApplicabilityError("RIE_CLAIM_CEILING_MISMATCH")
    return dict(envelope["result"])


def verify_knowledge_report(
    report: Mapping[str, Any], *, expected_identity: Mapping[str, Any]
) -> None:
    """Verify schema, claim ceiling, content hash and exact revision identity."""
    if not isinstance(report, Mapping):
        raise RieKnowledgeApplicabilityError("RIE_REPORT_NOT_MAPPING")
    if report.get("schema") != RIE_KNOWLEDGE_REPORT_SCHEMA:
        raise RieKnowledgeApplicabilityError("RIE_REPORT_SCHEMA_MISMATCH")
    if report.get("claim_ceiling") != RIE_KNOWLEDGE_CLAIM_CEILING:
        raise RieKnowledgeApplicabilityError("RIE_CLAIM_CEILING_MISMATCH")
    supplied = str(report.get("content_sha256") or "")
    if not SHA64.fullmatch(supplied):
        raise RieKnowledgeApplicabilityError("RIE_REPORT_CONTENT_SHA256_INVALID")
    material = {k: v for k, v in report.items() if k != "content_sha256"}
    if canonical_hash(material) != supplied:
        raise RieKnowledgeApplicabilityError("RIE_REPORT_CONTENT_SHA256_MISMATCH")
    identity = report.get("identity")
    if not isinstance(identity, Mapping):
        raise RieKnowledgeApplicabilityError("RIE_REPORT_IDENTITY_MISSING")
    if identity.get("is_valid") is not True or identity.get("stale_evidence") is not False:
        raise RieKnowledgeApplicabilityError("RIE_REPORT_IDENTITY_STALE_OR_INVALID")
    for key in _IDENTITY_KEYS:
        if identity.get(key) != expected_identity.get(key) or not expected_identity.get(key):
            raise RieKnowledgeApplicabilityError("RIE_REPORT_IDENTITY_MISMATCH", key)


# --------------------------------------------------------------------------- #
# G2: bounded projection
# --------------------------------------------------------------------------- #
def _empty_counts() -> dict[str, int]:
    return {status: 0 for status in STATUSES}


def not_applicable_projection(gaps: Sequence[str]) -> dict[str, Any]:
    """Explicit not-applicable evidence. Never reports CURRENT."""
    return {
        "schema": PROJECTION_SCHEMA,
        "status": "NOT_APPLICABLE",
        "relation_counts": _empty_counts(),
        "affected_artifact_refs": [],
        "uncovered_change_refs": [],
        "evidence_gaps": [_bound(g, MAX_GAP_CHARS) for g in list(gaps)[:MAX_GAPS]],
        "report_hash": "",
        "report_schema": RIE_KNOWLEDGE_REPORT_SCHEMA,
        "rie_claim_ceiling": RIE_KNOWLEDGE_CLAIM_CEILING,
        "claim_ceiling": PLANNER_SELECTED_CODEINTEL_CLAIM_CEILING,
    }


def project_knowledge_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Project a VERIFIED report into the bounded codeintel view.

    Only counts, artifact paths, change paths, gap codes and hashes are
    forwarded; reason codes, artifact text and source text never are.
    """
    counts = _empty_counts()
    review: list[tuple[int, str]] = []
    for rel in report.get("relations") or []:
        if not isinstance(rel, Mapping):
            continue
        status = rel.get("status")
        if status not in counts:
            status = "UNKNOWN"
        counts[status] += 1
        if status in _REVIEW_NEEDED_ORDER:
            review.append(
                (_REVIEW_NEEDED_ORDER.index(status),
                 f"{status}:{_bound(rel.get('artifact_path'), MAX_REF_CHARS - 24)}")
            )
    review.sort()
    refs = [_bound(text, MAX_REF_CHARS) for _, text in review[:MAX_REFS]]
    uncovered = [
        _bound(p, MAX_REF_CHARS) for p in list(report.get("uncovered_changes") or [])[:MAX_REFS]
    ]
    gaps = [_bound(g, MAX_GAP_CHARS) for g in list(report.get("evidence_gaps") or [])[:MAX_GAPS]]
    total = sum(counts.values())
    if total == 0:
        status = "NOT_APPLICABLE"
        gaps = (gaps or ["NO_KNOWLEDGE_RELATIONS"])[:MAX_GAPS]
    elif report.get("is_complete") is True:
        status = "COMPLETE"
    else:
        status = "INCOMPLETE"
    return {
        "schema": PROJECTION_SCHEMA,
        "status": status,
        "relation_counts": counts,
        "affected_artifact_refs": refs,
        "uncovered_change_refs": uncovered,
        "evidence_gaps": gaps,
        "report_hash": str(report.get("content_sha256") or ""),
        "report_schema": RIE_KNOWLEDGE_REPORT_SCHEMA,
        "rie_claim_ceiling": RIE_KNOWLEDGE_CLAIM_CEILING,
        "claim_ceiling": PLANNER_SELECTED_CODEINTEL_CLAIM_CEILING,
    }


def build_codeintel_knowledge_evidence(
    *,
    snapshot: Mapping[str, Any] | None,
    knowledge_artifacts: Sequence[Mapping[str, Any]] | None,
    changes: Sequence[Mapping[str, Any]] | None = None,
    observed_source_sha256: Mapping[str, str] | None = None,
    in_scope: Sequence[str] | None = None,
    collection_complete: bool = False,
    collection_errors: Sequence[str] = (),
    env: Mapping[str, str] | None = None,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    """Produce the ``evidence`` fragment for a Planner-selected codeintel stage.

    Returns ``{"knowledge_applicability": <bounded projection>}``, suitable to
    merge into the codeintel stage ``evidence`` consumed by
    ``extract_bounded_consumer_payload``.

    Missing claim inputs (no snapshot identity or no declared knowledge
    artifacts) short-circuit to explicit NOT_APPLICABLE evidence without
    invoking the engine. Engine/report integrity failures raise
    ``RieKnowledgeApplicabilityError`` (fail closed).
    """
    identity = dict(snapshot or {})
    if not all(identity.get(k) for k in _IDENTITY_KEYS):
        return {"knowledge_applicability": not_applicable_projection(
            ["REVISION_IDENTITY_UNAVAILABLE"])}
    if not knowledge_artifacts:
        return {"knowledge_applicability": not_applicable_projection(
            ["KNOWLEDGE_CLAIM_SOURCE_NOT_AVAILABLE", *collection_errors])}
    evidence = {
        "snapshot": identity,
        "knowledge_artifacts": [dict(a) for a in knowledge_artifacts],
        "changes": [dict(c) for c in (changes or [])],
        "observed_source_sha256": dict(observed_source_sha256 or {}),
        "in_scope": list(in_scope or []),
        "collection_complete": collection_complete is True,
        "collection_errors": list(collection_errors),
    }
    report = run_knowledge_operation(evidence, env=env, runner=runner)
    verify_knowledge_report(report, expected_identity=identity)
    return {"knowledge_applicability": project_knowledge_report(report)}
