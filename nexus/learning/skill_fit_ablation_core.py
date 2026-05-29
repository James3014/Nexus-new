"""Build and gate receipt-backed skill-fit ablation plans."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from nexus.learning.skill_fit_candidate_index import SkillFitCandidateIndex


REQUIRED_EFFECTIVE_FIELDS = (
    "selected",
    "injected",
    "used",
    "evidence_present",
    "gate_passed",
    "outcome_contributed",
)
BLOCKING_STATUSES = {"BLOCK", "RETURN", "FAIL_CLOSED", "REJECTED"}
POSITIVE_VERDICTS = {"KEEP", "PROMOTE", "PASS", "EFFECTIVE"}
TIMEOUT_INFRA_REASONS = {
    "task_stop_loss_exceeded",
    "timeout_before_model_call",
    "timeout_before_receipt",
    "timeout_during_gemini",
}
CAPABILITY_EXPECTED_CAPABILITY_MAP = {
    "repair_and_coding": {"codeintel", "hyper", "jit_validation"},
    "governance_and_trust": {"artifact_gate", "claim_gate", "delivery_gate", "mempalace_gate", "ultra_review"},
    "research_and_source_discipline": {"lancedb", "research", "semantic_searcher"},
}
CAPABILITY_RELEVANCE_KEYWORDS = {
    "repair_and_coding": (
        "repair",
        "debug",
        "tdd",
        "refactor",
        "simplification",
        "clean",
    ),
    "governance_and_trust": (
        "acceptance",
        "audit",
        "auth",
        "claim",
        "compliance",
        "evidence",
        "failclosed",
        "gate",
        "governance",
        "hardening",
        "security",
        "trust",
    ),
    "research_and_source_discipline": (
        "citation",
        "context",
        "docs",
        "evidence",
        "research",
        "retrieval",
        "source",
        "synthesis",
    ),
}
CAPABILITY_TASK_CATEGORIES = {
    "repair_and_coding": {"bugfix", "test_repair", "refactor", "docs_code_sync"},
    "governance_and_trust": set(),
    "research_and_source_discipline": set(),
}
CAPABILITY_TASK_KEYWORDS = {
    "repair_and_coding": ("bug", "fix", "repair", "test", "refactor", "code", "parser", "normalize"),
    "governance_and_trust": (),
    "research_and_source_discipline": (),
}
CAPABILITY_DISCOVERY_BLOCKED_TASKS = {
    "repair_and_coding": {
        "pub-bug-002",
        "pub-bug-004",
        "pub-ref-002",
        "pub-test-002",
    },
}
CAPABILITY_DISCOVERY_BLOCKED_TASK_CATEGORIES = {
    "repair_and_coding": {
        "test_repair",
    },
}
CAPABILITY_PREFERRED_SKILLS = {
    "repair_and_coding": (
        "tdd",
        "test-driven-development",
        "wondelai-clean-code",
        "workos-live-preview-debug-loop",
        "python-debugpy",
        "wondelai-refactoring-patterns",
    ),
    "governance_and_trust": (
        "nexus-acceptance-evidence-gate",
        "acceptance-evidence-failclosed",
        "nexus-root-cause-probe",
        "nexus-goal-closure-executor",
        "as-security-and-hardening",
        "audit",
    ),
    "research_and_source_discipline": (
        "browserbase-company-research",
        "arxiv",
        "autoresearch",
        "browserbase-search",
        "gbrain-citation-fixer",
        "authenticated-page-access-handoff",
    ),
}
CAPABILITY_DISCOVERY_BLOCKED_SKILLS = {
    "repair_and_coding": {
        "gstack-codex",
        "improve-codebase-architecture",
        "python-debugpy",
        "systematic-debugging",
        "tdd",
        "workos-live-preview-debug-loop",
        "wondelai-clean-architecture",
        "wondelai-clean-code",
        "wondelai-refactoring-patterns",
        "zoom-out",
    },
}
RESEARCH_CANDIDATE_V2_STRONG_SIGNALS = (
    "citation",
    "citations",
    "source",
    "sources",
    "source validation",
    "evidence",
    "raw source",
    "raw sources",
    "methodology",
    "replication",
    "conflict",
    "research",
    "retrieval",
    "synthesis",
    "semantic",
    "academic",
    "canonical tracker",
    "structured data",
    "perplexity",
)
RESEARCH_CANDIDATE_V2_PLATFORM_ONLY_SIGNALS = (
    "browserbase",
    "company",
    "sales",
    "icp",
    "deploy",
    "browser automation",
    "cookie",
    "event prospecting",
    "cli",
    "functions",
)


@dataclass(frozen=True)
class SkillAblationArm:
    arm_id: str
    arm_type: str
    capability: str
    anonymous_label: str
    expected_outcome: str
    skill_id: str = ""
    source_root: str = ""
    source_type: str = ""
    path: str = ""
    sha256: str = ""
    runtime_eligible: bool = False
    ablation_eligible: bool = False
    evidence_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "arm_id": self.arm_id,
            "arm_type": self.arm_type,
            "capability": self.capability,
            "anonymous_label": self.anonymous_label,
            "expected_outcome": self.expected_outcome,
            "skill_id": self.skill_id,
            "source_root": self.source_root,
            "source_type": self.source_type,
            "path": self.path,
            "sha256": self.sha256,
            "runtime_eligible": self.runtime_eligible,
            "ablation_eligible": self.ablation_eligible,
            "evidence_refs": list(self.evidence_refs),
        }


def _stable_digest(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:12]


def _matching_candidates(pool: Mapping[str, Any], capability: str) -> list[Mapping[str, Any]]:
    return SkillFitCandidateIndex.from_pool(pool).matching_for_capability(capability)


def _explicit_skill_candidates(pool: Mapping[str, Any], capability: str, skill_ids: Iterable[str]) -> list[Mapping[str, Any]]:
    return SkillFitCandidateIndex.from_pool(pool).explicit_for_capability(capability, skill_ids)


def _selected_skill_candidates(pool: Mapping[str, Any], capability: str, max_skill_arms: int) -> list[Mapping[str, Any]]:
    return SkillFitCandidateIndex.from_pool(pool).selected_for_capability(capability, max_skill_arms)


def _canonical_skill_id(row: Mapping[str, Any]) -> str:
    return SkillFitCandidateIndex.canonical_skill_id(row)


def _candidate_sort_key(row: Mapping[str, Any], capability: str) -> tuple[int, int, int, str, str]:
    return SkillFitCandidateIndex(()).candidate_sort_key(row, capability)


def _preferred_skill_rank(row: Mapping[str, Any], capability: str) -> int:
    return SkillFitCandidateIndex(()).preferred_skill_rank(row, capability)


def _candidate_relevance(row: Mapping[str, Any], capability: str) -> int:
    return SkillFitCandidateIndex(()).candidate_relevance(row, capability)


def _candidate_has_capability_signal(row: Mapping[str, Any], capability: str) -> bool:
    return SkillFitCandidateIndex(()).has_capability_signal(row, capability)


def _wrong_or_quarantined_candidate(pool: Mapping[str, Any], capability: str) -> Mapping[str, Any] | None:
    return SkillFitCandidateIndex.from_pool(pool).negative_control_for_capability(capability)


def _skill_arm(row: Mapping[str, Any], *, capability: str, index: int) -> SkillAblationArm:
    digest = _stable_digest(capability, str(row.get("path") or ""), str(row.get("sha256") or ""))
    return SkillAblationArm(
        arm_id=f"skill_arm_{index:03d}_{digest}",
        arm_type="skill_ablation",
        capability=capability,
        anonymous_label=f"candidate_{index:03d}",
        expected_outcome="must_prove_selected_injected_used_evidence_gate_outcome",
        skill_id=str(row.get("skill_id") or ""),
        source_root=str(row.get("source_root") or ""),
        source_type=str(row.get("source_type") or ""),
        path=str(row.get("path") or ""),
        sha256=str(row.get("sha256") or ""),
        runtime_eligible=bool(row.get("runtime_eligible")),
        ablation_eligible=bool(row.get("ablation_eligible")),
        evidence_refs=tuple(str(item) for item in row.get("evidence_refs", []) if str(item).strip()),
    )


def build_skill_fit_ablation_plan(
    candidate_pool: Mapping[str, Any],
    *,
    capability: str,
    max_skill_arms: int = 4,
    include_wrong_arm: bool = True,
    explicit_skill_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """Return a deterministic, source-neutral ablation plan for one capability."""

    if not capability:
        raise ValueError("capability is required")
    if max_skill_arms < 1:
        raise ValueError("max_skill_arms must be >= 1")

    explicit = _explicit_skill_candidates(candidate_pool, capability, explicit_skill_ids)
    matching = explicit or _selected_skill_candidates(candidate_pool, capability, max_skill_arms)
    arms: list[SkillAblationArm] = [
        SkillAblationArm(
            arm_id="capability_only",
            arm_type="capability_only",
            capability=capability,
            anonymous_label="capability_only",
            expected_outcome="baseline_without_skill_mount",
            evidence_refs=(f"candidate_pool:{candidate_pool.get('schema', 'unknown')}",),
        )
    ]
    arms.extend(_skill_arm(row, capability=capability, index=index) for index, row in enumerate(matching, start=1))

    wrong = _wrong_or_quarantined_candidate(candidate_pool, capability) if include_wrong_arm else None
    if wrong is not None:
        digest = _stable_digest(capability, str(wrong.get("path") or ""), str(wrong.get("sha256") or ""))
        arms.append(
            SkillAblationArm(
                arm_id=f"wrong_or_quarantined_{digest}",
                arm_type="wrong_or_quarantined_skill",
                capability=capability,
                anonymous_label="negative_control",
                expected_outcome="must_return_or_block",
                skill_id=str(wrong.get("skill_id") or ""),
                source_root=str(wrong.get("source_root") or ""),
                source_type=str(wrong.get("source_type") or ""),
                path=str(wrong.get("path") or ""),
                sha256=str(wrong.get("sha256") or ""),
                runtime_eligible=bool(wrong.get("runtime_eligible")),
                ablation_eligible=bool(wrong.get("ablation_eligible")),
                evidence_refs=tuple(str(item) for item in wrong.get("evidence_refs", []) if str(item).strip()),
            )
        )

    arm_type_counts = Counter(arm.arm_type for arm in arms)
    return {
        "schema": "nexus.skill_fit_ablation_plan.v1",
        "status": "PASS" if matching else "RETURN",
        "capability": capability,
        "summary": {
            "arm_count": len(arms),
            "skill_arm_count": arm_type_counts.get("skill_ablation", 0),
            "negative_control_count": arm_type_counts.get("wrong_or_quarantined_skill", 0),
            "runtime_eligible_skill_arm_count": sum(1 for arm in arms if arm.arm_type == "skill_ablation" and arm.runtime_eligible),
        },
        "claim_boundary": [
            "Capability-only is the baseline; selected skill arms are not value evidence.",
            "A skill arm is effective only with selected, injected, used, evidence_present, gate_passed, and outcome_contributed receipts.",
            "Wrong or quarantined skills must return or block; adopting them is a fail-closed violation.",
            "Skill verdicts must bind evidence_path and receipt_path before promotion, replacement, or rejection claims.",
            "Explicit skill ids are allowed only for seal validation of already-found skills; they do not bypass runtime promotion gates.",
        ],
        "arms": [arm.to_dict() for arm in arms],
    }


def _task_refs_from_lane_manifest(
    lane_manifest: Mapping[str, Any],
    lane_id: str,
    *,
    capability: str,
) -> list[dict[str, str]]:
    lane_ids = {item.strip() for item in lane_id.split(",") if item.strip()}
    refs = []
    for lane in lane_manifest.get("lanes", []):
        if not isinstance(lane, Mapping) or str(lane.get("id") or "") not in lane_ids:
            continue
        for item in lane.get("task_refs", []) or []:
            if not isinstance(item, Mapping):
                continue
            manifest = str(item.get("manifest") or "")
            task_id = str(item.get("task_id") or "")
            if manifest and task_id:
                refs.append({"manifest": manifest, "task_id": task_id})
    return _filter_task_refs_for_capability(refs, capability)


def _task_refs_from_task_manifest(manifest: str | Path, *, capability: str) -> list[dict[str, str]]:
    manifest_text = str(manifest)
    try:
        payload = json.loads(Path(manifest).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    refs = []
    for task in payload.get("tasks", []) or []:
        if not isinstance(task, Mapping):
            continue
        if _task_has_unsupported_execution_context(task):
            continue
        task_id = str(task.get("id") or task.get("task_id") or "")
        if task_id in CAPABILITY_DISCOVERY_BLOCKED_TASKS.get(capability, set()):
            continue
        if _task_category_blocked(task, capability):
            continue
        if task_id and _task_matches_capability(task, capability):
            refs.append({"manifest": manifest_text, "task_id": task_id})
    return refs


def _dedupe_task_refs(task_refs: Iterable[Mapping[str, str]]) -> list[dict[str, str]]:
    out = []
    seen = set()
    for item in task_refs:
        manifest = str(item.get("manifest") or "")
        task_id = str(item.get("task_id") or "")
        key = (manifest, task_id)
        if not manifest or not task_id or key in seen:
            continue
        seen.add(key)
        out.append({"manifest": manifest, "task_id": task_id})
    return out


def _filter_task_refs_for_capability(task_refs: Iterable[Mapping[str, str]], capability: str) -> list[dict[str, str]]:
    accepted_capabilities = CAPABILITY_EXPECTED_CAPABILITY_MAP.get(capability, set())
    out = []
    for item in task_refs:
        manifest = str(item.get("manifest") or "")
        task_id = str(item.get("task_id") or "")
        if not manifest or not task_id:
            continue
        if task_id in CAPABILITY_DISCOVERY_BLOCKED_TASKS.get(capability, set()):
            continue
        task = _task_for_ref(manifest, task_id)
        if (
            task
            and not _task_has_unsupported_execution_context(task)
            and not _task_category_blocked(task, capability)
            and _task_matches_capability(task, capability)
        ):
            out.append({"manifest": manifest, "task_id": task_id})
    return out


def _task_for_ref(manifest: str, task_id: str) -> Mapping[str, Any] | None:
    try:
        payload = json.loads(Path(manifest).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for task in payload.get("tasks", []) or []:
        if not isinstance(task, Mapping):
            continue
        if str(task.get("id") or task.get("task_id") or "") == task_id:
            return task
    return None


def _task_matches_capability(task: Mapping[str, Any], capability: str) -> bool:
    expected = {str(item) for item in task.get("expected_capabilities", []) if str(item)}
    accepted_capabilities = CAPABILITY_EXPECTED_CAPABILITY_MAP.get(capability, set())
    if expected and accepted_capabilities:
        return bool(accepted_capabilities.intersection(expected))
    categories = CAPABILITY_TASK_CATEGORIES.get(capability, set())
    category = str(task.get("category") or task.get("task_type") or "").strip().lower()
    if category and category in categories:
        return True
    keywords = CAPABILITY_TASK_KEYWORDS.get(capability, ())
    text = " ".join(
        str(task.get(key) or "")
        for key in ("id", "task_id", "title", "prompt", "description", "task_desc", "success_criteria")
    ).lower()
    return any(keyword in text for keyword in keywords)


def _task_category_blocked(task: Mapping[str, Any], capability: str) -> bool:
    category = str(task.get("category") or task.get("task_type") or "").strip().lower()
    return bool(category and category in CAPABILITY_DISCOVERY_BLOCKED_TASK_CATEGORIES.get(capability, set()))


def _task_has_unsupported_execution_context(task: Mapping[str, Any]) -> bool:
    repo_kind = str(task.get("repo_kind") or "")
    return (
        repo_kind in {"external", "nexus_internal"}
        or str(task.get("repo_ref") or "") == "current-worktree"
    )


def _expected_capabilities_for_task(manifest: str, task_id: str) -> set[str]:
    try:
        payload = json.loads(Path(manifest).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    for task in payload.get("tasks", []) or []:
        if not isinstance(task, Mapping):
            continue
        if str(task.get("id") or task.get("task_id") or "") != task_id:
            continue
        return {str(item) for item in task.get("expected_capabilities", []) if str(item)}
    return set()


def build_skill_fit_execution_matrix(
    plan: Mapping[str, Any],
    *,
    task_refs: Iterable[Mapping[str, Any]],
    max_tasks: int = 5,
    model: str = "gemini-3-flash-preview",
    runner: str = "scripts/bench/capability_ab_runner.py",
    skill_status_report: str = "docs/reports/NEXUS_SKILL_STATUS_2026-05-15.json",
) -> dict[str, Any]:
    """Expand a plan into a fixed row matrix for live Flash ablation."""

    if max_tasks < 1:
        raise ValueError("max_tasks must be >= 1")
    arms = [arm for arm in plan.get("arms", []) if isinstance(arm, Mapping)]
    selected_tasks = [
        {"manifest": str(item.get("manifest") or ""), "task_id": str(item.get("task_id") or "")}
        for item in task_refs
        if str(item.get("manifest") or "") and str(item.get("task_id") or "")
    ][:max_tasks]

    # Preflight validation for unsupported tasks (e.g. external without setup adapter)
    unsupported_blocked = False
    block_reason = ""
    for task_ref in selected_tasks:
        manifest_path = task_ref["manifest"]
        task_id = task_ref["task_id"]
        try:
            payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            for t in payload.get("tasks", []) or []:
                if not isinstance(t, Mapping):
                    continue
                if str(t.get("id") or t.get("task_id") or "") == task_id:
                    repo_kind = str(t.get("repo_kind") or "")
                    setup_adapter = t.get("setup_adapter")
                    if repo_kind == "external" and not setup_adapter:
                        unsupported_blocked = True
                        block_reason = f"Unsupported external task {task_id} without setup_adapter found in manifest."
                        break
            if unsupported_blocked:
                break
        except Exception:
            pass

    rows_by_arm_type: dict[str, list[dict[str, Any]]] = {
        "capability_only": [],
        "skill_ablation": [],
        "wrong_or_quarantined_skill": [],
    }
    for task_index, task in enumerate(selected_tasks, start=1):
        for arm in arms:
            arm_type = str(arm.get("arm_type") or "")
            skill_id = str(arm.get("skill_id") or "")
            if arm_type == "capability_only":
                skill_mount_requests: list[str] = []
            elif arm_type == "skill_ablation":
                skill_mount_requests = [skill_id]
            elif arm_type == "wrong_or_quarantined_skill":
                skill_mount_requests = [skill_id]
            else:
                skill_mount_requests = []
            row = {
                    "row_id": f"{plan.get('capability')}::{task['task_id']}::{arm.get('arm_id')}",
                    "task_index": task_index,
                    "task_ref": task,
                    "model": model,
                    "capability": str(plan.get("capability") or ""),
                    "arm_id": str(arm.get("arm_id") or ""),
                    "arm_type": arm_type,
                    "anonymous_label": str(arm.get("anonymous_label") or ""),
                    "skill_id": skill_id,
                    "source_root": str(arm.get("source_root") or ""),
                    "source_type": str(arm.get("source_type") or ""),
                    "runtime_eligible": bool(arm.get("runtime_eligible")),
                    "ablation_eligible": bool(arm.get("ablation_eligible")),
                    "skill_mount_requests": skill_mount_requests,
                    "runner_env": {
                        "NEXUS_VALUE_HIDDEN_VERIFIER": "1",
                        "NEXUS_DIRECT_GEMINI_MODEL": model,
                        "NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS": "1" if arm_type == "skill_ablation" else "0",
                        "NEXUS_BENCH_SKILL_MOUNT_REQUESTS": json.dumps(skill_mount_requests, ensure_ascii=False),
                        "NEXUS_BENCH_SKILL_STATUS_REPORT": skill_status_report,
                    },
                    "runner_args": [
                        "uv",
                        "run",
                        "python",
                        runner,
                        "--tasks-file",
                        task["manifest"],
                        "--task-id-filter",
                        task["task_id"],
                        "--max-tasks",
                        "1",
                        "--timeout-sec",
                        "300",
                        "--per-task-stop-loss-sec",
                        "600",
                        "--stop-loss-sec",
                        "600",
                        "--nexus-only",
                        "--gemini-model",
                        model,
                        "--with-nexus-runner",
                        "subprocess",
                        "--with-llm-mode",
                        "all",
                        "--without-mode",
                        "gemini",
                        "--force-flow",
                        "hyper_sprint",
                        "--enable-autoreason-executor",
                        "--enable-ddtree-executor",
                        "--enable-ultra-review-dry-gate",
                        "--llm-candidate-cap",
                        "3",
                        "--evidence-bundle",
                    ],
                    "expected_outcome": str(arm.get("expected_outcome") or ""),
                    "gate_requirements": list(REQUIRED_EFFECTIVE_FIELDS),
                }
            rows_by_arm_type.setdefault(arm_type, []).append(row)
    expected_rows = len(selected_tasks) * len(arms)
    rows = [
        *rows_by_arm_type.get("capability_only", []),
        *rows_by_arm_type.get("skill_ablation", []),
        *rows_by_arm_type.get("wrong_or_quarantined_skill", []),
    ]
    rows_by_capability = Counter(str(row.get("capability") or "") for row in rows)
    return {
        "schema": "nexus.skill_fit_execution_matrix.v1",
        "status": "RETURN" if unsupported_blocked else ("PASS" if rows and len(rows) == expected_rows else "RETURN"),
        "plan_schema": plan.get("schema", ""),
        "capability": plan.get("capability", ""),
        "summary": {
            "capability_count": len([capability for capability in rows_by_capability if capability]),
            "rows_by_capability": dict(sorted(rows_by_capability.items())),
            "task_count": len(selected_tasks),
            "arm_count": len(arms),
            "row_count": len(rows),
            "expected_row_count": expected_rows,
            "model": model,
            "block_reason": block_reason,
        },
        "claim_boundary": [
            "This matrix schedules ablation rows; it is not delivery or skill value evidence.",
            "Rows become usable only after live receipts pass the skill-fit ablation gate.",
            "Runner args are per-row contracts; live execution must still stop on first delivery, trust, or gate failure.",
        ],
        "rows": rows,
    }


def build_skill_fit_execution_matrix_from_files(
    *,
    plan_path: str | Path,
    lane_manifest_path: str | Path,
    lane_id: str,
    extra_task_manifests: Iterable[str | Path] = (),
    max_tasks: int = 5,
    model: str = "gemini-3-flash-preview",
    runner: str = "scripts/bench/capability_ab_runner.py",
    skill_status_report: str = "docs/reports/NEXUS_SKILL_STATUS_2026-05-15.json",
) -> dict[str, Any]:
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    lane_manifest = json.loads(Path(lane_manifest_path).read_text(encoding="utf-8"))
    capability = str(plan.get("capability") or "")
    task_refs = _task_refs_from_lane_manifest(lane_manifest, lane_id, capability=capability)
    for manifest in extra_task_manifests:
        task_refs.extend(_task_refs_from_task_manifest(manifest, capability=capability))
    return build_skill_fit_execution_matrix(
        plan,
        task_refs=_dedupe_task_refs(task_refs),
        max_tasks=max_tasks,
        model=model,
        runner=runner,
        skill_status_report=skill_status_report,
    )


def _truthy(row: Mapping[str, Any], name: str) -> bool:
    return row.get(name) is True


def _row_arm_type(row: Mapping[str, Any], plan_by_arm: Mapping[str, Mapping[str, Any]]) -> str:
    arm = plan_by_arm.get(str(row.get("arm_id") or ""), {})
    return str(row.get("arm_type") or arm.get("arm_type") or "")


def evaluate_skill_fit_ablation_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Gate ablation receipts without letting selected-only rows claim value."""

    plan_by_arm = {str(arm.get("arm_id") or ""): arm for arm in (plan or {}).get("arms", []) if isinstance(arm, Mapping)}
    results: list[dict[str, Any]] = []
    violations: list[dict[str, str]] = []
    for row in rows:
        arm_id = str(row.get("arm_id") or "")
        arm_type = _row_arm_type(row, plan_by_arm)
        missing_chain = [field for field in REQUIRED_EFFECTIVE_FIELDS if not _truthy(row, field)]
        evidence_path = str(row.get("evidence_path") or "")
        receipt_path = str(row.get("receipt_path") or "")
        trust_mismatch = bool(row.get("trust_mismatch"))
        status = str(row.get("status") or row.get("verdict") or "").upper()
        claimed_positive = status in POSITIVE_VERDICTS or row.get("claimed_effective") is True
        effective = not missing_chain and bool(evidence_path) and bool(receipt_path) and not trust_mismatch

        if trust_mismatch:
            violations.append({"arm_id": arm_id, "reason": "trust_mismatch_nonzero"})
        if claimed_positive and missing_chain:
            violations.append({"arm_id": arm_id, "reason": f"selected_only_or_incomplete_chain:{','.join(missing_chain)}"})
        if claimed_positive and (not evidence_path or not receipt_path):
            violations.append({"arm_id": arm_id, "reason": "positive_verdict_without_evidence_or_receipt_path"})
        if arm_type == "wrong_or_quarantined_skill":
            blocked = status in BLOCKING_STATUSES
            adopted = any(_truthy(row, field) for field in ("selected", "injected", "used", "gate_passed", "outcome_contributed"))
            if not blocked or adopted:
                violations.append({"arm_id": arm_id, "reason": "wrong_or_quarantined_skill_not_blocked"})

        results.append(
            {
                "arm_id": arm_id,
                "arm_type": arm_type,
                "status": status,
                "effective": effective,
                "missing_effective_fields": missing_chain,
                "evidence_path": evidence_path,
                "receipt_path": receipt_path,
                "trust_mismatch": trust_mismatch,
            }
        )

    return {
        "schema": "nexus.skill_fit_ablation_gate.v1",
        "status": "PASS" if not violations else "RETURN",
        "summary": {
            "row_count": len(results),
            "effective_count": sum(1 for row in results if row["effective"]),
            "violation_count": len(violations),
        },
        "violations": violations,
        "results": results,
    }


