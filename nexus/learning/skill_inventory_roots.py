"""Full skill-root inventory and duplicate cleanup planning for SF."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from nexus.learning.skill_route_taxonomy import ROUTE_CAPABILITIES, classify_skill_for_route_capabilities


DEFAULT_SKILL_ROOTS: tuple[str, ...] = (
    "/Users/jameschen/.agents/skills",
    "/Users/jameschen/.agents/skills.archived-20260426-context-budget",
    "/Users/jameschen/.codex/skills",
    "/Users/jameschen/.gemini/skills_OLD",
    "/Users/jameschen/Workspace/nexus/.agents/skills",
    "/Users/jameschen/Workspace/nexus/skills",
    "/Users/jameschen/Workspace/hermes-agent/skills",
    "/Users/jameschen/Workspace/skills_audit/skills",
)


SOURCE_PRIORITY: dict[str, int] = {
    "nexus_repo_local": 100,
    "nexus_workspace_skills": 90,
    "agents_primary": 70,
    "hermes_reference": 60,
    "audit_reference": 55,
    "codex_mirror_cache": 20,
    "archived_reference": 10,
    "legacy_old": 5,
    "unknown": 0,
}

CANONICAL_SOURCE_STATUSES = {
    "nexus_repo_local",
    "nexus_workspace_skills",
    "agents_primary",
    "hermes_reference",
    "audit_reference",
}


@dataclass(frozen=True)
class SkillRootRecord:
    identity_id: str
    skill_id: str
    root: str
    relative_dir: str
    skill_path: str
    sha256: str
    source_status: str
    source_priority: int
    ablation_eligible: bool
    runtime_eligible: bool
    title: str
    description: str

    def to_candidate(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "path": self.skill_path,
            "source_root": self.source_status,
            "source_type": self.source_status,
            "safety_status": "runtime_reviewed" if self.runtime_eligible else "ablation_only"
            if self.ablation_eligible
            else "quarantined",
            "ablation_eligible": self.ablation_eligible,
            "runtime_eligible": self.runtime_eligible,
            "capability_candidates": [],
            "load_when": self.description,
            "description": self.description,
            "name": self.title or self.skill_id,
            "sha256": self.sha256,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity_id": self.identity_id,
            "skill_id": self.skill_id,
            "root": self.root,
            "relative_dir": self.relative_dir,
            "skill_path": self.skill_path,
            "sha256": self.sha256,
            "source_status": self.source_status,
            "source_priority": self.source_priority,
            "ablation_eligible": self.ablation_eligible,
            "runtime_eligible": self.runtime_eligible,
            "title": self.title,
            "description": self.description,
        }


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-").lower()
    return normalized or "unknown-skill"


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    block = text[3:end]
    values: dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip().lower()] = value.strip().strip("\"'")
    return values


def _source_status(root: Path) -> str:
    root_text = str(root)
    if root_text.endswith("/Workspace/nexus/.agents/skills"):
        return "nexus_repo_local"
    if root_text.endswith("/Workspace/nexus/skills"):
        return "nexus_workspace_skills"
    if root_text.endswith("/.agents/skills"):
        return "agents_primary"
    if "hermes-agent/skills" in root_text:
        return "hermes_reference"
    if "skills_audit/skills" in root_text:
        return "audit_reference"
    if "/.codex/skills" in root_text:
        return "codex_mirror_cache"
    if "archived" in root_text:
        return "archived_reference"
    if "skills_OLD" in root_text:
        return "legacy_old"
    return "unknown"


def _identity_id(root: Path, skill_path: Path, skill_id: str, digest: str) -> str:
    relative_dir = str(skill_path.parent.relative_to(root))
    raw = f"{root}|{relative_dir}|{skill_id}|{digest}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _record_from_path(root: Path, skill_path: Path) -> SkillRootRecord:
    text = _read_text(skill_path)
    frontmatter = _frontmatter(text)
    title = str(frontmatter.get("name") or "").strip()
    skill_id = _slug(title or skill_path.parent.name)
    description = str(frontmatter.get("description") or "").strip()
    digest = _sha256(text)
    source_status = _source_status(root)
    priority = SOURCE_PRIORITY.get(source_status, 0)
    ablation_eligible = source_status in CANONICAL_SOURCE_STATUSES
    runtime_eligible = source_status == "nexus_repo_local" and "sf2" not in skill_path.relative_to(root).parts
    return SkillRootRecord(
        identity_id=_identity_id(root, skill_path, skill_id, digest),
        skill_id=skill_id,
        root=str(root),
        relative_dir=str(skill_path.parent.relative_to(root)),
        skill_path=str(skill_path),
        sha256=digest,
        source_status=source_status,
        source_priority=priority,
        ablation_eligible=ablation_eligible,
        runtime_eligible=runtime_eligible,
        title=title,
        description=description,
    )


def discover_skill_records(roots: Sequence[str | Path] = DEFAULT_SKILL_ROOTS) -> list[SkillRootRecord]:
    records: list[SkillRootRecord] = []
    for raw_root in roots:
        root = Path(raw_root).expanduser()
        if not root.exists():
            continue
        for skill_path in sorted(root.rglob("SKILL.md")):
            if not skill_path.is_file():
                continue
            if any(part in {".duplicates-quarantine", ".nexus-sf-index"} for part in skill_path.parts):
                continue
            records.append(_record_from_path(root, skill_path))
    return records


def build_full_skill_inventory(roots: Sequence[str | Path] = DEFAULT_SKILL_ROOTS) -> dict[str, Any]:
    records = discover_skill_records(roots)
    source_counts = Counter(record.source_status for record in records)
    root_counts = Counter(record.root for record in records)
    skill_id_counts = Counter(record.skill_id for record in records)
    duplicate_skill_ids = sorted(skill_id for skill_id, count in skill_id_counts.items() if count > 1)
    return {
        "schema": "nexus.sf_full_skill_inventory.v1",
        "status": "PASS",
        "summary": {
            "root_count": len(tuple(roots)),
            "existing_root_count": len(root_counts),
            "skill_file_count": len(records),
            "unique_skill_id_count": len(skill_id_counts),
            "duplicate_skill_id_count": len(duplicate_skill_ids),
            "source_status_counts": dict(sorted(source_counts.items())),
            "root_counts": dict(sorted(root_counts.items())),
        },
        "source_priority": dict(sorted(SOURCE_PRIORITY.items(), key=lambda item: -item[1])),
        "duplicate_skill_ids": duplicate_skill_ids[:500],
        "skills": [record.to_dict() for record in records],
    }


def _canonical_for_group(records: Iterable[Mapping[str, Any]]) -> Mapping[str, Any]:
    return sorted(
        records,
        key=lambda item: (
            -int(item.get("source_priority") or 0),
            str(item.get("skill_path") or ""),
        ),
    )[0]


def build_identity_dedup_report(inventory: Mapping[str, Any]) -> dict[str, Any]:
    records = [item for item in inventory.get("skills", []) or [] if isinstance(item, Mapping)]
    by_skill_id: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    by_sha: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        by_skill_id[str(record.get("skill_id") or "")].append(record)
        by_sha[str(record.get("sha256") or "")].append(record)

    duplicate_groups = []
    safe_delete_candidates = []
    manual_review_required = []
    safe_ignore = []
    for skill_id, items in sorted(by_skill_id.items()):
        if len(items) <= 1:
            continue
        canonical = _canonical_for_group(items)
        sha_groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for item in items:
            sha_groups[str(item.get("sha256") or "")].append(item)
        same_id_different_content = len(sha_groups) > 1
        duplicate_groups.append(
            {
                "skill_id": skill_id,
                "record_count": len(items),
                "content_variant_count": len(sha_groups),
                "canonical_identity_id": canonical.get("identity_id", ""),
                "canonical_path": canonical.get("skill_path", ""),
                "source_statuses": sorted({str(item.get("source_status") or "") for item in items}),
            }
        )
        if same_id_different_content:
            manual_review_required.append(
                {
                    "skill_id": skill_id,
                    "reason": "same_skill_id_different_content",
                    "canonical_path": canonical.get("skill_path", ""),
                    "variant_count": len(sha_groups),
                    "paths": sorted(str(item.get("skill_path") or "") for item in items),
                }
            )
        for sha_items in sha_groups.values():
            if len(sha_items) <= 1:
                continue
            sha_canonical = _canonical_for_group(sha_items)
            for item in sha_items:
                if item.get("identity_id") == sha_canonical.get("identity_id"):
                    continue
                if int(item.get("source_priority") or 0) < int(sha_canonical.get("source_priority") or 0):
                    safe_delete_candidates.append(
                        {
                            "skill_id": skill_id,
                            "identity_id": item.get("identity_id", ""),
                            "path": item.get("skill_path", ""),
                            "reason": "byte_identical_lower_priority_duplicate",
                            "canonical_path": sha_canonical.get("skill_path", ""),
                            "source_status": item.get("source_status", ""),
                        }
                    )
                elif str(item.get("source_status") or "") in {"codex_mirror_cache", "archived_reference", "legacy_old"}:
                    safe_ignore.append(
                        {
                            "skill_id": skill_id,
                            "identity_id": item.get("identity_id", ""),
                            "path": item.get("skill_path", ""),
                            "reason": "noncanonical_source_with_duplicate_skill_id",
                            "canonical_path": sha_canonical.get("skill_path", ""),
                        }
                    )

    sha_duplicate_groups = sum(1 for items in by_sha.values() if len(items) > 1)
    return {
        "schema": "nexus.sf_skill_identity_dedup.v1",
        "status": "PASS",
        "summary": {
            "skill_file_count": len(records),
            "duplicate_skill_id_group_count": len(duplicate_groups),
            "byte_identical_content_group_count": sha_duplicate_groups,
            "safe_delete_candidate_count": len(safe_delete_candidates),
            "safe_ignore_count": len(safe_ignore),
            "manual_review_required_count": len(manual_review_required),
        },
        "duplicate_groups": duplicate_groups,
        "safe_delete_candidates": safe_delete_candidates,
        "safe_ignore": safe_ignore,
        "manual_review_required": manual_review_required,
        "claim_boundary": [
            "safe_delete_candidates are byte-identical lower-priority duplicates only.",
            "same-id different-content records require review and must not be deleted automatically.",
        ],
    }


def build_canonical_capability_buckets(inventory: Mapping[str, Any], dedup_report: Mapping[str, Any]) -> dict[str, Any]:
    safe_ignore_paths = {str(item.get("path") or "") for item in dedup_report.get("safe_ignore", []) or []}
    safe_delete_paths = {str(item.get("path") or "") for item in dedup_report.get("safe_delete_candidates", []) or []}
    records = [
        item
        for item in inventory.get("skills", []) or []
        if isinstance(item, Mapping)
        and item.get("ablation_eligible")
        and str(item.get("skill_path") or "") not in safe_ignore_paths
        and str(item.get("skill_path") or "") not in safe_delete_paths
    ]
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in records:
        candidate = SkillRootRecord(
            identity_id=str(item.get("identity_id") or ""),
            skill_id=str(item.get("skill_id") or ""),
            root=str(item.get("root") or ""),
            relative_dir=str(item.get("relative_dir") or ""),
            skill_path=str(item.get("skill_path") or ""),
            sha256=str(item.get("sha256") or ""),
            source_status=str(item.get("source_status") or ""),
            source_priority=int(item.get("source_priority") or 0),
            ablation_eligible=bool(item.get("ablation_eligible")),
            runtime_eligible=bool(item.get("runtime_eligible")),
            title=str(item.get("title") or ""),
            description=str(item.get("description") or ""),
        ).to_candidate()
        for capability in classify_skill_for_route_capabilities(candidate):
            capability_id = str(capability.get("capability_id") or "")
            buckets[capability_id].append(
                {
                    "identity_id": item.get("identity_id", ""),
                    "skill_id": item.get("skill_id", ""),
                    "skill_path": item.get("skill_path", ""),
                    "sha256": item.get("sha256", ""),
                    "source_status": item.get("source_status", ""),
                    "source_priority": item.get("source_priority", 0),
                    "runtime_eligible": bool(item.get("runtime_eligible")),
                    "ablation_eligible": bool(item.get("ablation_eligible")),
                    "confidence": capability.get("confidence", ""),
                    "score": capability.get("score", 0),
                    "reasons": capability.get("reasons", []),
                }
            )
    capability_buckets = []
    missing_capabilities = []
    for capability in ROUTE_CAPABILITIES:
        capability_id = capability.capability_id
        items = buckets.get(capability_id, [])
        ranked = sorted(
            items,
            key=lambda item: (
                -int(item.get("score") or 0),
                -int(item.get("source_priority") or 0),
                str(item.get("skill_id") or ""),
                str(item.get("skill_path") or ""),
            ),
        )
        if not ranked:
            missing_capabilities.append(capability_id)
        capability_buckets.append(
            {
                "capability_id": capability_id,
                "group": capability.group,
                "pillar": capability.pillar,
                "candidate_count": len(ranked),
                "top_candidates": ranked[:12],
            }
        )
    return {
        "schema": "nexus.sf_canonical_capability_buckets.v1",
        "status": "PASS" if not missing_capabilities else "PARTIAL",
        "summary": {
            "canonical_skill_count": len(records),
            "capability_bucket_count": len(capability_buckets),
            "capabilities_with_candidates": len(capability_buckets) - len(missing_capabilities),
            "capabilities_without_candidates": len(missing_capabilities),
            "safe_delete_excluded_count": len(safe_delete_paths),
            "safe_ignore_excluded_count": len(safe_ignore_paths),
        },
        "missing_capabilities": missing_capabilities,
        "capability_buckets": capability_buckets,
    }


def _load_json_if_exists(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        return {}
    return json.loads(source.read_text(encoding="utf-8"))


def build_pairing_identity_recheck(
    *,
    patch_plan_path: str | Path,
    promotion_review_path: str | Path,
    inventory: Mapping[str, Any],
    dedup_report: Mapping[str, Any],
) -> dict[str, Any]:
    patch_plan = _load_json_if_exists(patch_plan_path)
    promotion_review = _load_json_if_exists(promotion_review_path)
    records = [item for item in inventory.get("skills", []) or [] if isinstance(item, Mapping)]
    records_by_path = {str(item.get("skill_path") or ""): item for item in records}
    records_by_id: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in records:
        records_by_id[str(item.get("skill_id") or "")].append(item)
    dedup_by_id = {str(item.get("skill_id") or ""): item for item in dedup_report.get("duplicate_groups", []) or []}

    promotion_items = {
        (str(item.get("capability_id") or ""), str(item.get("skill_id") or "")): item
        for item in promotion_review.get("review_items", []) or promotion_review.get("promotion_items", []) or []
        if isinstance(item, Mapping)
    }

    rechecks = []
    blockers = []
    warnings = []
    for change in patch_plan.get("planned_changes", []) or patch_plan.get("changes", []) or []:
        if not isinstance(change, Mapping):
            continue
        capability_id = str(change.get("capability_id") or "")
        skill_id = str(change.get("skill_id") or "")
        promotion_item = promotion_items.get((capability_id, skill_id), {})
        skill_path = str(change.get("skill_path") or promotion_item.get("skill_path") or promotion_item.get("path") or "")
        record = records_by_path.get(skill_path)
        duplicate_group = dedup_by_id.get(skill_id, {})
        status = "PASS"
        reasons: list[str] = []
        if not record:
            status = "BLOCKED"
            reasons.append("skill_path_not_found_in_full_roots_inventory")
            blockers.append(f"{capability_id}:{skill_id}:path_not_found")
        else:
            source_status = str(record.get("source_status") or "")
            planned_action = str(change.get("planned_action") or change.get("decision") or "")
            if "runtime" in planned_action.lower() and source_status != "nexus_repo_local":
                status = "BLOCKED"
                reasons.append(f"runtime_review_requires_nexus_repo_local:{source_status}")
                blockers.append(f"{capability_id}:{skill_id}:noncanonical_runtime_source")
            if duplicate_group:
                warnings.append(f"{capability_id}:{skill_id}:duplicate_skill_id_requires_path_identity")
                reasons.append("duplicate_skill_id_disambiguated_by_path_and_sha256")
        rechecks.append(
            {
                "capability_id": capability_id,
                "skill_id": skill_id,
                "status": status,
                "reasons": reasons,
                "planned_action": change.get("planned_action") or change.get("decision") or "",
                "skill_path": skill_path,
                "identity_id": record.get("identity_id", "") if record else "",
                "sha256": record.get("sha256", "") if record else "",
                "source_status": record.get("source_status", "") if record else "",
                "duplicate_skill_id_record_count": len(records_by_id.get(skill_id, [])),
            }
        )

    return {
        "schema": "nexus.sf_pairing_identity_recheck.v1",
        "status": "PASS" if not blockers else "BLOCKED",
        "summary": {
            "pairing_count": len(rechecks),
            "pass_count": sum(1 for item in rechecks if item["status"] == "PASS"),
            "blocker_count": len(blockers),
            "warning_count": len(set(warnings)),
        },
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "pairings": rechecks,
        "claim_boundary": [
            "Pairings are rechecked by path and sha256 identity, never skill_id alone.",
            "A PASS here means the pairing is source-clean enough for SF evidence review, not public benchmark unlock.",
        ],
    }


def build_cleanup_apply_plan(
    *,
    inventory: Mapping[str, Any],
    dedup_report: Mapping[str, Any],
    quarantine_root: str | Path,
) -> dict[str, Any]:
    records_by_path = {
        str(item.get("skill_path") or ""): item
        for item in inventory.get("skills", []) or []
        if isinstance(item, Mapping)
    }
    quarantine_base = Path(quarantine_root)
    items = []
    blockers = []
    for candidate in dedup_report.get("safe_delete_candidates", []) or []:
        if not isinstance(candidate, Mapping):
            continue
        skill_path = str(candidate.get("path") or "")
        record = records_by_path.get(skill_path)
        if not record:
            blockers.append(f"{skill_path}:missing_inventory_record")
            continue
        source_dir = str(Path(skill_path).parent)
        identity_id = str(record.get("identity_id") or "")
        source_status = str(record.get("source_status") or "unknown")
        relative_dir = Path(str(record.get("relative_dir") or Path(source_dir).name))
        destination_dir = quarantine_base / source_status / identity_id / relative_dir
        items.append(
            {
                "skill_id": candidate.get("skill_id", ""),
                "identity_id": identity_id,
                "source_status": source_status,
                "source_dir": source_dir,
                "source_skill_path": skill_path,
                "destination_dir": str(destination_dir),
                "reason": candidate.get("reason", ""),
                "canonical_path": candidate.get("canonical_path", ""),
            }
        )
    return {
        "schema": "nexus.sf_skill_cleanup_apply_plan.v1",
        "status": "PASS" if not blockers else "BLOCKED",
        "summary": {
            "planned_quarantine_count": len(items),
            "blocker_count": len(blockers),
            "quarantine_root": str(quarantine_base),
            "destructive_delete_allowed": False,
        },
        "blockers": sorted(blockers),
        "items": items,
        "claim_boundary": [
            "The apply plan moves byte-identical lower-priority duplicates to quarantine; it does not permanently delete files.",
            "Same-id different-content records are excluded and require manual review.",
        ],
    }


def apply_cleanup_plan(plan: Mapping[str, Any], *, mode: str = "dry-run") -> dict[str, Any]:
    if mode not in {"dry-run", "quarantine"}:
        raise ValueError(f"unsupported cleanup mode: {mode}")
    results = []
    blockers = []
    for item in plan.get("items", []) or []:
        if not isinstance(item, Mapping):
            continue
        source_dir = Path(str(item.get("source_dir") or ""))
        destination_dir = Path(str(item.get("destination_dir") or ""))
        result = {
            "skill_id": item.get("skill_id", ""),
            "identity_id": item.get("identity_id", ""),
            "source_dir": str(source_dir),
            "destination_dir": str(destination_dir),
            "mode": mode,
        }
        if not source_dir.exists():
            result.update({"status": "SKIPPED", "reason": "source_missing"})
            results.append(result)
            continue
        if destination_dir.exists():
            result.update({"status": "SKIPPED", "reason": "destination_exists"})
            blockers.append(f"{source_dir}:destination_exists")
            results.append(result)
            continue
        if mode == "dry-run":
            result.update({"status": "WOULD_MOVE", "reason": "dry_run"})
            results.append(result)
            continue
        destination_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_dir), str(destination_dir))
        result.update({"status": "MOVED", "reason": "quarantined"})
        results.append(result)
    status_counts = Counter(str(item.get("status") or "") for item in results)
    return {
        "schema": "nexus.sf_skill_cleanup_apply_result.v1",
        "status": "PASS" if not blockers else "BLOCKED",
        "summary": {
            "mode": mode,
            "result_count": len(results),
            "status_counts": dict(sorted(status_counts.items())),
            "blocker_count": len(blockers),
        },
        "blockers": sorted(blockers),
        "results": results,
    }
