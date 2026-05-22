from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ZeroTrustV2ReportNode:
    name: str
    builder: Path
    output: Path
    depends_on: tuple[str, ...] = ()
    runtime_update_allowed: bool = False
    public_benchmark_allowed: bool = False


def build_report_dag() -> dict[str, ZeroTrustV2ReportNode]:
    return {
        "curation_backlog": ZeroTrustV2ReportNode(
            name="curation_backlog",
            builder=Path("scripts/ops/build_zero_trust_v2_curation_backlog.py"),
            output=Path("docs/reports/NEXUS_ZERO_TRUST_V2_CURATION_BACKLOG_2026-05-21.json"),
        ),
        "fresh_task_refs": ZeroTrustV2ReportNode(
            name="fresh_task_refs",
            builder=Path("scripts/ops/build_zero_trust_v2_fresh_task_refs.py"),
            output=Path("docs/reports/NEXUS_ZERO_TRUST_V2_FRESH_TASK_REFS_2026-05-21.json"),
            depends_on=("curation_backlog",),
        ),
        "behavior_runner_matrix": ZeroTrustV2ReportNode(
            name="behavior_runner_matrix",
            builder=Path("scripts/ops/build_zero_trust_v2_behavior_runner_matrix.py"),
            output=Path("docs/reports/NEXUS_ZERO_TRUST_V2_BEHAVIOR_RUNNER_MATRIX_2026-05-21.json"),
            depends_on=("curation_backlog", "fresh_task_refs"),
        ),
        "m20_m27_completion": ZeroTrustV2ReportNode(
            name="m20_m27_completion",
            builder=Path("scripts/ops/build_zero_trust_v2_m20_m27_completion.py"),
            output=Path("docs/reports/NEXUS_ZERO_TRUST_V2_M20_M27_COMPLETION_2026-05-21.json"),
            depends_on=("fresh_task_refs", "behavior_runner_matrix"),
        ),
        "m28_m35_execution_plan": ZeroTrustV2ReportNode(
            name="m28_m35_execution_plan",
            builder=Path("scripts/ops/build_zero_trust_v2_m28_m35_execution_plan.py"),
            output=Path("docs/reports/NEXUS_ZERO_TRUST_V2_M28_M35_EXECUTION_PLAN_2026-05-21.json"),
            depends_on=("m20_m27_completion", "behavior_runner_matrix"),
        ),
        "m36_m44_completion": ZeroTrustV2ReportNode(
            name="m36_m44_completion",
            builder=Path("scripts/ops/build_zero_trust_v2_m36_m44_completion.py"),
            output=Path("docs/reports/NEXUS_ZERO_TRUST_V2_M36_M44_COMPLETION_2026-05-21.json"),
            depends_on=("m28_m35_execution_plan",),
        ),
        "m45_m52_completion": ZeroTrustV2ReportNode(
            name="m45_m52_completion",
            builder=Path("scripts/ops/build_zero_trust_v2_m45_m52_completion.py"),
            output=Path("docs/reports/NEXUS_ZERO_TRUST_V2_M45_M52_COMPLETION_2026-05-22.json"),
            depends_on=("m36_m44_completion",),
        ),
        "behavior_evidence": ZeroTrustV2ReportNode(
            name="behavior_evidence",
            builder=Path("scripts/ops/build_zero_trust_v2_behavior_evidence.py"),
            output=Path("docs/reports/NEXUS_ZERO_TRUST_V2_BEHAVIOR_EVIDENCE_2026-05-21.json"),
            depends_on=("curation_backlog", "m45_m52_completion"),
        ),
        "behavior_promotion_report": ZeroTrustV2ReportNode(
            name="behavior_promotion_report",
            builder=Path("scripts/ops/build_zero_trust_v2_behavior_promotion_report.py"),
            output=Path("docs/reports/NEXUS_ZERO_TRUST_V2_BEHAVIOR_PROMOTION_REPORT_2026-05-21.json"),
            depends_on=("behavior_evidence",),
        ),
        "manual_trial": ZeroTrustV2ReportNode(
            name="manual_trial",
            builder=Path("scripts/ops/build_zero_trust_v2_manual_trial.py"),
            output=Path("docs/reports/NEXUS_ZERO_TRUST_V2_MANUAL_APPLY_TRIAL_2026-05-21.json"),
            depends_on=("behavior_promotion_report",),
        ),
        "p0_rollout": ZeroTrustV2ReportNode(
            name="p0_rollout",
            builder=Path("scripts/ops/build_zero_trust_v2_p0_rollout.py"),
            output=Path("docs/reports/NEXUS_ZERO_TRUST_V2_P0_ROLLOUT_2026-05-21.json"),
            depends_on=("manual_trial",),
        ),
        "runtime_apply": ZeroTrustV2ReportNode(
            name="runtime_apply",
            builder=Path("scripts/ops/build_zero_trust_v2_runtime_apply.py"),
            output=Path("docs/reports/NEXUS_ZERO_TRUST_V2_RUNTIME_APPLY_PLAN_2026-05-21.json"),
            depends_on=("m45_m52_completion", "manual_trial", "p0_rollout", "behavior_promotion_report"),
            runtime_update_allowed=True,
        ),
        "unified_mainline": ZeroTrustV2ReportNode(
            name="unified_mainline",
            builder=Path("scripts/ops/build_zero_trust_v2_unified_mainline.py"),
            output=Path("docs/reports/NEXUS_ZERO_TRUST_V2_UNIFIED_MAINLINE_2026-05-22.json"),
            depends_on=("runtime_apply",),
        ),
        "public_claim_gate_review": ZeroTrustV2ReportNode(
            name="public_claim_gate_review",
            builder=Path("scripts/ops/build_zero_trust_v2_public_claim_gate_review.py"),
            output=Path("docs/reports/NEXUS_ZERO_TRUST_V2_PUBLIC_CLAIM_GATE_REVIEW_2026-05-22.json"),
            depends_on=("unified_mainline",),
            public_benchmark_allowed=False,
        ),
    }


def topological_report_order(dag: dict[str, ZeroTrustV2ReportNode]) -> list[str]:
    ordered: list[str] = []
    temporary: set[str] = set()
    permanent: set[str] = set()

    def visit(name: str) -> None:
        if name in permanent:
            return
        if name in temporary:
            raise ValueError(f"cycle detected in Zero Trust V2 report DAG at {name}")
        node = dag.get(name)
        if node is None:
            raise ValueError(f"unknown report node: {name}")
        temporary.add(name)
        for dep in node.depends_on:
            if dep not in dag:
                raise ValueError(f"{name} has unknown dependency: {dep}")
            visit(dep)
        temporary.remove(name)
        permanent.add(name)
        ordered.append(name)

    for name in dag:
        visit(name)
    return ordered