def classify_skill_fit_failure(row: Mapping[str, Any]) -> dict[str, str]:
    """Classify fail-fast skill-fit rows into policy actions."""

    if str(row.get("status") or "").upper() == "PASS":
        return {"kind": "none", "action": "continue", "reason": ""}

    arm_type = str(row.get("arm_type") or "")
    skill_id = str(row.get("skill_id") or "")
    task_ref = row.get("task_ref") if isinstance(row.get("task_ref"), Mapping) else {}
    repo_kind = str(task_ref.get("repo_kind") or "")
    stdout_tail = str(row.get("stdout_tail") or "")
    stderr_tail = str(row.get("stderr_tail") or "")
    bench_row = row.get("benchmark_row") if isinstance(row.get("benchmark_row"), Mapping) else {}
    infra_reason = str(bench_row.get("infra_invalid_reason") or "")
    text = "\n".join([infra_reason, str(row.get("reason") or ""), stdout_tail, stderr_tail])

    if infra_reason in {"model_call_without_tokens", "receipt_data_contract_violation"}:
        return {
            "kind": "provider_token_ineligible",
            "action": "stop_full_live_and_run_probe_or_clean_replay",
            "reason": infra_reason,
        }
    if repo_kind == "external" or "clone/setup adapter" in text:
        return {
            "kind": "adapter_missing",
            "action": "remove_from_skill_fit_until_adapter_exists",
            "reason": "external_or_adapter_missing",
        }
    if infra_reason in TIMEOUT_INFRA_REASONS or "timeout" in text.lower():
        if arm_type == "capability_only":
            return {
                "kind": "task_unstable_long_tail",
                "action": "move_task_to_long_tail_lane",
                "reason": infra_reason or "timeout",
            }
        if arm_type == "skill_ablation":
            return {
                "kind": "skill_stop_loss",
                "action": f"demote_skill_for_capability:{skill_id}",
                "reason": infra_reason or "timeout",
            }
    if arm_type == "wrong_or_quarantined_skill":
        return {
            "kind": "negative_control_violation",
            "action": "block_matrix_and_fix_quarantine_policy",
            "reason": str(row.get("reason") or "wrong_skill_not_blocked"),
        }
    return {
        "kind": "unclassified_return",
        "action": "inspect_row_before_rerun",
        "reason": str(row.get("reason") or "return"),
    }


