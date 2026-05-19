"""Build a source-neutral skill candidate pool for capability-skill ablation."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


RUNTIME_ELIGIBLE_STATUSES = {"nexus_curated_candidate"}
ABLATION_ELIGIBLE_STATUSES = {
    "agents_pool_review_needed",
    "external_reference_candidate",
    "nexus_curated_candidate",
    "provider_mirror_reference",
}
QUARANTINE_STATUSES = {
    "archive_quarantine",
    "candidate_quarantine",
    "runtime_vendor_readonly",
    "worktree_copy_quarantine",
}


@dataclass(frozen=True)
class FairSkillCandidate:
    skill_id: str
    source_root: str
    source_type: str
    path: str
    sha256: str
    capability_candidates: tuple[str, ...]
    load_when: str
    forbidden_when: tuple[str, ...]
    metadata_quality: str
    safety_status: str
    ablation_eligible: bool
    runtime_eligible: bool
    quarantine_reason: str
    evidence_refs: tuple[str, ...]
    shadow_policy: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "source_root": self.source_root,
            "source_type": self.source_type,
            "path": self.path,
            "sha256": self.sha256,
            "capability_candidates": list(self.capability_candidates),
            "load_when": self.load_when,
            "forbidden_when": list(self.forbidden_when),
            "metadata_quality": self.metadata_quality,
            "safety_status": self.safety_status,
            "ablation_eligible": self.ablation_eligible,
            "runtime_eligible": self.runtime_eligible,
            "quarantine_reason": self.quarantine_reason,
            "evidence_refs": list(self.evidence_refs),
            "shadow_policy": dict(self.shadow_policy),
        }


def _capability_candidates(row: Mapping[str, Any]) -> tuple[str, ...]:
    raw = str(row.get("capability_mount") or "").strip()
    if raw.startswith("reference:"):
        raw = raw.removeprefix("reference:")
    if not raw:
        return ()
    return (raw,)


def _source_type(root: str, status: str) -> str:
    if root == "nexus_repo":
        return "nexus_local"
    if status in {"external_reference_candidate", "provider_mirror_reference"}:
        return "reference"
    if status == "agents_pool_review_needed":
        return "local_candidate"
    if status in QUARANTINE_STATUSES:
        return "quarantine"
    return "unknown"


def _metadata_quality(row: Mapping[str, Any]) -> str:
    missing = [
        name
        for name in ("name", "path", "description", "capability_mount", "sha256")
        if not str(row.get(name) or "").strip()
    ]
    return "PASS" if not missing else f"INCOMPLETE:{','.join(missing)}"


def _safety_status(row: Mapping[str, Any]) -> str:
    status = str(row.get("skill_status") or "")
    if status in RUNTIME_ELIGIBLE_STATUSES:
        return "runtime_reviewed"
    if status in ABLATION_ELIGIBLE_STATUSES:
        return "ablation_only"
    if status in QUARANTINE_STATUSES:
        return "quarantined"
    return "unknown_status"


def _forbidden_when(row: Mapping[str, Any]) -> tuple[str, ...]:
    status = str(row.get("skill_status") or "")
    reasons = tuple(str(item) for item in (row.get("reason_codes") or ()) if str(item).strip())
    if status in QUARANTINE_STATUSES:
        return ("runtime_mount", "ablation_arm", *reasons)
    if status not in RUNTIME_ELIGIBLE_STATUSES:
        return ("runtime_mount", *reasons)
    return reasons


def _shadow_policy(row: Mapping[str, Any], by_name: Mapping[str, list[Mapping[str, Any]]]) -> dict[str, Any]:
    name = str(row.get("name") or row.get("dir_name") or "")
    siblings = by_name.get(name, [])
    if len(siblings) <= 1:
        return {"duplicate_count": 1, "shadowed": False, "canonical_path": str(row.get("path") or "")}
    runtime = [item for item in siblings if item.get("skill_status") in RUNTIME_ELIGIBLE_STATUSES]
    canonical = sorted(runtime or siblings, key=lambda item: str(item.get("path") or ""))[0]
    canonical_path = str(canonical.get("path") or "")
    current_path = str(row.get("path") or "")
    return {
        "duplicate_count": len(siblings),
        "shadowed": current_path != canonical_path,
        "canonical_path": canonical_path,
        "duplicate_paths": sorted(str(item.get("path") or "") for item in siblings),
    }


def _quarantine_reason(row: Mapping[str, Any], *, metadata_quality: str) -> str:
    status = str(row.get("skill_status") or "")
    if status in QUARANTINE_STATUSES:
        return f"status:{status}"
    if metadata_quality != "PASS":
        return f"metadata:{metadata_quality}"
    return ""


def build_fair_skill_candidate_pool(status_report: Mapping[str, Any]) -> dict[str, Any]:
    rows = [row for row in status_report.get("skills", []) if isinstance(row, Mapping)]
    by_name: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_name[str(row.get("name") or row.get("dir_name") or "")].append(row)

    candidates: list[FairSkillCandidate] = []
    violations: list[str] = []
    for row in rows:
        status = str(row.get("skill_status") or "")
        root = str(row.get("root") or "")
        metadata_quality = _metadata_quality(row)
        quarantine_reason = _quarantine_reason(row, metadata_quality=metadata_quality)
        runtime_eligible = bool(status in RUNTIME_ELIGIBLE_STATUSES and metadata_quality == "PASS")
        ablation_eligible = bool(status in ABLATION_ELIGIBLE_STATUSES and metadata_quality == "PASS")
        if runtime_eligible and root != "nexus_repo":
            violations.append(f"{row.get('name')}:runtime_eligible_unknown_or_external_root:{root}")
            runtime_eligible = False
        if status in QUARANTINE_STATUSES and runtime_eligible:
            violations.append(f"{row.get('name')}:quarantined_runtime_eligible:{status}")
            runtime_eligible = False
        shadow_policy = _shadow_policy(row, by_name)
        if len(by_name[str(row.get("name") or row.get("dir_name") or "")]) > 1 and not shadow_policy.get("canonical_path"):
            violations.append(f"{row.get('name')}:duplicate_without_canonical")
        candidates.append(
            FairSkillCandidate(
                skill_id=str(row.get("name") or row.get("dir_name") or ""),
                source_root=root,
                source_type=_source_type(root, status),
                path=str(row.get("path") or ""),
                sha256=str(row.get("sha256") or ""),
                capability_candidates=_capability_candidates(row),
                load_when=str(row.get("description") or ""),
                forbidden_when=_forbidden_when(row),
                metadata_quality=metadata_quality,
                safety_status=_safety_status(row),
                ablation_eligible=ablation_eligible,
                runtime_eligible=runtime_eligible,
                quarantine_reason=quarantine_reason,
                evidence_refs=(
                    f"skill_status_report:{status_report.get('schema', 'unknown')}",
                    f"skill_path:{row.get('path') or ''}",
                    f"skill_sha256:{row.get('sha256') or ''}",
                ),
                shadow_policy=shadow_policy,
            )
        )

    status_counts = Counter(candidate.safety_status for candidate in candidates)
    source_counts = Counter(candidate.source_root for candidate in candidates)
    capability_counts = Counter(
        capability
        for candidate in candidates
        if candidate.ablation_eligible
        for capability in candidate.capability_candidates
    )
    return {
        "schema": "nexus.fair_skill_candidate_pool.v1",
        "status": "PASS" if not violations else "RETURN",
        "source_status_report_schema": status_report.get("schema", ""),
        "summary": {
            "total_candidates": len(candidates),
            "ablation_eligible_count": sum(1 for candidate in candidates if candidate.ablation_eligible),
            "runtime_eligible_count": sum(1 for candidate in candidates if candidate.runtime_eligible),
            "quarantine_count": sum(1 for candidate in candidates if candidate.safety_status == "quarantined"),
            "source_root_counts": dict(sorted(source_counts.items())),
            "safety_status_counts": dict(sorted(status_counts.items())),
            "ablation_capability_counts": dict(sorted(capability_counts.items())),
        },
        "violations": sorted(set(violations)),
        "claim_boundary": [
            "Ablation eligibility means a skill can be tested in a controlled arm; it does not allow runtime auto-mounting.",
            "Runtime eligibility remains limited to reviewed Nexus-local curated candidates.",
            "Source roots do not provide scoring weight; winner decisions must come from receipt-backed ablation evidence.",
        ],
        "candidates": [candidate.to_dict() for candidate in candidates],
    }


def build_fair_skill_candidate_pool_from_file(path: str | Path) -> dict[str, Any]:
    return build_fair_skill_candidate_pool(json.loads(Path(path).read_text(encoding="utf-8")))


def write_fair_skill_candidate_pool(*, status_report_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    pool = build_fair_skill_candidate_pool_from_file(status_report_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(pool, indent=2, ensure_ascii=False), encoding="utf-8")
    return pool