@dataclass(frozen=True)
class SkillFitCatalogIndex:
    """Pre-index catalog rows without making promotion decisions."""

    rows: tuple[Mapping[str, Any], ...]
    planned_rows: int
    completed_rows: int
    by_skill: Mapping[tuple[str, str], tuple[Mapping[str, Any], ...]]
    negative_rows: tuple[Mapping[str, Any], ...]
    capability_only_rows: tuple[Mapping[str, Any], ...]

    @classmethod
    def from_run_summary(cls, run_summary: Mapping[str, Any]) -> "SkillFitCatalogIndex":
        rows = tuple(row for row in run_summary.get("results", []) if isinstance(row, Mapping))
        run_counts = run_summary.get("summary") if isinstance(run_summary.get("summary"), Mapping) else {}
        by_skill: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
        negative_rows: list[Mapping[str, Any]] = []
        capability_only_rows: list[Mapping[str, Any]] = []
        for row in rows:
            arm_type = str(row.get("arm_type") or "")
            if arm_type == "capability_only":
                capability_only_rows.append(row)
                continue
            if arm_type == "wrong_or_quarantined_skill":
                negative_rows.append(row)
                continue
            if arm_type != "skill_ablation":
                continue
            skill_id = str(row.get("skill_id") or "")
            if not skill_id:
                continue
            capability = _catalog_row_capability(row)
            by_skill.setdefault((capability, skill_id), []).append(row)
        return cls(
            rows=rows,
            planned_rows=int(run_counts.get("planned_rows") or len(rows)),
            completed_rows=int(run_counts.get("completed_rows") or len(rows)),
            by_skill={key: tuple(grouped_rows) for key, grouped_rows in sorted(by_skill.items())},
            negative_rows=tuple(negative_rows),
            capability_only_rows=tuple(capability_only_rows),
        )

    @property
    def skill_keys(self) -> tuple[tuple[str, str], ...]:
        return tuple(self.by_skill.keys())


def build_skill_fit_catalog(run_summary: Mapping[str, Any]) -> dict[str, Any]:
    """Summarize live ablation receipts into skill policy verdicts."""

    index = SkillFitCatalogIndex.from_run_summary(run_summary)
    planned_rows = index.planned_rows
    completed_rows = index.completed_rows
    negative_rows = index.negative_rows
    capability_only = index.capability_only_rows

    verdicts = []
    for (capability, skill_id), rows in index.by_skill.items():
        effective_rows = [
            row
            for row in rows
            if row.get("status") == "PASS"
            and (row.get("ablation_gate") or {}).get("status") == "PASS"
            and (row.get("ablation_gate_row") or {}).get("status") == "KEEP"
        ]
        trust_clean_rows = [row for row in rows if not (row.get("ablation_gate_row") or {}).get("trust_mismatch")]
        evidence_refs = [
            (row.get("ablation_gate_row") or {}).get("evidence_path", "")
            for row in rows
            if (row.get("ablation_gate_row") or {}).get("evidence_path")
        ]
        receipt_refs = [
            (row.get("ablation_gate_row") or {}).get("receipt_path", "")
            for row in rows
            if (row.get("ablation_gate_row") or {}).get("receipt_path")
        ]
        task_buckets = sorted(
            {
                _catalog_task_bucket(row)
                for row in rows
                if _catalog_task_bucket(row)
            }
        )
        runtime_eligible = any(bool(row.get("runtime_eligible")) for row in rows)
        if len(trust_clean_rows) != len(rows):
            verdict = "quarantine"
        elif len(effective_rows) == len(rows) and runtime_eligible:
            verdict = "keep"
        elif len(effective_rows) == len(rows):
            verdict = "replace_candidate"
        elif effective_rows:
            verdict = "needs_more_data"
        else:
            verdict = "reject"
        verdicts.append(
            {
                "skill_id": skill_id,
                "capability": capability,
                "anonymous_label": rows[0].get("anonymous_label", ""),
                "source_root": rows[0].get("source_root", ""),
                "runtime_eligible": runtime_eligible,
                "tested_rows": len(rows),
                "effective_rows": len(effective_rows),
                "trust_clean_rows": len(trust_clean_rows),
                "verdict": verdict,
                "evidence_refs": evidence_refs,
                "receipt_refs": receipt_refs,
                "task_buckets": task_buckets,
            }
        )

    negative_blocked = [
        row
        for row in negative_rows
        if (row.get("ablation_gate_row") or {}).get("status") == "BLOCK"
        and (row.get("ablation_gate") or {}).get("status") == "PASS"
    ]
    status = "PASS"
    failures = []
    run_status = str(run_summary.get("status") or "PASS")
    if run_status != "PASS" or completed_rows != planned_rows:
        status = "RETURN"
        failures.append("matrix_completion_gate_return")
    if len(negative_blocked) != len(negative_rows):
        status = "RETURN"
        failures.append("negative_control_not_fully_blocked")
    if any(item["verdict"] == "quarantine" for item in verdicts):
        status = "RETURN"
        failures.append("trust_mismatch_in_skill_arm")
    return {
        "schema": "nexus.skill_fit_catalog.v1",
        "status": status,
        "mode": run_summary.get("mode", ""),
        "matrix_path": run_summary.get("matrix_path", ""),
        "summary": {
            "planned_rows": planned_rows,
            "completed_rows": completed_rows,
            "matrix_complete": completed_rows == planned_rows,
            "capability_only_rows": len(capability_only),
            "skill_count": len(verdicts),
            "negative_control_rows": len(negative_rows),
            "negative_control_blocked_rows": len(negative_blocked),
            "keep_count": sum(1 for item in verdicts if item["verdict"] == "keep"),
            "replace_candidate_count": sum(1 for item in verdicts if item["verdict"] == "replace_candidate"),
            "reject_count": sum(1 for item in verdicts if item["verdict"] == "reject"),
            "needs_more_data_count": sum(1 for item in verdicts if item["verdict"] == "needs_more_data"),
        },
        "failures": failures,
        "claim_boundary": [
            "Catalog verdicts are valid only for this capability, task set, model, and matrix version.",
            "replace_candidate means import/review candidate, not runtime promotion.",
            "runtime policy changes require a later Flash 50/100 regression gate.",
        ],
        "skill_verdicts": verdicts,
    }


def build_skill_discovery_rerun_queue(catalog: Mapping[str, Any]) -> dict[str, Any]:
    """Build a conservative discovery queue from catalog verdicts."""

    queue = []
    skipped = []
    for item in catalog.get("skill_verdicts", []) or []:
        if not isinstance(item, Mapping):
            continue
        verdict = str(item.get("verdict") or "")
        entry = {
            "capability": str(item.get("capability") or ""),
            "skill_id": str(item.get("skill_id") or ""),
            "verdict": verdict,
            "tested_rows": int(item.get("tested_rows") or 0),
            "effective_rows": int(item.get("effective_rows") or 0),
        }
        if verdict == "needs_more_data":
            queue.append({**entry, "reason": "needs_more_data"})
        else:
            skipped.append({**entry, "reason": f"skip_{verdict or 'unknown'}"})
    return {
        "schema": "nexus.skill_discovery_rerun_queue.v1",
        "status": "PASS",
        "queue_count": len(queue),
        "skipped_count": len(skipped),
        "queue": queue,
        "skipped": skipped,
        "claim_boundary": [
            "Discovery queue schedules validation only; it must not update runtime defaults.",
            "Rejected skills are skipped until the taskset or candidate source changes.",
        ],
    }


def select_skill_discovery_replay_row_ids(matrix: Mapping[str, Any], queue: Mapping[str, Any]) -> list[str]:
    """Select skill-ablation row ids for queued capability/skill replays."""

    wanted = {
        (str(item.get("capability") or ""), str(item.get("skill_id") or ""))
        for item in queue.get("queue", []) or []
        if isinstance(item, Mapping)
    }
    selected = []
    seen = set()
    for row in matrix.get("rows", []) or []:
        if not isinstance(row, Mapping):
            continue
        key = (str(row.get("capability") or ""), str(row.get("skill_id") or ""))
        row_id = str(row.get("row_id") or "")
        if str(row.get("arm_type") or "") != "skill_ablation":
            continue
        if key not in wanted or not row_id or row_id in seen:
            continue
        selected.append(row_id)
        seen.add(row_id)
    return selected


def build_capability_skill_promotion_policy(catalog: Mapping[str, Any]) -> dict[str, Any]:
    """Convert receipt-backed catalog verdicts into a non-runtime policy draft."""

    defaults: dict[str, str] = {}
    alternates: dict[str, list[str]] = {}
    needs_more_data: dict[str, list[str]] = {}
    rejected: dict[str, list[str]] = {}
    failures = list(catalog.get("failures", []) or [])
    for item in catalog.get("skill_verdicts", []) or []:
        if not isinstance(item, Mapping):
            continue
        capability = str(item.get("capability") or "")
        skill_id = str(item.get("skill_id") or "")
        verdict = str(item.get("verdict") or "")
        evidence_refs = [str(ref) for ref in item.get("evidence_refs", []) or [] if str(ref)]
        receipt_refs = [str(ref) for ref in item.get("receipt_refs", []) or [] if str(ref)]
        if verdict in {"keep", "replace_candidate"} and (not evidence_refs or not receipt_refs):
            failures.append(f"{capability}:{skill_id}:promotion_without_evidence_or_receipt")
            continue
        if verdict == "keep" and capability and skill_id:
            defaults.setdefault(capability, skill_id)
        elif verdict == "replace_candidate" and capability and skill_id:
            alternates.setdefault(capability, []).append(skill_id)
        elif verdict == "needs_more_data" and capability and skill_id:
            needs_more_data.setdefault(capability, []).append(skill_id)
        elif capability and skill_id:
            rejected.setdefault(capability, []).append(skill_id)
    return {
        "schema": "nexus.capability_skill_promotion_policy_draft.v1",
        "status": "PASS" if not failures else "RETURN",
        "runtime_update_allowed": False,
        "defaults": defaults,
        "alternates": {key: sorted(value) for key, value in sorted(alternates.items())},
        "needs_more_data": {key: sorted(value) for key, value in sorted(needs_more_data.items())},
        "rejected": {key: sorted(value) for key, value in sorted(rejected.items())},
        "failures": sorted(set(str(item) for item in failures)),
        "claim_boundary": [
            "This is a promotion draft, not a runtime policy write.",
            "Runtime defaults require a later Flash50/100 validation gate.",
        ],
    }


def build_skill_promotion_threshold_contract(
    catalog: Mapping[str, Any],
    promotion_policy: Mapping[str, Any],
    *,
    rerun_queue: Mapping[str, Any] | None = None,
    min_tested_rows_per_skill: int = 30,
    min_seal_runs_before_runtime: int = 2,
    default_min_effective_rate: float = 0.8,
    alternate_min_effective_rate: float = 0.6,
    min_task_buckets_for_alternate: int = 2,
    required_validation_lanes: Iterable[str] = ("Flash50", "Flash100"),
) -> dict[str, Any]:
    """Freeze promotion thresholds without updating runtime defaults."""

    failures: list[str] = []
    catalog_summary = catalog.get("summary") if isinstance(catalog.get("summary"), Mapping) else {}
    matrix_complete = bool(catalog_summary.get("matrix_complete"))
    catalog_status = str(catalog.get("status") or "")
    policy_status = str(promotion_policy.get("status") or "")
    runtime_update_requested = bool(promotion_policy.get("runtime_update_allowed"))
    if catalog_status != "PASS":
        failures.append("catalog_not_pass")
    if policy_status != "PASS":
        failures.append("promotion_policy_not_pass")
    if not matrix_complete:
        failures.append("matrix_not_complete")
    if runtime_update_requested:
        failures.append("runtime_update_must_remain_false")

    validation_lanes = tuple(str(item) for item in required_validation_lanes if str(item))
    queue_items = rerun_queue.get("queue", []) if isinstance(rerun_queue, Mapping) else []
    queued = {
        (str(item.get("capability") or ""), str(item.get("skill_id") or ""))
        for item in queue_items
        if isinstance(item, Mapping)
    }
    capability_thresholds = []
    promotion_ready_count = 0
    for item in catalog.get("skill_verdicts", []) or []:
        if not isinstance(item, Mapping):
            continue
        capability = str(item.get("capability") or "")
        skill_id = str(item.get("skill_id") or "")
        verdict = str(item.get("verdict") or "")
        tested_rows = int(item.get("tested_rows") or 0)
        effective_rows = int(item.get("effective_rows") or 0)
        effective_rate = (effective_rows / tested_rows) if tested_rows else 0.0
        task_buckets = [str(bucket) for bucket in item.get("task_buckets", []) or [] if str(bucket)]
        task_bucket_count = len(set(task_buckets))
        evidence_refs = [str(ref) for ref in item.get("evidence_refs", []) or [] if str(ref)]
        receipt_refs = [str(ref) for ref in item.get("receipt_refs", []) or [] if str(ref)]
        evidence_complete = bool(evidence_refs and receipt_refs)
        observed_rows_ok = tested_rows >= min_tested_rows_per_skill
        positive = verdict in {"keep", "replace_candidate"}
        if positive and not evidence_complete:
            failures.append(f"{capability}:{skill_id}:positive_without_evidence_or_receipt")
        if positive and not observed_rows_ok:
            failures.append(f"{capability}:{skill_id}:insufficient_tested_rows")
        threshold_status = "reject"
        threshold_recommendation = "reject"
        if verdict == "needs_more_data":
            threshold_status = "targeted_replay_required" if (capability, skill_id) in queued else "queue_missing"
            threshold_recommendation = "needs_more_data"
        elif positive and evidence_complete and observed_rows_ok:
            threshold_status = "validation_required"
            if verdict == "keep" and effective_rate >= default_min_effective_rate:
                threshold_recommendation = "default_candidate"
            elif effective_rate >= alternate_min_effective_rate and task_bucket_count >= min_task_buckets_for_alternate:
                threshold_recommendation = "alternate_candidate"
            else:
                threshold_recommendation = "needs_more_data"
            promotion_ready_count += 1
        elif verdict == "quarantine":
            threshold_status = "quarantine"
            threshold_recommendation = "quarantine"
        capability_thresholds.append(
            {
                "capability": capability,
                "skill_id": skill_id,
                "verdict": verdict,
                "tested_rows": tested_rows,
                "effective_rows": effective_rows,
                "effective_rate": round(effective_rate, 4),
                "task_bucket_count": task_bucket_count,
                "evidence_complete": evidence_complete,
                "observed_rows_ok": observed_rows_ok,
                "threshold_status": threshold_status,
                "threshold_recommendation": threshold_recommendation,
                "required_validation_lanes": list(validation_lanes) if threshold_status == "validation_required" else [],
            }
        )

    return {
        "schema": "nexus.skill_promotion_threshold_contract.v1",
        "status": "PASS" if not failures else "RETURN",
        "runtime_update_allowed": False,
        "flash100_allowed": promotion_ready_count > 0 and not failures,
        "promotion_allowed": False,
        "thresholds": {
            "min_tested_rows_per_skill": min_tested_rows_per_skill,
            "min_seal_runs_before_runtime": min_seal_runs_before_runtime,
            "default_min_effective_rate": default_min_effective_rate,
            "alternate_min_effective_rate": alternate_min_effective_rate,
            "min_task_buckets_for_alternate": min_task_buckets_for_alternate,
            "required_validation_lanes": list(validation_lanes),
            "requires_repeated_denominator": True,
            "requires_trust_mismatch_zero": True,
            "requires_evidence_and_receipt_refs": True,
        },
        "summary": {
            "skill_count": len(capability_thresholds),
            "promotion_ready_count": promotion_ready_count,
            "needs_targeted_replay_count": sum(1 for item in capability_thresholds if item["threshold_status"] == "targeted_replay_required"),
            "default_candidate_count": sum(1 for item in capability_thresholds if item["threshold_recommendation"] == "default_candidate"),
            "alternate_candidate_count": sum(1 for item in capability_thresholds if item["threshold_recommendation"] == "alternate_candidate"),
            "queue_count": len(queued),
            "matrix_complete": matrix_complete,
        },
        "failures": sorted(set(failures)),
        "capability_skill_thresholds": capability_thresholds,
        "claim_boundary": [
            "This contract freezes promotion thresholds; it does not update runtime policy.",
            "A single diagnostic Flash180 run can schedule targeted replay but cannot by itself promote runtime defaults.",
            "Flash100 is allowed only after at least one capability/skill pair has receipt-backed positive verdict evidence.",
        ],
    }


def build_skill_fit_row_level_rca(
    run_summary: Mapping[str, Any],
    catalog: Mapping[str, Any] | None = None,
    *,
    capability: str = "",
    alternate_min_effective_rate: float = 0.6,
    promising_min_effective_rate: float = 0.4,
) -> dict[str, Any]:
    """Explain skill-fit outcomes at row granularity without changing promotion state."""

    results = [row for row in run_summary.get("results", []) or [] if isinstance(row, Mapping)]
    target_capability = capability or str(catalog.get("skill_verdicts", [{}])[0].get("capability") if catalog else "") or str(
        run_summary.get("capability") or ""
    )
    capability_results = [
        row for row in results if not target_capability or str(row.get("capability") or "") == target_capability
    ]
    baseline_by_task = {
        _row_task_key(row): row
        for row in capability_results
        if str(row.get("arm_type") or "") == "capability_only" and _row_task_key(row)
    }
    catalog_by_skill = {
        str(item.get("skill_id") or ""): item
        for item in (catalog or {}).get("skill_verdicts", []) or []
        if isinstance(item, Mapping)
    }
    rows_by_skill: dict[str, list[Mapping[str, Any]]] = {}
    for row in capability_results:
        if str(row.get("arm_type") or "") != "skill_ablation":
            continue
        skill_id = str(row.get("skill_id") or "")
        if skill_id:
            rows_by_skill.setdefault(skill_id, []).append(row)

    skill_analyses = []
    for skill_id, rows in sorted(rows_by_skill.items()):
        effective_rows = [_is_effective_skill_row(row) for row in rows]
        effective_count = sum(1 for item in effective_rows if item)
        tested_rows = len(rows)
        effective_rate = (effective_count / tested_rows) if tested_rows else 0.0
        verdict = str(catalog_by_skill.get(skill_id, {}).get("verdict") or "")
        bucket_counts: Counter[str] = Counter()
        effective_bucket_counts: Counter[str] = Counter()
        row_records = []
        for row, effective in zip(rows, effective_rows, strict=False):
            bucket = _catalog_task_bucket(row)
            if bucket:
                bucket_counts[bucket] += 1
                if effective:
                    effective_bucket_counts[bucket] += 1
            task_key = _row_task_key(row)
            baseline = baseline_by_task.get(task_key, {})
            gate_row = row.get("ablation_gate_row") if isinstance(row.get("ablation_gate_row"), Mapping) else {}
            row_records.append(
                {
                    "row_id": str(row.get("row_id") or ""),
                    "task_key": task_key,
                    "task_ref": row.get("task_ref") if isinstance(row.get("task_ref"), Mapping) else {},
                    "task_bucket": bucket,
                    "baseline_status": str(baseline.get("status") or ""),
                    "skill_status": str(row.get("status") or ""),
                    "gate_status": str((row.get("ablation_gate") or {}).get("status") if isinstance(row.get("ablation_gate"), Mapping) else ""),
                    "gate_row_status": str(gate_row.get("status") or ""),
                    "effective": effective,
                    "missing_effective_fields": list(gate_row.get("missing_effective_fields", []) or []),
                    "trust_mismatch": bool(gate_row.get("trust_mismatch")),
                    "evidence_path": str(gate_row.get("evidence_path") or ""),
                    "receipt_path": str(gate_row.get("receipt_path") or ""),
                }
            )
        recommendation = "reject_or_replace_candidate"
        if verdict == "needs_more_data" and effective_rate >= alternate_min_effective_rate:
            recommendation = "eligible_for_threshold_review"
        elif verdict == "needs_more_data" and effective_rate >= promising_min_effective_rate:
            recommendation = "targeted_replay"
        elif verdict == "needs_more_data" and effective_count > 0:
            recommendation = "candidate_pool_v2_or_taskset_expansion"
        elif verdict == "reject":
            recommendation = "skip_until_candidate_or_taskset_changes"
        skill_analyses.append(
            {
                "skill_id": skill_id,
                "verdict": verdict,
                "tested_rows": tested_rows,
                "effective_rows": effective_count,
                "effective_rate": round(effective_rate, 4),
                "task_bucket_counts": dict(sorted(bucket_counts.items())),
                "effective_task_bucket_counts": dict(sorted(effective_bucket_counts.items())),
                "recommendation": recommendation,
                "targeted_replay_row_ids": [
                    record["row_id"]
                    for record in row_records
                    if recommendation in {"targeted_replay", "eligible_for_threshold_review"}
                ],
                "rows": row_records,
            }
        )

    ready_count = sum(1 for item in skill_analyses if item["recommendation"] == "eligible_for_threshold_review")
    targeted_count = sum(1 for item in skill_analyses if item["recommendation"] == "targeted_replay")
    return {
        "schema": "nexus.skill_fit_row_level_rca.v1",
        "status": "PASS" if capability_results else "RETURN",
        "capability": target_capability,
        "summary": {
            "row_count": len(capability_results),
            "baseline_task_count": len(baseline_by_task),
            "skill_count": len(skill_analyses),
            "eligible_for_threshold_review_count": ready_count,
            "targeted_replay_count": targeted_count,
            "runtime_update_allowed": False,
            "flash100_allowed": False,
        },
        "root_cause": "skill_outcome_contribution_below_threshold"
        if skill_analyses and ready_count == 0
        else "threshold_review_required",
        "skill_analyses": skill_analyses,
        "claim_boundary": [
            "Row-level RCA explains discovery evidence; it does not promote runtime defaults.",
            "Targeted replay is allowed only for receipt-backed needs_more_data skills.",
            "Flash100 remains blocked until a threshold contract reports alternate/default readiness.",
        ],
    }


def build_research_candidate_v2_report(
    candidate_pool: Mapping[str, Any],
    previous_catalog: Mapping[str, Any],
    *,
    capability: str = "research_and_source_discipline",
    max_candidates: int = 4,
) -> dict[str, Any]:
    """Select a safer research/source-discipline candidate v2 pool from audited candidates."""

    rejected = {
        str(item.get("skill_id") or "")
        for item in previous_catalog.get("skill_verdicts", []) or []
        if isinstance(item, Mapping)
        and str(item.get("capability") or "") == capability
        and str(item.get("verdict") or "") == "reject"
    }
    scored = []
    skipped = []
    seen: set[str] = set()
    for row in candidate_pool.get("candidates", []) or []:
        if not isinstance(row, Mapping):
            continue
        skill_id = str(row.get("skill_id") or "")
        canonical = _canonical_skill_id(row)
        if canonical in seen:
            continue
        seen.add(canonical)
        capability_candidates = {str(item) for item in row.get("capability_candidates", []) or []}
        if capability not in capability_candidates or row.get("ablation_eligible") is not True:
            continue
        if skill_id in rejected:
            skipped.append(_candidate_v2_decision(row, "skip_previously_rejected", 0, 0))
            continue
        score, penalty = _research_candidate_v2_score(row)
        if score <= 0:
            skipped.append(_candidate_v2_decision(row, "skip_no_source_discipline_signal", score, penalty))
            continue
        if penalty >= score:
            skipped.append(_candidate_v2_decision(row, "skip_platform_or_sales_heavy", score, penalty))
            continue
        scored.append(_candidate_v2_decision(row, "include_v2", score, penalty))

    selected = sorted(
        scored,
        key=lambda item: (
            -int(item["source_discipline_score"]),
            int(item["platform_only_penalty"]),
            str(item["skill_id"]),
            str(item["path"]),
        ),
    )[:max_candidates]
    selected_ids = {str(item["skill_id"]) for item in selected}
    v2_candidates = [
        row
        for row in candidate_pool.get("candidates", []) or []
        if isinstance(row, Mapping) and str(row.get("skill_id") or "") in selected_ids
    ]
    negative_control = _wrong_or_quarantined_candidate(candidate_pool, capability)
    if negative_control is not None:
        v2_candidates.append(negative_control)
    return {
        "schema": "nexus.research_candidate_v2_report.v1",
        "status": "PASS" if selected else "RETURN",
        "capability": capability,
        "runtime_update_allowed": False,
        "summary": {
            "previous_reject_count": len(rejected),
            "selected_candidate_count": len(selected),
            "skipped_count": len(skipped),
            "max_candidates": max_candidates,
        },
        "selection_policy": {
            "requires_ablation_eligible": True,
            "excludes_previous_rejects": True,
            "requires_source_discipline_score_gt_platform_penalty": True,
            "strong_signals": list(RESEARCH_CANDIDATE_V2_STRONG_SIGNALS),
            "platform_only_penalty_signals": list(RESEARCH_CANDIDATE_V2_PLATFORM_ONLY_SIGNALS),
        },
        "selected_candidates": selected,
        "skipped_candidates": skipped[:100],
        "candidate_pool_v2": {
            "schema": "nexus.fair_skill_candidate_pool.v2.slice",
            "status": "PASS" if selected else "RETURN",
            "source_status_report_schema": candidate_pool.get("source_status_report_schema", ""),
            "summary": {
                "total_candidates": len(v2_candidates),
                "selected_candidate_count": len(selected),
                "negative_control_count": 1 if negative_control is not None else 0,
                "capability": capability,
                "source_root_counts": dict(Counter(str(row.get("source_root") or "") for row in v2_candidates)),
            },
            "claim_boundary": [
                "This v2 pool is ablation-only and cannot update runtime policy.",
                "Rejected v1 candidates are excluded until source or taskset changes.",
            ],
            "candidates": v2_candidates,
        },
        "claim_boundary": [
            "Candidate v2 changes discovery inputs only; it does not prove skill value.",
            "Selected candidates still require live ablation, receipt paths, and threshold contracts.",
        ],
    }


def write_skill_fit_row_level_rca(
    *,
    run_summary_path: str | Path,
    catalog_path: str | Path,
    output_path: str | Path,
    capability: str = "",
) -> dict[str, Any]:
    rca = build_skill_fit_row_level_rca(
        json.loads(Path(run_summary_path).read_text(encoding="utf-8")),
        json.loads(Path(catalog_path).read_text(encoding="utf-8")),
        capability=capability,
    )
    Path(output_path).write_text(json.dumps(rca, indent=2, ensure_ascii=False), encoding="utf-8")
    return rca


def write_research_candidate_v2_report(
    *,
    candidate_pool_path: str | Path,
    previous_catalog_path: str | Path,
    output_path: str | Path,
    candidate_pool_v2_path: str | Path | None = None,
    max_candidates: int = 4,
) -> dict[str, Any]:
    report = build_research_candidate_v2_report(
        json.loads(Path(candidate_pool_path).read_text(encoding="utf-8")),
        json.loads(Path(previous_catalog_path).read_text(encoding="utf-8")),
        max_candidates=max_candidates,
    )
    Path(output_path).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if candidate_pool_v2_path:
        Path(candidate_pool_v2_path).write_text(
            json.dumps(report["candidate_pool_v2"], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    return report


def _row_task_key(row: Mapping[str, Any]) -> str:
    task_ref = row.get("task_ref") if isinstance(row.get("task_ref"), Mapping) else {}
    manifest = str(task_ref.get("manifest") or "")
    task_id = str(task_ref.get("task_id") or "")
    return f"{manifest}::{task_id}" if manifest and task_id else task_id


def _is_effective_skill_row(row: Mapping[str, Any]) -> bool:
    gate = row.get("ablation_gate") if isinstance(row.get("ablation_gate"), Mapping) else {}
    gate_row = row.get("ablation_gate_row") if isinstance(row.get("ablation_gate_row"), Mapping) else {}
    return (
        str(row.get("status") or "") == "PASS"
        and str(gate.get("status") or "") == "PASS"
        and str(gate_row.get("status") or "") == "KEEP"
        and bool(gate_row.get("evidence_path"))
        and bool(gate_row.get("receipt_path"))
        and not bool(gate_row.get("trust_mismatch"))
    )


def _research_candidate_v2_score(row: Mapping[str, Any]) -> tuple[int, int]:
    text = " ".join(str(row.get(key) or "") for key in ("skill_id", "load_when", "path")).lower()
    score = sum(text.count(signal) for signal in RESEARCH_CANDIDATE_V2_STRONG_SIGNALS)
    penalty = sum(text.count(signal) for signal in RESEARCH_CANDIDATE_V2_PLATFORM_ONLY_SIGNALS)
    return score, penalty


def _candidate_v2_decision(row: Mapping[str, Any], decision: str, score: int, penalty: int) -> dict[str, Any]:
    return {
        "skill_id": str(row.get("skill_id") or ""),
        "source_root": str(row.get("source_root") or ""),
        "source_type": str(row.get("source_type") or ""),
        "path": str(row.get("path") or ""),
        "sha256": str(row.get("sha256") or ""),
        "runtime_eligible": bool(row.get("runtime_eligible")),
        "ablation_eligible": bool(row.get("ablation_eligible")),
        "safety_status": str(row.get("safety_status") or ""),
        "source_discipline_score": score,
        "platform_only_penalty": penalty,
        "candidate_decision": decision,
        "semantic_cluster_id": _canonical_skill_id(row),
        "dedup_similarity": 1.0,
        "kept_reason": "source_discipline_signal" if decision == "include_v2" else "",
        "evidence_refs": [str(ref) for ref in row.get("evidence_refs", []) or [] if str(ref)],
    }


def write_skill_promotion_threshold_contract(
    *,
    catalog_path: str | Path,
    promotion_policy_path: str | Path,
    output_path: str | Path,
    rerun_queue_path: str | Path | None = None,
    min_tested_rows_per_skill: int = 30,
    default_min_effective_rate: float = 0.8,
    alternate_min_effective_rate: float = 0.6,
    min_task_buckets_for_alternate: int = 2,
) -> dict[str, Any]:
    catalog = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    promotion_policy = json.loads(Path(promotion_policy_path).read_text(encoding="utf-8"))
    rerun_queue = json.loads(Path(rerun_queue_path).read_text(encoding="utf-8")) if rerun_queue_path else None
    contract = build_skill_promotion_threshold_contract(
        catalog,
        promotion_policy,
        rerun_queue=rerun_queue,
        min_tested_rows_per_skill=min_tested_rows_per_skill,
        default_min_effective_rate=default_min_effective_rate,
        alternate_min_effective_rate=alternate_min_effective_rate,
        min_task_buckets_for_alternate=min_task_buckets_for_alternate,
    )
    Path(output_path).write_text(json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8")
    return contract


def _catalog_row_capability(row: Mapping[str, Any]) -> str:
    direct = str(row.get("capability") or "").strip()
    if direct:
        return direct
    bench_row = row.get("benchmark_row")
    bench_row = bench_row if isinstance(bench_row, Mapping) else {}
    mounts = bench_row.get("skill_mount_contract") or bench_row.get("skill_mount_contracts") or []
    if isinstance(mounts, Mapping):
        mounts = [mounts]
    if isinstance(mounts, list):
        for mount in mounts:
            if not isinstance(mount, Mapping):
                continue
            capability = str(mount.get("capability") or mount.get("capability_mount") or "").strip()
            if capability:
                return capability
    return ""


def _catalog_task_bucket(row: Mapping[str, Any]) -> str:
    task_ref = row.get("task_ref") if isinstance(row.get("task_ref"), Mapping) else {}
    manifest = str(task_ref.get("manifest") or "")
    task_id = str(task_ref.get("task_id") or "")
    if manifest and task_id:
        task = _task_for_ref(manifest, task_id)
        if task:
            bucket = str(task.get("category") or task.get("task_type") or "").strip()
            if bucket:
                return bucket
    return task_id.split("-")[0] if task_id else ""


def build_skill_fit_ablation_plan_from_file(
    path: str | Path,
    *,
    capability: str,
    max_skill_arms: int = 4,
    include_wrong_arm: bool = True,
    explicit_skill_ids: Iterable[str] = (),
) -> dict[str, Any]:
    return build_skill_fit_ablation_plan(
        json.loads(Path(path).read_text(encoding="utf-8")),
        capability=capability,
        max_skill_arms=max_skill_arms,
        include_wrong_arm=include_wrong_arm,
        explicit_skill_ids=explicit_skill_ids,
    )


def write_skill_fit_ablation_plan(
    *,
    candidate_pool_path: str | Path,
    output_path: str | Path,
    capability: str,
    max_skill_arms: int = 4,
    include_wrong_arm: bool = True,
    explicit_skill_ids: Iterable[str] = (),
) -> dict[str, Any]:
    plan = build_skill_fit_ablation_plan_from_file(
        candidate_pool_path,
        capability=capability,
        max_skill_arms=max_skill_arms,
        include_wrong_arm=include_wrong_arm,
        explicit_skill_ids=explicit_skill_ids,
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    return plan


def write_skill_fit_execution_matrix(
    *,
    plan_path: str | Path,
    lane_manifest_path: str | Path,
    lane_id: str,
    output_path: str | Path,
    extra_task_manifests: Iterable[str | Path] = (),
    max_tasks: int = 5,
    model: str = "gemini-3-flash-preview",
    runner: str = "scripts/bench/capability_ab_runner.py",
    skill_status_report: str = "docs/reports/NEXUS_SKILL_STATUS_2026-05-15.json",
) -> dict[str, Any]:
    matrix = build_skill_fit_execution_matrix_from_files(
        plan_path=plan_path,
        lane_manifest_path=lane_manifest_path,
        lane_id=lane_id,
        extra_task_manifests=extra_task_manifests,
        max_tasks=max_tasks,
        model=model,
        runner=runner,
        skill_status_report=skill_status_report,
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(matrix, indent=2, ensure_ascii=False), encoding="utf-8")
    return matrix


# Compatibility exports. New code should import these from the smaller modules.
from nexus.learning.skill_fit_followup import (  # noqa: E402
    build_governance_candidate_v2_report,
    build_research_candidate_v2_report,
    build_research_candidate_v3_report,
    build_research_skill_supply_gap_contract,
    build_research_source_discipline_skill_specs,
    build_governance_taskset_expansion_contract,
    build_governance_mutant_lane_contract,
    build_skill_fit_cost_phase_contract,
    build_skill_fit_redesign_contract,
    build_skill_fit_row_level_rca,
    write_governance_candidate_v2_report,
    write_research_candidate_v2_report,
    write_research_candidate_v3_report,
    write_research_skill_supply_gap_contract,
    write_research_source_discipline_skill_specs,
    write_governance_taskset_expansion_contract,
    write_governance_mutant_lane_contract,
    write_skill_fit_cost_phase_contract,
    write_skill_fit_redesign_contract,
    write_skill_fit_row_level_rca,
)
from nexus.learning.governance_mutants import (  # noqa: E402
    build_governance_mutant_matrix_preflight,
    build_governance_mutant_promotion_gate,
    write_governance_mutant_matrix_preflight,
    write_governance_mutant_promotion_gate,
)
from nexus.learning.skill_fit_promotion import (  # noqa: E402
    build_capability_skill_promotion_policy,
    build_skill_discovery_rerun_queue,
    build_skill_promotion_threshold_contract,
    select_skill_discovery_replay_row_ids,
    write_skill_promotion_threshold_contract,
)
