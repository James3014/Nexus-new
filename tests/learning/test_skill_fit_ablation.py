import json
from pathlib import Path

from nexus.learning.skill_fit_ablation import (
    build_capability_skill_promotion_policy,
    build_governance_candidate_bound_mutant_catalog,
    build_governance_candidate_bound_mutant_matrix,
    build_governance_candidate_v2_report,
    build_governance_mutant_lane_contract,
    build_governance_mutant_live_sealing,
    build_governance_mutant_matrix_preflight,
    build_governance_mutant_promotion_gate,
    build_governance_taskset_expansion_contract,
    build_research_candidate_v2_report,
    build_research_candidate_v3_report,
    build_research_external_candidate_pool,
    build_research_external_ingest_guard,
    build_research_skill_supply_gap_contract,
    build_research_source_discipline_skill_specs,
    build_capability_skill_discovery_scheduler,
    build_skill_fit_cost_phase_contract,
    build_skill_fit_completion_gate,
    build_skill_fit_runtime_policy_apply_gate,
    build_skill_fit_runtime_policy_overlay,
    build_skill_fit_runtime_promotion_review,
    build_skill_fit_redesign_contract,
    build_skill_discovery_rerun_queue,
    build_skill_fit_ablation_plan,
    build_skill_fit_catalog,
    build_skill_fit_execution_matrix,
    build_skill_fit_row_level_rca,
    build_skill_promotion_threshold_contract,
    classify_skill_fit_failure,
    evaluate_skill_fit_ablation_rows,
    select_skill_discovery_replay_row_ids,
    write_capability_skill_promotion_policy,
    write_capability_skill_discovery_scheduler,
    write_skill_fit_completion_gate,
    write_skill_fit_runtime_policy_apply_gate,
    write_skill_fit_runtime_promotion_review,
    write_skill_fit_ablation_plan,
    write_skill_fit_execution_matrix,
    write_skill_promotion_threshold_contract,
)
from nexus.learning.skill_fit_ablation_core import SkillFitCatalogIndex
from nexus.learning.skill_fit_candidate_index import SkillFitCandidateIndex
from nexus.learning.skill_fit_followup import SkillFitRowIndex
from nexus.learning.skill_fit_status import build_skill_fit_status_rollup
from scripts.ops.build_skill_fit_ablation_plan import DEFAULT_EXTRA_TASK_MANIFESTS, resolved_extra_task_manifests
from scripts.ops.run_skill_fit_ablation_matrix import (
    _result_status_from_gate,
    _with_failure_classification,
    build_resume_manifest,
    run_discovery_controller,
    run_matrix,
    run_resume_manifest,
)


def _candidate_pool():
    return {
        "schema": "nexus.fair_skill_candidate_pool.v1",
        "status": "PASS",
        "candidates": [
            {
                "skill_id": "nexus-tdd",
                "source_root": "nexus_repo",
                "source_type": "nexus_local",
                "path": "/repo/.agents/skills/tdd/SKILL.md",
                "sha256": "b" * 64,
                "capability_candidates": ["repair_and_coding"],
                "ablation_eligible": True,
                "runtime_eligible": True,
                "safety_status": "runtime_reviewed",
                "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
            },
            {
                "skill_id": "hermes-debug",
                "source_root": "hermes",
                "source_type": "reference",
                "path": "/Users/jameschen/Workspace/hermes-agent/skills/debug/SKILL.md",
                "sha256": "a" * 64,
                "capability_candidates": ["repair_and_coding"],
                "ablation_eligible": True,
                "runtime_eligible": False,
                "safety_status": "ablation_only",
                "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
            },
            {
                "skill_id": "wrong-skill",
                "source_root": "agents",
                "source_type": "quarantine",
                "path": "/Users/jameschen/.agents/skills/candidate/SKILL.md",
                "sha256": "c" * 64,
                "capability_candidates": ["planning_and_handoff"],
                "ablation_eligible": False,
                "runtime_eligible": False,
                "safety_status": "quarantined",
                "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
            },
        ],
    }


def test_plan_builds_capability_only_anonymous_skill_and_negative_control_arms():
    plan = build_skill_fit_ablation_plan(_candidate_pool(), capability="repair_and_coding", max_skill_arms=2)
    arms = plan["arms"]

    assert plan["status"] == "PASS"
    assert [arm["arm_type"] for arm in arms] == [
        "capability_only",
        "skill_ablation",
        "skill_ablation",
        "wrong_or_quarantined_skill",
    ]
    assert arms[1]["anonymous_label"] == "candidate_001"
    assert {arm["source_root"] for arm in arms if arm["arm_type"] == "skill_ablation"} == {"hermes", "nexus_repo"}
    assert plan["summary"]["runtime_eligible_skill_arm_count"] == 1


def test_discovery_scheduler_plans_capability_local_ablation_without_runtime_promotion():
    scheduler = build_capability_skill_discovery_scheduler(
        _candidate_pool(),
        refresh_plan={
            "status": "SUCCESS",
            "due": [{"topic": "skill:repair_and_coding", "source": "repo:example/skills"}],
        },
        capabilities=["repair_and_coding"],
        max_skill_arms=2,
    )

    item = scheduler["scheduled"][0]
    assert scheduler["status"] == "PASS"
    assert scheduler["runtime_update_allowed"] is False
    assert scheduler["public_benchmark_allowed"] is False
    assert item["capability_id"] == "repair_and_coding"
    assert item["next_action"] == "build_flash30_ablation_matrix"
    assert item["due_source_count"] == 1
    assert item["candidate_arm_count"] == 2
    assert item["negative_control_count"] == 1


def test_discovery_scheduler_monitors_existing_primary_and_keeps_held_lane_separate():
    scheduler = build_capability_skill_discovery_scheduler(
        _candidate_pool(),
        current_catalog={
            "schema": "nexus.sf_final_capability_skill_catalog.v1",
            "capability_skill_catalog": [
                {"capability_id": "repair_and_coding", "primary_default": "nexus-tdd"}
            ],
        },
        capabilities=["repair_and_coding"],
        max_skill_arms=2,
    )

    assert scheduler["scheduled"][0]["next_action"] == "monitor_new_candidates"
    assert scheduler["scheduled"][0]["current_primary_skill_id"] == "nexus-tdd"


def test_discovery_scheduler_reads_v5_capabilities_positive_state():
    scheduler = build_capability_skill_discovery_scheduler(
        _candidate_pool(),
        current_catalog={
            "schema": "nexus.sf_final_capability_skill_catalog.v5",
            "capabilities": {
                "repair_and_coding": {
                    "verdict": "alternate_candidate",
                    "alternate_candidates": ["nexus-tdd"],
                }
            },
        },
        capabilities=["repair_and_coding"],
        max_skill_arms=2,
    )

    assert scheduler["scheduled"][0]["next_action"] == "monitor_new_candidates"
    assert scheduler["scheduled"][0]["current_primary_skill_id"] == "nexus-tdd"


def test_write_discovery_scheduler_outputs_json(tmp_path: Path):
    candidate_path = tmp_path / "candidates.json"
    output_path = tmp_path / "scheduler.json"
    candidate_path.write_text(json.dumps(_candidate_pool()), encoding="utf-8")

    scheduler = write_capability_skill_discovery_scheduler(
        candidate_pool_path=candidate_path,
        output_path=output_path,
        capabilities=["repair_and_coding"],
        max_skill_arms=1,
    )

    assert scheduler["status"] == "PASS"
    assert json.loads(output_path.read_text(encoding="utf-8"))["schema"] == (
        "nexus.sf_capability_skill_discovery_scheduler.v1"
    )


def test_plan_includes_reviewed_runtime_candidate_when_limited():
    plan = build_skill_fit_ablation_plan(_candidate_pool(), capability="repair_and_coding", max_skill_arms=1)
    skill_arms = [arm for arm in plan["arms"] if arm["arm_type"] == "skill_ablation"]

    assert len(skill_arms) == 1
    assert skill_arms[0]["skill_id"] == "nexus-tdd"
    assert skill_arms[0]["runtime_eligible"] is True


def test_plan_uses_external_candidates_after_one_runtime_baseline():
    pool = _candidate_pool()
    pool["candidates"].append(
        {
            "skill_id": "nexus-second-runtime",
            "source_root": "nexus_repo",
            "source_type": "nexus_local",
            "path": "/repo/.agents/skills/second/SKILL.md",
            "sha256": "d" * 64,
            "capability_candidates": ["repair_and_coding"],
            "ablation_eligible": True,
            "runtime_eligible": True,
            "safety_status": "runtime_reviewed",
            "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
        }
    )

    plan = build_skill_fit_ablation_plan(pool, capability="repair_and_coding", max_skill_arms=2)
    skill_arms = [arm for arm in plan["arms"] if arm["arm_type"] == "skill_ablation"]

    assert [arm["runtime_eligible"] for arm in skill_arms] == [True, False]


def test_plan_prefers_named_repair_candidates_over_generic_candidates():
    pool = _candidate_pool()
    pool["candidates"].append(
        {
            "skill_id": "test-driven-development",
            "source_root": "hermes",
            "source_type": "reference",
            "path": "/Users/jameschen/Workspace/hermes-agent/skills/software-development/test-driven-development/SKILL.md",
            "sha256": "e" * 64,
            "capability_candidates": ["repair_and_coding"],
            "ablation_eligible": True,
            "runtime_eligible": False,
            "safety_status": "ablation_only",
            "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
            "load_when": "TDD: enforce RED-GREEN-REFACTOR, tests before code.",
        }
    )

    plan = build_skill_fit_ablation_plan(pool, capability="repair_and_coding", max_skill_arms=2)
    skill_arms = [arm for arm in plan["arms"] if arm["arm_type"] == "skill_ablation"]

    assert [arm["skill_id"] for arm in skill_arms] == ["nexus-tdd", "test-driven-development"]


def test_plan_dedupes_skill_candidates_by_skill_id():
    pool = _candidate_pool()
    pool["candidates"].append(
        {
            "skill_id": "hermes-debug",
            "source_root": "agents",
            "source_type": "reference",
            "path": "/Users/jameschen/.agents/skills/debug/SKILL.md",
            "sha256": "e" * 64,
            "capability_candidates": ["repair_and_coding"],
            "ablation_eligible": True,
            "runtime_eligible": False,
            "safety_status": "ablation_only",
            "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
            "load_when": "Debug Python repair tasks.",
        }
    )

    plan = build_skill_fit_ablation_plan(pool, capability="repair_and_coding", max_skill_arms=3)
    skill_ids = [arm["skill_id"] for arm in plan["arms"] if arm["arm_type"] == "skill_ablation"]

    assert skill_ids.count("hermes-debug") == 1


def test_plan_allows_explicit_found_skill_for_seal_even_when_discovery_blocked():
    pool = {
        "schema": "nexus.fair_skill_candidate_pool.v1",
        "status": "PASS",
        "candidates": [
            {
                "skill_id": "tdd",
                "source_root": "nexus_repo",
                "source_type": "nexus_local",
                "path": "/repo/.agents/skills/tdd/SKILL.md",
                "sha256": "1" * 64,
                "capability_candidates": ["repair_and_coding"],
                "ablation_eligible": True,
                "runtime_eligible": True,
                "safety_status": "runtime_reviewed",
                "load_when": "TDD loop",
            },
            {
                "skill_id": "test-driven-development",
                "source_root": "hermes",
                "source_type": "reference",
                "path": "/repo/skills/test-driven-development/SKILL.md",
                "sha256": "2" * 64,
                "capability_candidates": ["repair_and_coding"],
                "ablation_eligible": True,
                "runtime_eligible": False,
                "safety_status": "ablation_only",
                "load_when": "TDD loop",
            },
        ],
    }

    plan = build_skill_fit_ablation_plan(
        pool,
        capability="repair_and_coding",
        max_skill_arms=1,
        explicit_skill_ids=["tdd"],
        include_wrong_arm=False,
    )

    skill_arms = [arm for arm in plan["arms"] if arm["arm_type"] == "skill_ablation"]
    assert [arm["skill_id"] for arm in skill_arms] == ["tdd"]
    assert skill_arms[0]["runtime_eligible"] is True


def test_plan_dedupes_gstack_prefixed_skill_aliases():
    pool = _candidate_pool()
    pool["candidates"].extend(
        [
            {
                "skill_id": "gstack-investigate",
                "source_root": "agents",
                "source_type": "reference",
                "path": "/Users/jameschen/.agents/skills/gstack-investigate/SKILL.md",
                "sha256": "9" * 64,
                "capability_candidates": ["repair_and_coding"],
                "ablation_eligible": True,
                "runtime_eligible": False,
                "safety_status": "ablation_only",
                "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
                "load_when": "Investigate and debug repair failures.",
            },
            {
                "skill_id": "investigate",
                "source_root": "agents",
                "source_type": "reference",
                "path": "/Users/jameschen/.agents/skills/gstack/.agents/skills/gstack-investigate/SKILL.md",
                "sha256": "a" * 64,
                "capability_candidates": ["repair_and_coding"],
                "ablation_eligible": True,
                "runtime_eligible": False,
                "safety_status": "ablation_only",
                "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
                "load_when": "Investigate and debug repair failures.",
            },
        ]
    )

    plan = build_skill_fit_ablation_plan(pool, capability="repair_and_coding", max_skill_arms=4)
    skill_ids = [arm["skill_id"] for arm in plan["arms"] if arm["arm_type"] == "skill_ablation"]

    assert len({"gstack-investigate", "investigate"}.intersection(skill_ids)) == 1


def test_skill_fit_plan_characterizes_public_candidate_selection_contract():
    pool = _candidate_pool()
    pool["candidates"].extend(
        [
            {
                "skill_id": "runtime-repair",
                "source_root": "nexus_repo",
                "source_type": "nexus_local",
                "path": "/repo/.agents/skills/runtime-repair/SKILL.md",
                "sha256": "1" * 64,
                "capability_candidates": ["repair_and_coding"],
                "ablation_eligible": True,
                "runtime_eligible": True,
                "safety_status": "runtime_reviewed",
                "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
                "load_when": "Repair tasks.",
            },
            {
                "skill_id": "test-driven-development",
                "source_root": "hermes",
                "source_type": "reference",
                "path": "/Users/jameschen/Workspace/hermes-agent/skills/software-development/test-driven-development/SKILL.md",
                "sha256": "2" * 64,
                "capability_candidates": ["repair_and_coding"],
                "ablation_eligible": True,
                "runtime_eligible": False,
                "safety_status": "ablation_only",
                "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
                "load_when": "TDD repair loop.",
            },
            {
                "skill_id": "gstack-investigate",
                "source_root": "agents",
                "source_type": "reference",
                "path": "/Users/jameschen/.agents/skills/gstack-investigate/SKILL.md",
                "sha256": "3" * 64,
                "capability_candidates": ["repair_and_coding"],
                "ablation_eligible": True,
                "runtime_eligible": False,
                "safety_status": "ablation_only",
                "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
                "load_when": "Debug repair failures.",
            },
            {
                "skill_id": "investigate",
                "source_root": "agents",
                "source_type": "reference",
                "path": "/Users/jameschen/.agents/skills/gstack/.agents/skills/gstack-investigate/SKILL.md",
                "sha256": "4" * 64,
                "capability_candidates": ["repair_and_coding"],
                "ablation_eligible": True,
                "runtime_eligible": False,
                "safety_status": "ablation_only",
                "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
                "load_when": "Debug repair failures.",
            },
            {
                "skill_id": "python-debugpy",
                "source_root": "agents",
                "source_type": "reference",
                "path": "/repo/.agents/skills/python-debugpy/SKILL.md",
                "sha256": "5" * 64,
                "capability_candidates": ["repair_and_coding"],
                "ablation_eligible": True,
                "runtime_eligible": False,
                "safety_status": "ablation_only",
                "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
                "load_when": "Debug Python code.",
            },
            {
                "skill_id": "grill-me",
                "source_root": "nexus_repo",
                "source_type": "nexus_local",
                "path": "/repo/.agents/skills/grill-me/SKILL.md",
                "sha256": "6" * 64,
                "capability_candidates": ["repair_and_coding"],
                "ablation_eligible": True,
                "runtime_eligible": True,
                "safety_status": "runtime_reviewed",
                "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
                "load_when": "Interview the user about a plan.",
            },
        ]
    )

    plan = build_skill_fit_ablation_plan(pool, capability="repair_and_coding", max_skill_arms=4)
    skill_arms = [arm for arm in plan["arms"] if arm["arm_type"] == "skill_ablation"]
    skill_ids = [arm["skill_id"] for arm in skill_arms]

    assert skill_ids == ["runtime-repair", "test-driven-development", "gstack-investigate", "hermes-debug"]
    assert [arm["runtime_eligible"] for arm in skill_arms] == [True, False, False, False]
    assert skill_arms[1]["source_root"] == "hermes"
    assert skill_arms[2]["source_root"] == "agents"
    assert "nexus-tdd" not in skill_ids
    assert "investigate" not in skill_ids
    assert "python-debugpy" not in skill_ids
    assert "grill-me" not in skill_ids
    assert plan["summary"]["runtime_eligible_skill_arm_count"] == 1
    assert plan["claim_boundary"][4].startswith("Explicit skill ids are allowed only")


def test_skill_fit_candidate_index_preserves_plan_selection_contract():
    pool = _candidate_pool()
    pool["candidates"].extend(
        [
            {
                "skill_id": "runtime-repair",
                "source_root": "nexus_repo",
                "source_type": "nexus_local",
                "path": "/repo/.agents/skills/runtime-repair/SKILL.md",
                "sha256": "1" * 64,
                "capability_candidates": ["repair_and_coding"],
                "ablation_eligible": True,
                "runtime_eligible": True,
                "safety_status": "runtime_reviewed",
                "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
                "load_when": "Repair tasks.",
            },
            {
                "skill_id": "test-driven-development",
                "source_root": "hermes",
                "source_type": "reference",
                "path": "/Users/jameschen/.hermes/skills/test-driven-development/SKILL.md",
                "sha256": "2" * 64,
                "capability_candidates": ["repair_and_coding"],
                "ablation_eligible": True,
                "runtime_eligible": False,
                "safety_status": "ablation_only",
                "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
                "load_when": "TDD repair loop.",
            },
            {
                "skill_id": "wrong-skill",
                "source_root": "agents",
                "source_type": "quarantine",
                "path": "/skills/wrong/SKILL.md",
                "sha256": "0" * 64,
                "capability_candidates": ["planning_and_handoff"],
                "ablation_eligible": False,
                "runtime_eligible": False,
                "safety_status": "quarantined",
                "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
                "load_when": "Planning only.",
            },
        ]
    )

    index = SkillFitCandidateIndex.from_pool(pool)

    assert [row["skill_id"] for row in index.selected_for_capability("repair_and_coding", 2)] == [
        "runtime-repair",
        "test-driven-development",
    ]
    assert [row["skill_id"] for row in index.explicit_for_capability("repair_and_coding", ["nexus-tdd"])] == [
        "nexus-tdd"
    ]
    assert index.negative_control_for_capability("repair_and_coding")["skill_id"] == "wrong-skill"
    assert index.canonical_skill_id({"skill_id": "gstack-investigate"}) == "investigate"


def test_plan_blocks_timeout_unstable_repair_discovery_candidates():
    pool = _candidate_pool()
    pool["candidates"].append(
        {
            "skill_id": "python-debugpy",
            "source_root": "agents",
            "source_type": "reference",
            "path": "/repo/.agents/skills/python-debugpy/SKILL.md",
            "sha256": "5" * 64,
            "capability_candidates": ["repair_and_coding"],
            "ablation_eligible": True,
            "runtime_eligible": False,
            "safety_status": "ablation_only",
            "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
            "load_when": "Debug Python code with debugpy.",
        }
    )
    pool["candidates"].append(
        {
            "skill_id": "zoom-out",
            "source_root": "nexus_repo",
            "source_type": "nexus_local",
            "path": "/repo/.agents/skills/zoom-out/SKILL.md",
            "sha256": "4" * 64,
            "capability_candidates": ["repair_and_coding"],
            "ablation_eligible": True,
            "runtime_eligible": True,
            "safety_status": "runtime_reviewed",
            "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
            "load_when": "Zoom out on code architecture and repair approach.",
        }
    )
    pool["candidates"].append(
        {
            "skill_id": "improve-codebase-architecture",
            "source_root": "nexus_repo",
            "source_type": "nexus_local",
            "path": "/repo/.agents/skills/improve-codebase-architecture/SKILL.md",
            "sha256": "2" * 64,
            "capability_candidates": ["repair_and_coding"],
            "ablation_eligible": True,
            "runtime_eligible": True,
            "safety_status": "runtime_reviewed",
            "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
            "load_when": "Use architecture guidance for broad codebase changes.",
        }
    )
    pool["candidates"].append(
        {
            "skill_id": "tdd",
            "source_root": "nexus_repo",
            "source_type": "nexus_local",
            "path": "/repo/.agents/skills/tdd/SKILL.md",
            "sha256": "1" * 64,
            "capability_candidates": ["repair_and_coding"],
            "ablation_eligible": True,
            "runtime_eligible": True,
            "safety_status": "runtime_reviewed",
            "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
            "load_when": "Use TDD for coding repairs.",
        }
    )
    pool["candidates"].append(
        {
            "skill_id": "systematic-debugging",
            "source_root": "hermes",
            "source_type": "reference",
            "path": "/Users/jameschen/Workspace/hermes-agent/skills/software-development/systematic-debugging/SKILL.md",
            "sha256": "f" * 64,
            "capability_candidates": ["repair_and_coding"],
            "ablation_eligible": True,
            "runtime_eligible": False,
            "safety_status": "ablation_only",
            "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
            "load_when": "Debug failing repair tasks step by step.",
        }
    )
    pool["candidates"].append(
        {
            "skill_id": "wondelai-clean-code",
            "source_root": "agents",
            "source_type": "reference",
            "path": "/Users/jameschen/.agents/skills/wondelai-clean-code/SKILL.md",
            "sha256": "0" * 64,
            "capability_candidates": ["repair_and_coding"],
            "ablation_eligible": True,
            "runtime_eligible": False,
            "safety_status": "ablation_only",
            "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
            "load_when": "Clean code refactor and repair tasks.",
        }
    )

    plan = build_skill_fit_ablation_plan(pool, capability="repair_and_coding", max_skill_arms=3)
    skill_ids = [arm["skill_id"] for arm in plan["arms"] if arm["arm_type"] == "skill_ablation"]

    assert "systematic-debugging" not in skill_ids
    assert "gstack-codex" not in skill_ids
    assert "improve-codebase-architecture" not in skill_ids
    assert "tdd" not in skill_ids
    assert "workos-live-preview-debug-loop" not in skill_ids
    assert "wondelai-clean-architecture" not in skill_ids
    assert "wondelai-clean-code" not in skill_ids
    assert "wondelai-refactoring-patterns" not in skill_ids
    assert "zoom-out" not in skill_ids
    assert "python-debugpy" not in skill_ids


def test_plan_ignores_capability_candidate_without_repair_signal():
    pool = _candidate_pool()
    pool["candidates"].append(
        {
            "skill_id": "grill-me",
            "source_root": "nexus_repo",
            "source_type": "nexus_local",
            "path": "/repo/.agents/skills/grill-me/SKILL.md",
            "sha256": "3" * 64,
            "capability_candidates": ["repair_and_coding"],
            "ablation_eligible": True,
            "runtime_eligible": True,
            "safety_status": "runtime_reviewed",
            "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
            "load_when": "Interview the user about a plan or design.",
        }
    )

    plan = build_skill_fit_ablation_plan(pool, capability="repair_and_coding", max_skill_arms=3)
    skill_ids = [arm["skill_id"] for arm in plan["arms"] if arm["arm_type"] == "skill_ablation"]

    assert "grill-me" not in skill_ids


def test_plan_ignores_path_only_repair_keyword_matches():
    pool = _candidate_pool()
    pool["candidates"].append(
        {
            "skill_id": "health",
            "source_root": "agents",
            "source_type": "reference",
            "path": "/Users/jameschen/.agents/skills/gstack/.opencode/skills/gstack-health/SKILL.md",
            "sha256": "6" * 64,
            "capability_candidates": ["repair_and_coding"],
            "ablation_eligible": True,
            "runtime_eligible": False,
            "safety_status": "ablation_only",
            "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
            "load_when": "Check system health.",
        }
    )

    plan = build_skill_fit_ablation_plan(pool, capability="repair_and_coding", max_skill_arms=3)
    skill_ids = [arm["skill_id"] for arm in plan["arms"] if arm["arm_type"] == "skill_ablation"]

    assert "health" not in skill_ids


def test_plan_ignores_generic_code_quality_dashboard_skill():
    pool = _candidate_pool()
    pool["candidates"].append(
        {
            "skill_id": "gstack-health",
            "source_root": "agents",
            "source_type": "reference",
            "path": "/Users/jameschen/.agents/skills/gstack-health/SKILL.md",
            "sha256": "7" * 64,
            "capability_candidates": ["repair_and_coding"],
            "ablation_eligible": True,
            "runtime_eligible": False,
            "safety_status": "ablation_only",
            "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
            "load_when": "Code quality dashboard and health score.",
        }
    )

    plan = build_skill_fit_ablation_plan(pool, capability="repair_and_coding", max_skill_arms=3)
    skill_ids = [arm["skill_id"] for arm in plan["arms"] if arm["arm_type"] == "skill_ablation"]

    assert "gstack-health" not in skill_ids


def test_plan_ignores_planning_review_skill_with_architecture_only_signal():
    pool = _candidate_pool()
    pool["candidates"].append(
        {
            "skill_id": "plan-eng-review",
            "source_root": "agents",
            "source_type": "reference",
            "path": "/Users/jameschen/.agents/skills/gstack-plan-eng-review/SKILL.md",
            "sha256": "8" * 64,
            "capability_candidates": ["repair_and_coding"],
            "ablation_eligible": True,
            "runtime_eligible": False,
            "safety_status": "ablation_only",
            "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
            "load_when": "Review architecture, data flow, and edge cases before coding.",
        }
    )

    plan = build_skill_fit_ablation_plan(pool, capability="repair_and_coding", max_skill_arms=3)
    skill_ids = [arm["skill_id"] for arm in plan["arms"] if arm["arm_type"] == "skill_ablation"]

    assert "plan-eng-review" not in skill_ids


def test_gate_rejects_selected_only_positive_skill_claim():
    gate = evaluate_skill_fit_ablation_rows(
        [
            {
                "arm_id": "skill_arm_001",
                "arm_type": "skill_ablation",
                "status": "KEEP",
                "selected": True,
                "injected": False,
                "used": False,
                "evidence_present": False,
                "gate_passed": False,
                "outcome_contributed": False,
                "evidence_path": "",
                "receipt_path": "",
                "trust_mismatch": False,
            }
        ]
    )

    assert gate["status"] == "RETURN"
    assert gate["summary"]["violation_count"] == 2
    assert {violation["reason"] for violation in gate["violations"]} == {
        "selected_only_or_incomplete_chain:injected,used,evidence_present,gate_passed,outcome_contributed",
        "positive_verdict_without_evidence_or_receipt_path",
    }


def test_gate_accepts_receipt_backed_effective_skill_claim():
    gate = evaluate_skill_fit_ablation_rows(
        [
            {
                "arm_id": "skill_arm_001",
                "arm_type": "skill_ablation",
                "status": "KEEP",
                "selected": True,
                "injected": True,
                "used": True,
                "evidence_present": True,
                "gate_passed": True,
                "outcome_contributed": True,
                "evidence_path": "docs/reports/skill-row.json",
                "receipt_path": ".nexus/reports/receipt.json",
                "trust_mismatch": False,
            }
        ]
    )

    assert gate["status"] == "PASS"
    assert gate["summary"]["effective_count"] == 1


def test_gate_blocks_wrong_or_quarantined_skill_adoption():
    gate = evaluate_skill_fit_ablation_rows(
        [
            {
                "arm_id": "wrong",
                "arm_type": "wrong_or_quarantined_skill",
                "status": "PASS",
                "selected": True,
                "injected": True,
                "used": True,
                "evidence_present": True,
                "gate_passed": True,
                "outcome_contributed": True,
                "evidence_path": "docs/reports/wrong.json",
                "receipt_path": ".nexus/reports/wrong.json",
                "trust_mismatch": False,
            }
        ]
    )

    assert gate["status"] == "RETURN"
    assert gate["violations"] == [{"arm_id": "wrong", "reason": "wrong_or_quarantined_skill_not_blocked"}]


def test_write_skill_fit_ablation_plan_outputs_json(tmp_path: Path):
    pool_path = tmp_path / "pool.json"
    output_path = tmp_path / "plan.json"
    pool_path.write_text(json.dumps(_candidate_pool()), encoding="utf-8")

    plan = write_skill_fit_ablation_plan(
        candidate_pool_path=pool_path,
        output_path=output_path,
        capability="repair_and_coding",
        max_skill_arms=1,
    )

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved == plan
    assert saved["schema"] == "nexus.skill_fit_ablation_plan.v1"
    assert saved["summary"]["skill_arm_count"] == 1


def test_execution_matrix_expands_tasks_by_arms_without_claiming_value():
    plan = build_skill_fit_ablation_plan(_candidate_pool(), capability="repair_and_coding", max_skill_arms=1)
    matrix = build_skill_fit_execution_matrix(
        plan,
        task_refs=[
            {"manifest": "scripts/bench/public_benchmark_nexus_value_v1.json", "task_id": "nexus-value-repair-001"},
            {"manifest": "scripts/bench/public_benchmark_nexus_value_v1.json", "task_id": "nexus-value-repair-002"},
        ],
        max_tasks=2,
    )

    assert matrix["status"] == "PASS"
    assert matrix["summary"]["task_count"] == 2
    assert matrix["summary"]["arm_count"] == 3
    assert matrix["summary"]["row_count"] == 6
    assert [row["arm_type"] for row in matrix["rows"][:2]] == ["capability_only", "capability_only"]
    assert {row["task_ref"]["task_id"] for row in matrix["rows"][:2]} == {
        "nexus-value-repair-001",
        "nexus-value-repair-002",
    }
    capability_only = [row for row in matrix["rows"] if row["arm_type"] == "capability_only"]
    skill_rows = [row for row in matrix["rows"] if row["arm_type"] == "skill_ablation"]
    wrong_rows = [row for row in matrix["rows"] if row["arm_type"] == "wrong_or_quarantined_skill"]
    assert all(row["skill_mount_requests"] == [] for row in capability_only)
    assert all(row["skill_mount_requests"] == ["nexus-tdd"] for row in skill_rows)
    assert all(row["source_root"] == "nexus_repo" for row in skill_rows)
    assert all(row["runtime_eligible"] is True for row in skill_rows)
    assert all(row["skill_mount_requests"] == ["wrong-skill"] for row in wrong_rows)
    assert all("--task-id-filter" in row["runner_args"] for row in matrix["rows"])
    assert all("--timeout-sec" in row["runner_args"] for row in matrix["rows"])
    assert all("--enable-autoreason-executor" in row["runner_args"] for row in matrix["rows"])
    assert all(row["runner_env"]["NEXUS_VALUE_HIDDEN_VERIFIER"] == "1" for row in matrix["rows"])
    assert all(row["runner_env"]["NEXUS_BENCH_SKILL_STATUS_REPORT"] for row in matrix["rows"])
    assert all(row["runner_env"]["NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS"] == "1" for row in skill_rows)
    assert all(row["runner_env"]["NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS"] == "0" for row in wrong_rows)
    assert "not delivery or skill value evidence" in matrix["claim_boundary"][0]


def test_execution_matrix_characterizes_public_row_shape_for_all_arm_types():
    plan = build_skill_fit_ablation_plan(_candidate_pool(), capability="repair_and_coding", max_skill_arms=1)
    matrix = build_skill_fit_execution_matrix(
        plan,
        task_refs=[
            {"manifest": "scripts/bench/public_benchmark_nexus_value_v1.json", "task_id": "nexus-value-repair-001"}
        ],
        max_tasks=1,
        model="gemini-test-model",
        runner="scripts/bench/capability_ab_runner.py",
        skill_status_report="docs/reports/skill-status.json",
    )

    rows = {row["arm_type"]: row for row in matrix["rows"]}
    assert tuple(rows) == ("capability_only", "skill_ablation", "wrong_or_quarantined_skill")
    assert matrix["summary"]["rows_by_capability"] == {"repair_and_coding": 3}
    assert matrix["summary"]["expected_row_count"] == 3

    for row in rows.values():
        assert row["row_id"] == f"repair_and_coding::nexus-value-repair-001::{row['arm_id']}"
        assert row["task_ref"] == {
            "manifest": "scripts/bench/public_benchmark_nexus_value_v1.json",
            "task_id": "nexus-value-repair-001",
        }
        assert row["model"] == "gemini-test-model"
        assert row["capability"] == "repair_and_coding"
        assert row["gate_requirements"] == [
            "selected",
            "injected",
            "used",
            "evidence_present",
            "gate_passed",
            "outcome_contributed",
        ]
        assert row["runner_env"]["NEXUS_VALUE_HIDDEN_VERIFIER"] == "1"
        assert row["runner_env"]["NEXUS_DIRECT_GEMINI_MODEL"] == "gemini-test-model"
        assert row["runner_env"]["NEXUS_BENCH_SKILL_STATUS_REPORT"] == "docs/reports/skill-status.json"
        assert json.loads(row["runner_env"]["NEXUS_BENCH_SKILL_MOUNT_REQUESTS"]) == row["skill_mount_requests"]
        assert row["runner_args"][:4] == ["uv", "run", "python", "scripts/bench/capability_ab_runner.py"]
        assert row["runner_args"][row["runner_args"].index("--task-id-filter") + 1] == "nexus-value-repair-001"
        assert row["runner_args"][row["runner_args"].index("--gemini-model") + 1] == "gemini-test-model"
        assert "--evidence-bundle" in row["runner_args"]

    assert rows["capability_only"]["skill_mount_requests"] == []
    assert rows["capability_only"]["expected_outcome"] == "baseline_without_skill_mount"
    assert rows["capability_only"]["runner_env"]["NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS"] == "0"

    assert rows["skill_ablation"]["skill_mount_requests"] == ["nexus-tdd"]
    assert rows["skill_ablation"]["source_root"] == "nexus_repo"
    assert rows["skill_ablation"]["runtime_eligible"] is True
    assert rows["skill_ablation"]["expected_outcome"] == "must_prove_selected_injected_used_evidence_gate_outcome"
    assert rows["skill_ablation"]["runner_env"]["NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS"] == "1"

    assert rows["wrong_or_quarantined_skill"]["skill_mount_requests"] == ["wrong-skill"]
    assert rows["wrong_or_quarantined_skill"]["expected_outcome"] == "must_return_or_block"
    assert rows["wrong_or_quarantined_skill"]["runner_env"]["NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS"] == "0"


def test_write_execution_matrix_from_lane_manifest(tmp_path: Path):
    pool_path = tmp_path / "pool.json"
    plan_path = tmp_path / "plan.json"
    lane_path = tmp_path / "lanes.json"
    matrix_path = tmp_path / "matrix.json"
    pool_path.write_text(json.dumps(_candidate_pool()), encoding="utf-8")
    write_skill_fit_ablation_plan(
        candidate_pool_path=pool_path,
        output_path=plan_path,
        capability="repair_and_coding",
        max_skill_arms=1,
    )
    lane_path.write_text(
        json.dumps(
            {
                "lanes": [
                    {
                        "id": "cost_efficiency",
                        "task_refs": [
                            {
                                "manifest": "scripts/bench/public_benchmark_nexus_value_v1.json",
                                    "task_id": "nexus-value-context-001",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    matrix = write_skill_fit_execution_matrix(
        plan_path=plan_path,
        lane_manifest_path=lane_path,
        lane_id="cost_efficiency",
        output_path=matrix_path,
        max_tasks=1,
    )

    saved = json.loads(matrix_path.read_text(encoding="utf-8"))
    assert saved == matrix
    assert saved["schema"] == "nexus.skill_fit_execution_matrix.v1"
    assert saved["summary"]["row_count"] == 3


def test_write_execution_matrix_filters_non_matching_capability_tasks(tmp_path: Path):
    pool_path = tmp_path / "pool.json"
    plan_path = tmp_path / "plan.json"
    task_manifest = tmp_path / "tasks.json"
    lane_path = tmp_path / "lanes.json"
    matrix_path = tmp_path / "matrix.json"
    pool_path.write_text(json.dumps(_candidate_pool()), encoding="utf-8")
    write_skill_fit_ablation_plan(
        candidate_pool_path=pool_path,
        output_path=plan_path,
        capability="repair_and_coding",
        max_skill_arms=1,
    )
    task_manifest.write_text(
        json.dumps(
            {
                "tasks": [
                    {"id": "repair", "expected_capabilities": ["hyper", "delivery_gate"]},
                    {"id": "belief", "expected_capabilities": ["belief"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    lane_path.write_text(
        json.dumps(
            {
                "lanes": [
                    {
                        "id": "mixed",
                        "task_refs": [
                            {"manifest": str(task_manifest), "task_id": "repair"},
                            {"manifest": str(task_manifest), "task_id": "belief"},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    matrix = write_skill_fit_execution_matrix(
        plan_path=plan_path,
        lane_manifest_path=lane_path,
        lane_id="mixed",
        output_path=matrix_path,
        max_tasks=5,
    )

    assert {row["task_ref"]["task_id"] for row in matrix["rows"]} == {"repair"}


def test_write_execution_matrix_accepts_skill_status_report_override(tmp_path: Path):
    pool_path = tmp_path / "pool.json"
    plan_path = tmp_path / "plan.json"
    lane_path = tmp_path / "lanes.json"
    matrix_path = tmp_path / "matrix.json"
    pool_path.write_text(json.dumps(_candidate_pool()), encoding="utf-8")
    write_skill_fit_ablation_plan(
        candidate_pool_path=pool_path,
        output_path=plan_path,
        capability="repair_and_coding",
        max_skill_arms=1,
    )
    lane_path.write_text(
        json.dumps(
            {
                "lanes": [
                    {
                        "id": "cost_efficiency",
                        "task_refs": [
                            {
                                "manifest": "scripts/bench/public_benchmark_nexus_value_v1.json",
                                "task_id": "nexus-value-context-001",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    matrix = write_skill_fit_execution_matrix(
        plan_path=plan_path,
        lane_manifest_path=lane_path,
        lane_id="cost_efficiency",
        output_path=matrix_path,
        max_tasks=1,
        skill_status_report="docs/reports/NEXUS_SKILL_STATUS_SF_RESEARCH_2026-05-18.json",
    )

    assert {
        row["runner_env"]["NEXUS_BENCH_SKILL_STATUS_REPORT"]
        for row in matrix["rows"]
    } == {"docs/reports/NEXUS_SKILL_STATUS_SF_RESEARCH_2026-05-18.json"}


def test_governance_skill_fit_plan_and_matrix_are_capability_specific():
    pool = _candidate_pool()
    pool["candidates"].append(
        {
            "skill_id": "nexus-root-cause-probe",
            "source_root": "nexus_repo",
            "source_type": "nexus_local",
            "path": "/repo/.agents/skills/nexus-root-cause-probe/SKILL.md",
            "sha256": "1" * 64,
            "capability_candidates": ["governance_and_trust"],
            "ablation_eligible": True,
            "runtime_eligible": True,
            "safety_status": "runtime_reviewed",
            "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
            "load_when": "Investigate trust, evidence, governance, and failclosed claim gates.",
        }
    )

    plan = build_skill_fit_ablation_plan(pool, capability="governance_and_trust", max_skill_arms=1)
    matrix = build_skill_fit_execution_matrix(
        plan,
        task_refs=[{"manifest": "tasks.json", "task_id": "gov-task"}],
        max_tasks=1,
    )

    assert plan["status"] == "PASS"
    assert matrix["status"] == "PASS"
    assert matrix["summary"]["rows_by_capability"] == {"governance_and_trust": 3}
    assert {row["capability"] for row in matrix["rows"]} == {"governance_and_trust"}


def test_research_skill_fit_plan_and_matrix_are_capability_specific():
    pool = _candidate_pool()
    pool["candidates"].append(
        {
            "skill_id": "arxiv",
            "source_root": "hermes",
            "source_type": "reference",
            "path": "/Users/jameschen/.hermes/skills/research/arxiv/SKILL.md",
            "sha256": "2" * 64,
            "capability_candidates": ["research_and_source_discipline"],
            "ablation_eligible": True,
            "runtime_eligible": False,
            "safety_status": "ablation_only",
            "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
            "load_when": "Use arxiv research sources and citations for retrieval evidence.",
        }
    )

    plan = build_skill_fit_ablation_plan(pool, capability="research_and_source_discipline", max_skill_arms=1)
    matrix = build_skill_fit_execution_matrix(
        plan,
        task_refs=[{"manifest": "tasks.json", "task_id": "research-task"}],
        max_tasks=1,
    )

    assert plan["status"] == "PASS"
    assert matrix["status"] == "PASS"
    assert matrix["summary"]["rows_by_capability"] == {"research_and_source_discipline": 3}
    assert {row["capability"] for row in matrix["rows"]} == {"research_and_source_discipline"}


def test_write_execution_matrix_includes_extra_public_manifests_with_capability_filter(tmp_path: Path):
    pool_path = tmp_path / "pool.json"
    plan_path = tmp_path / "plan.json"
    lane_path = tmp_path / "lanes.json"
    extra_path = tmp_path / "extra_tasks.json"
    matrix_path = tmp_path / "matrix.json"
    pool_path.write_text(json.dumps(_candidate_pool()), encoding="utf-8")
    write_skill_fit_ablation_plan(
        candidate_pool_path=pool_path,
        output_path=plan_path,
        capability="repair_and_coding",
        max_skill_arms=1,
    )
    lane_path.write_text(json.dumps({"lanes": [{"id": "empty", "task_refs": []}]}), encoding="utf-8")
    extra_path.write_text(
        json.dumps(
            {
                "tasks": [
                    {"id": "pub-bug", "category": "bugfix"},
                    {"id": "pub-bug-002", "category": "bugfix"},
                    {"id": "pub-bug-004", "category": "bugfix"},
                    {"id": "pub-test-002", "category": "test_repair"},
                    {"id": "pub-ref", "category": "refactor"},
                    {"id": "local-bug", "category": "bugfix", "repo_kind": "nexus_internal", "repo_ref": "current-worktree"},
                    {"id": "external-bug", "category": "bugfix", "repo_kind": "external", "repo_ref": "abc123"},
                    {"id": "pub-ops", "category": "ops_research"},
                ]
            }
        ),
        encoding="utf-8",
    )

    matrix = write_skill_fit_execution_matrix(
        plan_path=plan_path,
        lane_manifest_path=lane_path,
        lane_id="empty",
        output_path=matrix_path,
        extra_task_manifests=[extra_path],
        max_tasks=10,
    )

    assert {row["task_ref"]["task_id"] for row in matrix["rows"]} == {"pub-bug", "pub-ref"}
    assert matrix["summary"]["task_count"] == 2


def test_research_execution_matrix_requires_expected_research_capability(tmp_path: Path):
    pool_path = tmp_path / "pool.json"
    plan_path = tmp_path / "plan.json"
    lane_path = tmp_path / "lanes.json"
    extra_path = tmp_path / "research_tasks.json"
    matrix_path = tmp_path / "matrix.json"
    pool = _candidate_pool()
    pool["candidates"].append(
        {
            "skill_id": "source-discipline",
            "source_root": "nexus_repo",
            "source_type": "reference",
            "path": ".agents/skills/source-discipline/SKILL.md",
            "sha256": "3" * 64,
            "capability_candidates": ["research_and_source_discipline"],
            "ablation_eligible": True,
            "runtime_eligible": False,
            "safety_status": "ablation_only",
            "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
            "load_when": "Use source validation and citation evidence.",
        }
    )
    pool_path.write_text(json.dumps(pool), encoding="utf-8")
    write_skill_fit_ablation_plan(
        candidate_pool_path=pool_path,
        output_path=plan_path,
        capability="research_and_source_discipline",
        max_skill_arms=1,
    )
    lane_path.write_text(json.dumps({"lanes": [{"id": "empty", "task_refs": []}]}), encoding="utf-8")
    extra_path.write_text(
        json.dumps(
            {
                "tasks": [
                    {"id": "generic-docs", "category": "docs_code_sync", "task_desc": "Update docs with source wording."},
                    {
                        "id": "route-oracle-research",
                        "category": "docs_code_sync",
                        "expected_capabilities": ["research"],
                        "task_desc": "Accept cited source evidence only when supported.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    matrix = write_skill_fit_execution_matrix(
        plan_path=plan_path,
        lane_manifest_path=lane_path,
        lane_id="empty",
        output_path=matrix_path,
        extra_task_manifests=[extra_path],
        max_tasks=10,
    )

    assert {row["task_ref"]["task_id"] for row in matrix["rows"]} == {"route-oracle-research"}
    assert matrix["summary"]["task_count"] == 1


def test_governance_execution_matrix_requires_expected_governance_capability(tmp_path: Path):
    pool_path = tmp_path / "pool.json"
    plan_path = tmp_path / "plan.json"
    lane_path = tmp_path / "lanes.json"
    extra_path = tmp_path / "governance_tasks.json"
    matrix_path = tmp_path / "matrix.json"
    pool = _candidate_pool()
    pool["candidates"].append(
        {
            "skill_id": "evidence-gate",
            "source_root": "nexus_repo",
            "source_type": "curated",
            "path": ".agents/skills/evidence-gate/SKILL.md",
            "sha256": "4" * 64,
            "capability_candidates": ["governance_and_trust"],
            "ablation_eligible": True,
            "runtime_eligible": True,
            "safety_status": "runtime_reviewed",
            "evidence_refs": ["skill_status_report:nexus.skill_status.v1"],
            "load_when": "Use claim gate and evidence governance checks.",
        }
    )
    pool_path.write_text(json.dumps(pool), encoding="utf-8")
    write_skill_fit_ablation_plan(
        candidate_pool_path=pool_path,
        output_path=plan_path,
        capability="governance_and_trust",
        max_skill_arms=1,
    )
    lane_path.write_text(json.dumps({"lanes": [{"id": "empty", "task_refs": []}]}), encoding="utf-8")
    extra_path.write_text(
        json.dumps(
            {
                "tasks": [
                    {"id": "generic-evidence", "category": "feature", "task_desc": "Fix evidence wording."},
                    {
                        "id": "claim-gate",
                        "category": "feature",
                        "expected_capabilities": ["claim_gate"],
                        "task_desc": "Reject unsupported claims.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    matrix = write_skill_fit_execution_matrix(
        plan_path=plan_path,
        lane_manifest_path=lane_path,
        lane_id="empty",
        output_path=matrix_path,
        extra_task_manifests=[extra_path],
        max_tasks=10,
    )

    assert {row["task_ref"]["task_id"] for row in matrix["rows"]} == {"claim-gate"}
    assert matrix["summary"]["task_count"] == 1


def test_default_skill_fit_extra_manifests_exclude_non_public_real_world_tasks():
    assert "scripts/bench/real_world_tasks_v1.json" not in DEFAULT_EXTRA_TASK_MANIFESTS


def test_explicit_skill_fit_extra_manifests_replace_cli_defaults():
    assert resolved_extra_task_manifests(["custom.json"]) == ["custom.json"]


def test_skill_fit_extra_manifests_fall_back_to_defaults_when_unspecified():
    assert resolved_extra_task_manifests(None) == list(DEFAULT_EXTRA_TASK_MANIFESTS)


def test_write_execution_matrix_dedupes_lane_and_extra_task_refs(tmp_path: Path):
    pool_path = tmp_path / "pool.json"
    plan_path = tmp_path / "plan.json"
    task_manifest = tmp_path / "tasks.json"
    lane_path = tmp_path / "lanes.json"
    matrix_path = tmp_path / "matrix.json"
    pool_path.write_text(json.dumps(_candidate_pool()), encoding="utf-8")
    write_skill_fit_ablation_plan(
        candidate_pool_path=pool_path,
        output_path=plan_path,
        capability="repair_and_coding",
        max_skill_arms=1,
    )
    task_manifest.write_text(json.dumps({"tasks": [{"id": "repair", "expected_capabilities": ["hyper"]}]}), encoding="utf-8")
    lane_path.write_text(
        json.dumps(
            {
                "lanes": [
                    {
                        "id": "mixed",
                        "task_refs": [
                            {"manifest": str(task_manifest), "task_id": "repair"},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    matrix = write_skill_fit_execution_matrix(
        plan_path=plan_path,
        lane_manifest_path=lane_path,
        lane_id="mixed",
        output_path=matrix_path,
        extra_task_manifests=[task_manifest],
        max_tasks=10,
    )

    assert [row["task_ref"]["task_id"] for row in matrix["rows"] if row["arm_type"] == "capability_only"] == ["repair"]


def test_matrix_runner_preflight_fail_fast_with_stub_runner(tmp_path: Path):
    stub = tmp_path / "stub_runner.py"
    stub.write_text(
        "import argparse, json\n"
        "from pathlib import Path\n"
        "parser=argparse.ArgumentParser(); parser.add_argument('--output-dir'); parser.add_argument('--preflight-only', action='store_true')\n"
        "args, _ = parser.parse_known_args(); Path(args.output_dir).mkdir(parents=True, exist_ok=True)\n"
        "Path(args.output_dir, 'benchmark_preflight.json').write_text(json.dumps({'status':'PASS','failures':[]}), encoding='utf-8')\n",
        encoding="utf-8",
    )
    matrix = {
        "rows": [
            {
                "row_id": "task::capability_only",
                "arm_id": "capability_only",
                "arm_type": "capability_only",
                "task_ref": {"manifest": "m.json", "task_id": "task"},
                "runner_env": {},
                "runner_args": ["python3", str(stub)],
            }
        ]
    }
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")

    summary = run_matrix(matrix_path=matrix_path, output_root=tmp_path / "out", preflight_only=True)

    assert summary["status"] == "PASS"
    assert summary["summary"]["completed_rows"] == 1
    assert (tmp_path / "out" / "preflight_summary.json").exists()


def test_matrix_runner_filters_specific_row_ids_with_stub_runner(tmp_path: Path):
    stub = tmp_path / "stub_runner.py"
    stub.write_text(
        "import argparse, json\n"
        "from pathlib import Path\n"
        "parser=argparse.ArgumentParser(); parser.add_argument('--output-dir'); parser.add_argument('--preflight-only', action='store_true')\n"
        "args, _ = parser.parse_known_args(); Path(args.output_dir).mkdir(parents=True, exist_ok=True)\n"
        "Path(args.output_dir, 'benchmark_preflight.json').write_text(json.dumps({'status':'PASS','failures':[]}), encoding='utf-8')\n",
        encoding="utf-8",
    )
    matrix = {
        "rows": [
            {"row_id": "task::a", "arm_type": "capability_only", "runner_env": {}, "runner_args": ["python3", str(stub)]},
            {"row_id": "task::b", "arm_type": "capability_only", "runner_env": {}, "runner_args": ["python3", str(stub)]},
        ]
    }
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")

    summary = run_matrix(
        matrix_path=matrix_path,
        output_root=tmp_path / "out",
        preflight_only=True,
        row_id_filter="task::b",
    )

    assert summary["summary"]["planned_rows"] == 1
    assert summary["results"][0]["row_id"] == "task::b"
    checkpoint = json.loads((tmp_path / "out" / "checkpoint_summary.json").read_text(encoding="utf-8"))
    assert checkpoint["schema"] == "nexus.skill_fit_ablation_matrix_checkpoint.v1"
    assert checkpoint["summary"]["completed_rows"] == 1
    assert checkpoint["last_result"]["row_id"] == "task::b"


def test_matrix_runner_filters_arm_types_with_stub_runner(tmp_path: Path):
    stub = tmp_path / "stub_runner.py"
    stub.write_text(
        "import argparse, json\n"
        "from pathlib import Path\n"
        "parser=argparse.ArgumentParser(); parser.add_argument('--output-dir'); parser.add_argument('--preflight-only', action='store_true')\n"
        "args, _ = parser.parse_known_args(); Path(args.output_dir).mkdir(parents=True, exist_ok=True)\n"
        "Path(args.output_dir, 'benchmark_preflight.json').write_text(json.dumps({'status':'PASS','failures':[]}), encoding='utf-8')\n",
        encoding="utf-8",
    )
    matrix = {
        "rows": [
            {"row_id": "task::base", "arm_type": "capability_only", "runner_env": {}, "runner_args": ["python3", str(stub)]},
            {"row_id": "task::skill", "arm_type": "skill_ablation", "runner_env": {}, "runner_args": ["python3", str(stub)]},
            {"row_id": "task::negative", "arm_type": "wrong_or_quarantined_skill", "runner_env": {}, "runner_args": ["python3", str(stub)]},
        ]
    }
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")

    summary = run_matrix(
        matrix_path=matrix_path,
        output_root=tmp_path / "out",
        preflight_only=True,
        arm_type_filter="skill_ablation,wrong_or_quarantined_skill",
    )

    assert summary["summary"]["planned_rows"] == 2
    assert [row["row_id"] for row in summary["results"]] == ["task::skill", "task::negative"]


def test_select_skill_discovery_replay_row_ids_from_queue():
    matrix = {
        "rows": [
            {"row_id": "base", "capability": "repair_and_coding", "skill_id": "", "arm_type": "capability_only"},
            {"row_id": "skill-a-1", "capability": "repair_and_coding", "skill_id": "a", "arm_type": "skill_ablation"},
            {"row_id": "skill-b-1", "capability": "repair_and_coding", "skill_id": "b", "arm_type": "skill_ablation"},
            {"row_id": "wrong-a", "capability": "repair_and_coding", "skill_id": "a", "arm_type": "wrong_or_quarantined_skill"},
        ]
    }
    queue = {
        "queue": [
            {"capability": "repair_and_coding", "skill_id": "a", "verdict": "needs_more_data"},
        ]
    }

    assert select_skill_discovery_replay_row_ids(matrix, queue) == ["skill-a-1"]


def test_discovery_controller_runs_capability_sweep_with_stub_runner(tmp_path: Path):
    stub = tmp_path / "stub_runner.py"
    stub.write_text(
        "import argparse, json\n"
        "from pathlib import Path\n"
        "parser=argparse.ArgumentParser(); parser.add_argument('--output-dir'); parser.add_argument('--preflight-only', action='store_true')\n"
        "args, _ = parser.parse_known_args(); Path(args.output_dir).mkdir(parents=True, exist_ok=True)\n"
        "Path(args.output_dir, 'benchmark_preflight.json').write_text(json.dumps({'status':'PASS','failures':[]}), encoding='utf-8')\n",
        encoding="utf-8",
    )
    matrix = {
        "rows": [
            {"row_id": "task::base", "arm_type": "capability_only", "runner_env": {}, "runner_args": ["python3", str(stub)]},
            {"row_id": "task::skill", "arm_type": "skill_ablation", "runner_env": {}, "runner_args": ["python3", str(stub)]},
        ]
    }
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")

    summary = run_discovery_controller(
        phase="capability_sweep",
        matrix_path=matrix_path,
        output_root=tmp_path / "out",
        preflight_only=True,
    )

    assert summary["controller"]["phase"] == "capability_sweep"
    assert summary["summary"]["planned_rows"] == 1
    assert summary["results"][0]["row_id"] == "task::base"


def test_discovery_controller_runs_targeted_replay_from_queue(tmp_path: Path):
    stub = tmp_path / "stub_runner.py"
    stub.write_text(
        "import argparse, json\n"
        "from pathlib import Path\n"
        "parser=argparse.ArgumentParser(); parser.add_argument('--output-dir'); parser.add_argument('--preflight-only', action='store_true')\n"
        "args, _ = parser.parse_known_args(); Path(args.output_dir).mkdir(parents=True, exist_ok=True)\n"
        "Path(args.output_dir, 'benchmark_preflight.json').write_text(json.dumps({'status':'PASS','failures':[]}), encoding='utf-8')\n",
        encoding="utf-8",
    )
    matrix = {
        "rows": [
            {
                "row_id": "task::base",
                "capability": "repair_and_coding",
                "skill_id": "",
                "arm_type": "capability_only",
                "runner_env": {},
                "runner_args": ["python3", str(stub)],
            },
            {
                "row_id": "task::skill-a",
                "capability": "repair_and_coding",
                "skill_id": "a",
                "arm_type": "skill_ablation",
                "runner_env": {},
                "runner_args": ["python3", str(stub)],
            },
            {
                "row_id": "task::skill-b",
                "capability": "repair_and_coding",
                "skill_id": "b",
                "arm_type": "skill_ablation",
                "runner_env": {},
                "runner_args": ["python3", str(stub)],
            },
        ]
    }
    queue = {"queue": [{"capability": "repair_and_coding", "skill_id": "b", "verdict": "needs_more_data"}]}
    matrix_path = tmp_path / "matrix.json"
    queue_path = tmp_path / "queue.json"
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")
    queue_path.write_text(json.dumps(queue), encoding="utf-8")

    summary = run_discovery_controller(
        phase="targeted_replay",
        matrix_path=matrix_path,
        output_root=tmp_path / "out",
        preflight_only=True,
        rerun_queue_path=queue_path,
    )

    assert summary["controller"]["phase"] == "targeted_replay"
    assert summary["summary"]["planned_rows"] == 1
    assert summary["results"][0]["row_id"] == "task::skill-b"


def test_matrix_runner_returns_on_empty_selection(tmp_path: Path):
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(json.dumps({"rows": []}), encoding="utf-8")

    summary = run_matrix(matrix_path=matrix_path, output_root=tmp_path / "out", preflight_only=True)

    assert summary["status"] == "RETURN"
    assert summary["summary"]["planned_rows"] == 0
    assert summary["failure_classification"]["kind"] == "empty_matrix_selection"


def test_resume_manifest_reports_completed_and_remaining_rows(tmp_path: Path):
    matrix = {
        "rows": [
            {"row_id": "task::done", "arm_type": "capability_only"},
            {"row_id": "task::todo", "arm_type": "skill_ablation"},
        ]
    }
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")
    done_dir = tmp_path / "out" / "task_done"
    done_dir.mkdir(parents=True)
    (done_dir / "with_nexus_stub.jsonl").write_text('{"status":"SUCCESS"}\n', encoding="utf-8")

    manifest = build_resume_manifest(
        matrix_path=matrix_path,
        output_root=tmp_path / "out",
        abort_reason="quota_exhausted",
    )

    assert manifest["status"] == "RESUME_REQUIRED"
    assert manifest["summary"] == {"planned_rows": 2, "completed_rows": 1, "remaining_rows": 1}
    assert manifest["last_completed_row_id"] == "task::done"
    assert manifest["next_row_id"] == "task::todo"
    assert manifest["abort_reason"] == "quota_exhausted"


def test_run_resume_manifest_merges_existing_and_new_rows(tmp_path: Path):
    stub = tmp_path / "stub_runner.py"
    stub.write_text(
        "import argparse, json\n"
        "from pathlib import Path\n"
        "parser=argparse.ArgumentParser(); parser.add_argument('--output-dir')\n"
        "args, _ = parser.parse_known_args(); out=Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)\n"
        "row={'status':'SUCCESS','skill_mount_contract_status':'PASS','skill_mount_contract':[{'skill_id':'s'}]}\n"
        "Path(out, 'with_nexus_stub.jsonl').write_text(json.dumps(row)+'\\n', encoding='utf-8')\n",
        encoding="utf-8",
    )
    matrix = {
        "rows": [
            {
                "row_id": "task::done",
                "arm_id": "done",
                "arm_type": "skill_ablation",
                "skill_id": "s",
                "runtime_eligible": True,
                "runner_env": {},
                "runner_args": ["python3", str(stub)],
            },
            {
                "row_id": "task::todo",
                "arm_id": "todo",
                "arm_type": "skill_ablation",
                "skill_id": "s",
                "runtime_eligible": True,
                "runner_env": {},
                "runner_args": ["python3", str(stub)],
            },
        ]
    }
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")
    done_dir = tmp_path / "out" / "task_done"
    done_dir.mkdir(parents=True)
    (done_dir / "with_nexus_stub.jsonl").write_text(
        json.dumps({"status": "SUCCESS", "skill_mount_contract_status": "PASS", "skill_mount_contract": [{"skill_id": "s"}]}) + "\n",
        encoding="utf-8",
    )
    manifest = build_resume_manifest(matrix_path=matrix_path, output_root=tmp_path / "out")
    manifest_path = tmp_path / "resume.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    docs_catalog = tmp_path / "docs_catalog.json"

    summary = run_resume_manifest(
        resume_manifest_path=manifest_path,
        docs_catalog_path=docs_catalog,
    )

    assert summary["status"] == "PASS"
    assert summary["summary"]["planned_rows"] == 2
    assert summary["summary"]["completed_rows"] == 2
    assert summary["results"][0]["resumed_from_existing_artifact"] is True
    assert docs_catalog.exists()


def test_run_resume_manifest_seals_only_manifest_selected_rows(tmp_path: Path):
    stub = tmp_path / "stub_runner.py"
    stub.write_text(
        "import argparse, json\n"
        "from pathlib import Path\n"
        "parser=argparse.ArgumentParser(); parser.add_argument('--output-dir')\n"
        "args, _ = parser.parse_known_args(); out=Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)\n"
        "row={'status':'SUCCESS','skill_mount_contract_status':'PASS','skill_mount_contract':[{'skill_id':'s'}]}\n"
        "Path(out, 'with_nexus_stub.jsonl').write_text(json.dumps(row)+'\\n', encoding='utf-8')\n",
        encoding="utf-8",
    )
    matrix = {
        "rows": [
            {"row_id": "task::capability", "arm_type": "capability_only", "runner_args": ["python3", str(stub)]},
            {
                "row_id": "task::skill",
                "arm_id": "skill",
                "arm_type": "skill_ablation",
                "skill_id": "s",
                "runtime_eligible": True,
                "runner_env": {},
                "runner_args": ["python3", str(stub)],
            },
        ]
    }
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")
    manifest = build_resume_manifest(
        matrix_path=matrix_path,
        output_root=tmp_path / "out",
        row_id_filter="task::skill",
    )
    manifest_path = tmp_path / "resume.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    summary = run_resume_manifest(resume_manifest_path=manifest_path)

    assert summary["status"] == "PASS"
    assert summary["summary"]["planned_rows"] == 1
    assert [row["row_id"] for row in summary["results"]] == ["task::skill"]


def test_run_resume_manifest_skips_stale_remaining_rows_with_existing_artifacts(tmp_path: Path):
    stub = tmp_path / "stub_runner.py"
    stub.write_text("raise SystemExit('should not rerun existing artifacts')\n", encoding="utf-8")
    matrix = {
        "rows": [
            {
                "row_id": "task::skill",
                "arm_id": "skill",
                "arm_type": "skill_ablation",
                "skill_id": "s",
                "runtime_eligible": True,
                "runner_env": {},
                "runner_args": ["python3", str(stub)],
            }
        ]
    }
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")
    done_dir = tmp_path / "out" / "task_skill"
    done_dir.mkdir(parents=True)
    (done_dir / "with_nexus_stub.jsonl").write_text(
        json.dumps({"status": "SUCCESS", "skill_mount_contract_status": "PASS", "skill_mount_contract": [{"skill_id": "s"}]}) + "\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "resume.json"
    manifest_path.write_text(
        json.dumps(
            {
                "matrix_path": str(matrix_path),
                "output_root": str(tmp_path / "out"),
                "remaining_row_ids": ["task::skill"],
                "completed_row_ids": [],
            }
        ),
        encoding="utf-8",
    )

    summary = run_resume_manifest(resume_manifest_path=manifest_path)

    assert summary["status"] == "PASS"
    assert summary["summary"]["planned_rows"] == 1
    assert summary["results"][0]["resumed_from_existing_artifact"] is True


def test_run_resume_manifest_can_collect_existing_returns_for_reports(tmp_path: Path):
    matrix = {
        "rows": [
            {
                "row_id": "task::bad",
                "arm_id": "bad",
                "arm_type": "skill_ablation",
                "skill_id": "s",
                "runtime_eligible": True,
            },
            {
                "row_id": "task::good",
                "arm_id": "good",
                "arm_type": "skill_ablation",
                "skill_id": "s",
                "runtime_eligible": True,
            },
        ]
    }
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")
    for row_id, status in (("task_bad", "FAILED"), ("task_good", "SUCCESS")):
        row_dir = tmp_path / "out" / row_id
        row_dir.mkdir(parents=True)
        row = {"status": status, "skill_mount_contract_status": "PASS", "skill_mount_contract": [{"skill_id": "s"}]}
        (row_dir / "with_nexus_stub.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    manifest_path = tmp_path / "resume.json"
    manifest_path.write_text(
        json.dumps(
            {
                "matrix_path": str(matrix_path),
                "output_root": str(tmp_path / "out"),
                "completed_row_ids": ["task::bad", "task::good"],
                "remaining_row_ids": [],
            }
        ),
        encoding="utf-8",
    )

    summary = run_resume_manifest(resume_manifest_path=manifest_path, collect_existing_returns=True)

    assert summary["status"] == "RETURN"
    assert summary["summary"]["completed_rows"] == 2
    assert summary["summary"]["return_count"] == 1
    assert [row["row_id"] for row in summary["results"]] == ["task::bad", "task::good"]


def test_run_resume_manifest_collects_remaining_rows_after_return(tmp_path: Path):
    stub = tmp_path / "stub_runner.py"
    stub.write_text(
        "import argparse, json\n"
        "from pathlib import Path\n"
        "parser=argparse.ArgumentParser(); parser.add_argument('--output-dir')\n"
        "args, _ = parser.parse_known_args(); out=Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)\n"
        "status = 'FAILED' if out.name.endswith('bad') else 'SUCCESS'\n"
        "row={'status':status,'skill_mount_contract_status':'PASS','skill_mount_contract':[{'skill_id':'s'}]}\n"
        "Path(out, 'with_nexus_stub.jsonl').write_text(json.dumps(row)+'\\n', encoding='utf-8')\n",
        encoding="utf-8",
    )
    matrix = {
        "rows": [
            {
                "row_id": "task::bad",
                "arm_id": "bad",
                "arm_type": "skill_ablation",
                "skill_id": "s",
                "runtime_eligible": True,
                "runner_args": ["python3", str(stub)],
            },
            {
                "row_id": "task::good",
                "arm_id": "good",
                "arm_type": "skill_ablation",
                "skill_id": "s",
                "runtime_eligible": True,
                "runner_args": ["python3", str(stub)],
            },
        ]
    }
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")
    manifest = build_resume_manifest(matrix_path=matrix_path, output_root=tmp_path / "out")
    manifest_path = tmp_path / "resume.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    summary = run_resume_manifest(resume_manifest_path=manifest_path, collect_existing_returns=True)

    assert summary["status"] == "RETURN"
    assert summary["summary"]["completed_rows"] == 2
    assert summary["summary"]["return_count"] == 1
    assert [row["row_id"] for row in summary["results"]] == ["task::bad", "task::good"]


def test_classify_skill_fit_failure_routes_timeout_policy():
    skill_result = {
        "status": "RETURN",
        "arm_type": "skill_ablation",
        "skill_id": "debug-skill",
        "reason": "delivery_or_ablation_gate_return",
        "benchmark_row": {"infra_invalid_reason": "timeout_during_gemini"},
    }
    task_result = {
        "status": "RETURN",
        "arm_type": "capability_only",
        "reason": "delivery_or_ablation_gate_return",
        "benchmark_row": {"infra_invalid_reason": "timeout_before_receipt"},
    }

    assert classify_skill_fit_failure(skill_result)["kind"] == "skill_stop_loss"
    assert classify_skill_fit_failure(task_result)["kind"] == "task_unstable_long_tail"


def test_skill_fit_live_row_returns_on_model_call_without_tokens():
    status = _result_status_from_gate(
        {"arm_type": "skill_ablation"},
        {
            "status": "SUCCESS",
            "semantic_status": "VERIFIED",
            "infra_invalid_reason": "model_call_without_tokens",
            "run_eligible": False,
            "model_calls": 1,
            "total_tokens": 0,
            "token_measured": False,
        },
        {"status": "PASS"},
    )
    classified = _with_failure_classification(
        {
            "status": status,
            "arm_type": "skill_ablation",
            "skill_id": "research-source-conflict-resolver",
            "reason": "model_call_without_tokens",
            "benchmark_row": {"infra_invalid_reason": "model_call_without_tokens"},
        }
    )

    assert status == "RETURN"
    assert classified["failure_classification"]["kind"] == "provider_token_ineligible"
    assert classified["failure_action"] == "stop_full_live_and_run_probe_or_clean_replay"


def test_classify_skill_fit_failure_routes_adapter_policy():
    result = {
        "status": "RETURN",
        "arm_type": "capability_only",
        "task_ref": {"repo_kind": "external"},
        "stderr_tail": "clone/setup adapter is required before public execution",
    }

    assert classify_skill_fit_failure(result)["kind"] == "adapter_missing"


def test_matrix_runner_live_summary_persists_catalog_paths_with_stub_runner(tmp_path: Path):
    stub = tmp_path / "stub_runner.py"
    stub.write_text(
        "import argparse, json\n"
        "from pathlib import Path\n"
        "parser=argparse.ArgumentParser(); parser.add_argument('--output-dir')\n"
        "args, _ = parser.parse_known_args(); out=Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)\n"
        "row={'status':'SUCCESS','skill_mount_contract_status':'PASS','skill_mount_contract':[{'skill_id':'nexus-tdd'}]}\n"
        "Path(out, 'with_nexus_stub.jsonl').write_text(json.dumps(row)+'\\n', encoding='utf-8')\n",
        encoding="utf-8",
    )
    matrix = {
        "rows": [
            {
                "row_id": "task::skill",
                "arm_id": "skill",
                "arm_type": "skill_ablation",
                "anonymous_label": "candidate_001",
                "skill_id": "nexus-tdd",
                "source_root": "nexus_repo",
                "runtime_eligible": True,
                "task_ref": {"manifest": "m.json", "task_id": "task"},
                "runner_env": {},
                "runner_args": ["python3", str(stub)],
            }
        ]
    }
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")

    docs_catalog = tmp_path / "docs_catalog.json"
    summary = run_matrix(
        matrix_path=matrix_path,
        output_root=tmp_path / "out",
        preflight_only=False,
        docs_catalog_path=docs_catalog,
    )
    persisted = json.loads((tmp_path / "out" / "live_summary.json").read_text(encoding="utf-8"))

    assert summary["status"] == "PASS"
    assert persisted["skill_fit_catalog_path"] == str(tmp_path / "out" / "skill_fit_catalog.json")
    assert persisted["docs_skill_fit_catalog_path"] == str(docs_catalog)


def test_matrix_runner_accepts_blocked_negative_control_with_failed_benchmark_status(tmp_path: Path):
    stub = tmp_path / "stub_runner.py"
    stub.write_text(
        "import argparse, json\n"
        "from pathlib import Path\n"
        "parser=argparse.ArgumentParser(); parser.add_argument('--output-dir')\n"
        "args, _ = parser.parse_known_args(); out=Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)\n"
        "row={'status':'FAILED','skill_mount_contract_status':'EMPTY','skill_mount_contract':[]}\n"
        "Path(out, 'with_nexus_stub.jsonl').write_text(json.dumps(row)+'\\n', encoding='utf-8')\n",
        encoding="utf-8",
    )
    matrix = {
        "rows": [
            {
                "row_id": "task::wrong",
                "arm_id": "wrong",
                "arm_type": "wrong_or_quarantined_skill",
                "skill_id": "bad",
                "task_ref": {"manifest": "m.json", "task_id": "task"},
                "runner_env": {},
                "runner_args": ["python3", str(stub)],
            }
        ]
    }
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")

    summary = run_matrix(matrix_path=matrix_path, output_root=tmp_path / "out")

    assert summary["status"] == "PASS"
    assert summary["results"][0]["ablation_gate_row"]["status"] == "BLOCK"
    assert summary["results"][0]["ablation_gate"]["status"] == "PASS"


def test_skill_fit_catalog_requires_receipt_backed_effective_rows():
    summary = {
        "mode": "live",
        "results": [
            {
                "arm_type": "capability_only",
                "status": "PASS",
                "ablation_gate": {"status": "PASS"},
                "ablation_gate_row": {"status": "PASS", "trust_mismatch": False},
            },
            {
                "arm_type": "skill_ablation",
                "skill_id": "nexus-tdd",
                "anonymous_label": "candidate_001",
                "source_root": "nexus_repo",
                "runtime_eligible": True,
                "status": "PASS",
                "ablation_gate": {"status": "PASS"},
                "ablation_gate_row": {
                    "status": "KEEP",
                    "trust_mismatch": False,
                    "evidence_path": "evidence.json",
                    "receipt_path": "receipt",
                },
            },
            {
                "arm_type": "skill_ablation",
                "skill_id": "external",
                "anonymous_label": "candidate_002",
                "source_root": "agents",
                "runtime_eligible": False,
                "status": "PASS",
                "ablation_gate": {"status": "PASS"},
                "ablation_gate_row": {
                    "status": "KEEP",
                    "trust_mismatch": False,
                    "evidence_path": "external-evidence.json",
                    "receipt_path": "external-receipt",
                },
            },
            {
                "arm_type": "wrong_or_quarantined_skill",
                "status": "PASS",
                "ablation_gate": {"status": "PASS"},
                "ablation_gate_row": {"status": "BLOCK", "trust_mismatch": False},
            },
        ],
    }

    catalog = build_skill_fit_catalog(summary)
    verdicts = {item["skill_id"]: item["verdict"] for item in catalog["skill_verdicts"]}

    assert catalog["status"] == "PASS"
    assert verdicts == {"external": "replace_candidate", "nexus-tdd": "keep"}
    assert catalog["summary"]["negative_control_blocked_rows"] == 1


def test_skill_fit_catalog_groups_verdicts_by_capability_and_skill_id():
    summary = {
        "mode": "live",
        "results": [
            {
                "capability": "repair_and_coding",
                "arm_type": "skill_ablation",
                "skill_id": "shared-skill",
                "anonymous_label": "candidate_001",
                "source_root": "agents",
                "runtime_eligible": False,
                "status": "PASS",
                "ablation_gate": {"status": "PASS"},
                "ablation_gate_row": {
                    "status": "KEEP",
                    "trust_mismatch": False,
                    "evidence_path": "repair-evidence.json",
                    "receipt_path": "repair-receipt",
                },
            },
            {
                "capability": "governance_and_trust",
                "arm_type": "skill_ablation",
                "skill_id": "shared-skill",
                "anonymous_label": "candidate_001",
                "source_root": "agents",
                "runtime_eligible": False,
                "status": "PASS",
                "ablation_gate": {"status": "RETURN"},
                "ablation_gate_row": {
                    "status": "RETURN",
                    "trust_mismatch": False,
                    "evidence_path": "gov-evidence.json",
                    "receipt_path": "gov-receipt",
                },
            },
            {
                "arm_type": "wrong_or_quarantined_skill",
                "status": "PASS",
                "ablation_gate": {"status": "PASS"},
                "ablation_gate_row": {"status": "BLOCK", "trust_mismatch": False},
            },
        ],
    }

    catalog = build_skill_fit_catalog(summary)
    verdicts = {
        (item["capability"], item["skill_id"]): item["verdict"]
        for item in catalog["skill_verdicts"]
    }

    assert verdicts == {
        ("governance_and_trust", "shared-skill"): "reject",
        ("repair_and_coding", "shared-skill"): "replace_candidate",
    }


def test_skill_fit_catalog_index_groups_rows_by_capability_and_skill_id():
    summary = {
        "summary": {"planned_rows": 4, "completed_rows": 4},
        "results": [
            {
                "capability": "repair_and_coding",
                "arm_type": "capability_only",
                "row_id": "repair::base",
            },
            {
                "capability": "repair_and_coding",
                "arm_type": "skill_ablation",
                "skill_id": "shared-skill",
                "row_id": "repair::skill",
            },
            {
                "capability": "governance_and_trust",
                "arm_type": "skill_ablation",
                "skill_id": "shared-skill",
                "row_id": "governance::skill",
            },
            {
                "arm_type": "wrong_or_quarantined_skill",
                "row_id": "negative::skill",
            },
        ],
    }

    index = SkillFitCatalogIndex.from_run_summary(summary)

    assert index.planned_rows == 4
    assert index.completed_rows == 4
    assert [row["row_id"] for row in index.capability_only_rows] == ["repair::base"]
    assert [row["row_id"] for row in index.negative_rows] == ["negative::skill"]
    assert index.skill_keys == (
        ("governance_and_trust", "shared-skill"),
        ("repair_and_coding", "shared-skill"),
    )
    assert [row["row_id"] for row in index.by_skill[("repair_and_coding", "shared-skill")]] == [
        "repair::skill"
    ]
    assert [row["row_id"] for row in index.by_skill[("governance_and_trust", "shared-skill")]] == [
        "governance::skill"
    ]
    assert isinstance(index.rows, tuple)
    assert isinstance(index.by_skill[("repair_and_coding", "shared-skill")], tuple)


def test_skill_fit_catalog_returns_when_matrix_incomplete():
    summary = {
        "status": "RETURN",
        "mode": "live",
        "summary": {"planned_rows": 180, "completed_rows": 67},
        "results": [
            {
                "capability": "repair_and_coding",
                "arm_type": "skill_ablation",
                "skill_id": "tdd",
                "anonymous_label": "candidate_001",
                "source_root": "nexus_repo",
                "runtime_eligible": True,
                "status": "PASS",
                "ablation_gate": {"status": "PASS"},
                "ablation_gate_row": {
                    "status": "KEEP",
                    "trust_mismatch": False,
                    "evidence_path": "evidence.json",
                    "receipt_path": "receipt",
                },
            },
            {
                "arm_type": "wrong_or_quarantined_skill",
                "status": "PASS",
                "ablation_gate": {"status": "PASS"},
                "ablation_gate_row": {"status": "BLOCK", "trust_mismatch": False},
            },
        ],
    }

    catalog = build_skill_fit_catalog(summary)

    assert catalog["status"] == "RETURN"
    assert "matrix_completion_gate_return" in catalog["failures"]
    assert catalog["summary"]["matrix_complete"] is False


def test_skill_discovery_queue_and_promotion_policy_do_not_update_runtime():
    catalog = {
        "status": "PASS",
        "skill_verdicts": [
            {
                "capability": "repair_and_coding",
                "skill_id": "tdd",
                "verdict": "keep",
                "tested_rows": 5,
                "effective_rows": 5,
                "evidence_refs": ["evidence"],
                "receipt_refs": ["receipt"],
            },
            {
                "capability": "repair_and_coding",
                "skill_id": "external-debug",
                "verdict": "needs_more_data",
                "tested_rows": 5,
                "effective_rows": 1,
                "evidence_refs": ["evidence"],
                "receipt_refs": ["receipt"],
            },
            {
                "capability": "repair_and_coding",
                "skill_id": "bad-skill",
                "verdict": "reject",
                "tested_rows": 5,
                "effective_rows": 0,
                "evidence_refs": ["evidence"],
                "receipt_refs": ["receipt"],
            },
        ],
    }

    queue = build_skill_discovery_rerun_queue(catalog)
    policy = build_capability_skill_promotion_policy(catalog)

    assert queue["queue"] == [
        {
            "capability": "repair_and_coding",
            "skill_id": "external-debug",
            "verdict": "needs_more_data",
            "tested_rows": 5,
            "effective_rows": 1,
            "reason": "needs_more_data",
        }
    ]
    assert policy["runtime_update_allowed"] is False
    assert policy["defaults"] == {"repair_and_coding": "tdd"}
    assert policy["needs_more_data"] == {"repair_and_coding": ["external-debug"]}
    assert policy["rejected"] == {"repair_and_coding": ["bad-skill"]}


def test_promotion_policy_returns_when_positive_verdict_lacks_evidence():
    policy = build_capability_skill_promotion_policy(
        {
            "status": "PASS",
            "skill_verdicts": [
                {
                    "capability": "repair_and_coding",
                    "skill_id": "tdd",
                    "verdict": "keep",
                    "evidence_refs": [],
                    "receipt_refs": ["receipt"],
                }
            ],
        }
    )

    assert policy["status"] == "RETURN"
    assert policy["failures"] == ["repair_and_coding:tdd:promotion_without_evidence_or_receipt"]


def test_write_capability_skill_promotion_policy_outputs_json(tmp_path: Path):
    catalog_path = tmp_path / "catalog.json"
    output_path = tmp_path / "policy.json"
    catalog_path.write_text(
        json.dumps(
            {
                "status": "PASS",
                "skill_verdicts": [
                    {
                        "capability": "repair_and_coding",
                        "skill_id": "tdd",
                        "verdict": "keep",
                        "evidence_refs": ["evidence"],
                        "receipt_refs": ["receipt"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    policy = write_capability_skill_promotion_policy(catalog_path=catalog_path, output_path=output_path)

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert policy["defaults"] == {"repair_and_coding": "tdd"}
    assert saved["defaults"] == {"repair_and_coding": "tdd"}


def test_promotion_policy_reads_final_capability_catalog_sections():
    policy = build_capability_skill_promotion_policy(
        {
            "status": "PASS",
            "capabilities": {
                "repair_and_coding": {
                    "default_candidate": None,
                    "alternate_candidates": ["tdd"],
                },
                "governance_and_trust": {
                    "alternate_candidates": ["acceptance-evidence-failclosed"],
                    "needs_more_data_normal_lane": ["acceptance-evidence-failclosed", "cso"],
                    "rejected": ["self-audit"],
                },
                "research_and_source_discipline": {
                    "replace_candidates": ["research-citation-chain-verifier"],
                },
            },
        }
    )

    assert policy["runtime_update_allowed"] is False
    assert policy["alternates"] == {
        "governance_and_trust": ["acceptance-evidence-failclosed"],
        "repair_and_coding": ["tdd"],
    }
    assert policy["replace_candidates"] == {
        "research_and_source_discipline": ["research-citation-chain-verifier"]
    }
    assert policy["needs_more_data"] == {"governance_and_trust": ["cso"]}
    assert policy["rejected"] == {"governance_and_trust": ["self-audit"]}


def test_skill_fit_completion_gate_passes_with_actionable_capability_recommendations():
    gate = build_skill_fit_completion_gate(
        {
            "status": "PASS",
            "skill_fit_complete": True,
            "sf_catalog_complete": True,
            "sf_promotion_policy_draft_complete": True,
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        {
            "status": "PASS",
            "runtime_update_allowed": False,
            "defaults": {},
            "alternates": {
                "repair_and_coding": ["tdd"],
                "governance_and_trust": ["acceptance-evidence-failclosed"],
            },
            "replace_candidates": {
                "forecast_pregate": ["create-plan"],
                "research_and_source_discipline": ["research-citation-chain-verifier"],
            },
            "needs_more_data": {},
            "rejected": {},
        },
    )

    assert gate["status"] == "PASS"
    assert gate["skill_fit_complete"] is True
    assert gate["runtime_update_allowed"] is False
    assert gate["public_benchmark_allowed"] is False
    assert gate["summary"]["actionable_capability_count"] == 3
    assert gate["summary"]["replace_candidate_count"] == 1


def test_skill_fit_completion_gate_returns_when_capability_has_no_actionable_skill():
    gate = build_skill_fit_completion_gate(
        {
            "status": "PASS",
            "skill_fit_complete": True,
            "sf_catalog_complete": True,
            "sf_promotion_policy_draft_complete": True,
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        {
            "status": "PASS",
            "runtime_update_allowed": False,
            "defaults": {},
            "alternates": {"repair_and_coding": ["tdd"]},
            "replace_candidates": {},
            "needs_more_data": {"governance_and_trust": ["cso"]},
            "rejected": {},
        },
    )

    assert gate["status"] == "RETURN"
    assert "governance_and_trust:needs_more_data_not_closed" in gate["failures"]
    assert "research_and_source_discipline:no_actionable_skill_recommendation" in gate["failures"]


def test_write_skill_fit_completion_gate_outputs_json(tmp_path: Path):
    catalog_path = tmp_path / "catalog.json"
    policy_path = tmp_path / "policy.json"
    output_path = tmp_path / "gate.json"
    catalog_path.write_text(
        json.dumps(
            {
                "status": "PASS",
                "skill_fit_complete": True,
                "sf_catalog_complete": True,
                "sf_promotion_policy_draft_complete": True,
                "runtime_update_allowed": False,
                "public_benchmark_allowed": False,
            }
        ),
        encoding="utf-8",
    )
    policy_path.write_text(
        json.dumps(
            {
                "status": "PASS",
                "runtime_update_allowed": False,
                "defaults": {},
                "alternates": {
                    "repair_and_coding": ["tdd"],
                    "governance_and_trust": ["acceptance-evidence-failclosed"],
                },
                "replace_candidates": {
                    "research_and_source_discipline": ["research-citation-chain-verifier"]
                },
                "needs_more_data": {},
                "rejected": {},
            }
        ),
        encoding="utf-8",
    )

    gate = write_skill_fit_completion_gate(
        catalog_path=catalog_path,
        promotion_policy_path=policy_path,
        output_path=output_path,
    )

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert gate["status"] == "PASS"
    assert saved["schema"] == "nexus.skill_fit_completion_gate.v1"


def test_runtime_promotion_review_disposes_all_recommended_skills_without_runtime_write():
    review = build_skill_fit_runtime_promotion_review(
        {
            "status": "PASS",
            "skill_fit_complete": True,
            "sf_catalog_complete": True,
            "sf_promotion_policy_draft_complete": True,
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        {
            "status": "PASS",
            "runtime_update_allowed": False,
            "defaults": {},
            "alternates": {
                "repair_and_coding": ["tdd"],
                "governance_and_trust": ["acceptance-evidence-failclosed"],
            },
            "replace_candidates": {
                "forecast_pregate": ["create-plan"],
                "research_and_source_discipline": ["research-citation-chain-verifier"]
            },
            "needs_more_data": {},
            "rejected": {},
        },
        candidate_sources=[
            {
                "candidates": [
                    {
                        "skill_id": "tdd",
                        "source_root": "nexus_repo",
                        "source_type": "nexus_local",
                        "path": "/repo/.agents/skills/tdd/SKILL.md",
                        "runtime_eligible": True,
                        "safety_status": "runtime_reviewed",
                    },
                    {
                        "skill_id": "acceptance-evidence-failclosed",
                        "source_root": "agents",
                        "source_type": "reference",
                        "path": "/Users/jameschen/.agents/skills/devops/acceptance-evidence-failclosed/SKILL.md",
                        "runtime_eligible": False,
                        "safety_status": "ablation_only",
                    },
                    {
                        "skill_id": "research-citation-chain-verifier",
                        "path": ".agents/skills/research-citation-chain-verifier/SKILL.md",
                    },
                    {
                        "skill_id": "create-plan",
                        "path": "/Users/jameschen/Workspace/nexus/.agents/skills/create-plan/SKILL.md",
                        "runtime_eligible": False,
                    },
                    {
                        "skill_id": "create-plan",
                        "metadata_overlay": True,
                        "source_root": "nexus_repo",
                        "source_type": "repo_local_materialized_external",
                        "path": "/Users/jameschen/Workspace/nexus/.agents/skills/create-plan/SKILL.md",
                        "runtime_eligible": True,
                        "safety_status": "runtime_reviewed",
                    },
                ]
            }
        ],
    )

    dispositions = {item["skill_id"]: item["disposition"] for item in review["runtime_review_items"]}
    assert review["status"] == "PASS"
    assert review["sf_closed_loop_complete"] is True
    assert review["runtime_update_allowed"] is False
    assert dispositions == {
        "tdd": "runtime_review_ready",
        "acceptance-evidence-failclosed": "catalog_alternate_only",
        "research-citation-chain-verifier": "repo_candidate_runtime_review_required",
        "create-plan": "runtime_review_ready",
    }


def test_write_runtime_promotion_review_outputs_json(tmp_path: Path):
    catalog_path = tmp_path / "catalog.json"
    policy_path = tmp_path / "policy.json"
    source_path = tmp_path / "candidates.json"
    output_path = tmp_path / "runtime_review.json"
    catalog_path.write_text(
        json.dumps(
            {
                "status": "PASS",
                "skill_fit_complete": True,
                "sf_catalog_complete": True,
                "sf_promotion_policy_draft_complete": True,
                "runtime_update_allowed": False,
                "public_benchmark_allowed": False,
            }
        ),
        encoding="utf-8",
    )
    policy_path.write_text(
        json.dumps(
            {
                "status": "PASS",
                "runtime_update_allowed": False,
                "defaults": {},
                "alternates": {
                    "repair_and_coding": ["tdd"],
                    "governance_and_trust": ["acceptance-evidence-failclosed"],
                },
                "replace_candidates": {
                    "research_and_source_discipline": ["research-citation-chain-verifier"]
                },
                "needs_more_data": {},
                "rejected": {},
            }
        ),
        encoding="utf-8",
    )
    source_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "skill_id": "tdd",
                        "source_root": "nexus_repo",
                        "source_type": "nexus_local",
                        "path": "/repo/.agents/skills/tdd/SKILL.md",
                        "runtime_eligible": True,
                        "safety_status": "runtime_reviewed",
                    }
                ],
                "materialized_skills": [
                    {
                        "skill_id": "research-citation-chain-verifier",
                        "path": ".agents/skills/research-citation-chain-verifier/SKILL.md",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    review = write_skill_fit_runtime_promotion_review(
        catalog_path=catalog_path,
        promotion_policy_path=policy_path,
        output_path=output_path,
        candidate_source_paths=[source_path],
    )

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert review["status"] == "PASS"
    assert saved["schema"] == "nexus.skill_fit_runtime_promotion_review.v1"


def test_runtime_policy_apply_gate_builds_primary_overlay_without_public_benchmark():
    patch_plan = {
        "status": "PASS",
        "planned_changes": [
            {
                "capability_id": "repair_loop",
                "skill_id": "tdd",
                "planned_action": "set_capability_primary_skill_candidate",
                "apply_state": "apply_ready_but_not_written",
                "evidence_refs": ["seal:tdd"],
            },
            {
                "capability_id": "research_and_source_discipline",
                "skill_id": "research-citation-chain-verifier",
                "planned_action": "keep_as_runtime_review_ready_alternate_until_research_tiebreak",
                "apply_state": "hold_primary_default",
            },
        ],
    }
    review = {
        "status": "PASS",
        "sf_closed_loop_complete": True,
        "runtime_review_items": [
            {
                "capability": "repair_loop",
                "skill_id": "tdd",
                "disposition": "runtime_review_ready",
                "runtime_review_ready": True,
                "runtime_eligible": True,
                "safety_status": "runtime_reviewed",
                "source_root": "nexus_repo",
                "source_type": "nexus_local",
                "path": "/repo/.agents/skills/tdd/SKILL.md",
            }
        ],
    }

    gate = build_skill_fit_runtime_policy_apply_gate(patch_plan, review)
    overlay = build_skill_fit_runtime_policy_overlay(gate)

    assert gate["status"] == "PASS"
    assert gate["summary"]["runtime_update_allowed"] is True
    assert gate["summary"]["public_benchmark_allowed"] is False
    assert overlay["status"] == "PASS"
    assert overlay["primary_skill_by_capability"] == {"repair_loop": "tdd"}
    assert overlay["public_benchmark_allowed"] is False


def test_runtime_policy_apply_gate_blocks_unreviewed_primary():
    patch_plan = {
        "status": "PASS",
        "planned_changes": [
            {
                "capability_id": "repair_loop",
                "skill_id": "tdd",
                "planned_action": "set_capability_primary_skill_candidate",
                "apply_state": "apply_ready_but_not_written",
                "evidence_refs": ["seal:tdd"],
            }
        ],
    }
    review = {
        "status": "PASS",
        "sf_closed_loop_complete": True,
        "runtime_review_items": [
            {
                "capability": "repair_loop",
                "skill_id": "tdd",
                "disposition": "catalog_alternate_only",
                "runtime_review_ready": False,
                "runtime_eligible": False,
                "safety_status": "ablation_only",
            }
        ],
    }

    gate = build_skill_fit_runtime_policy_apply_gate(patch_plan, review)
    overlay = build_skill_fit_runtime_policy_overlay(gate)

    assert gate["status"] == "BLOCKED"
    assert "repair_loop:tdd:not_runtime_review_ready" in gate["blockers"]
    assert overlay["status"] == "BLOCKED"
    assert overlay["primary_skill_by_capability"] == {}


def test_write_runtime_policy_apply_gate_outputs_gate_and_overlay(tmp_path: Path):
    patch_path = tmp_path / "patch.json"
    review_path = tmp_path / "review.json"
    gate_path = tmp_path / "apply_gate.json"
    overlay_path = tmp_path / "overlay.json"
    patch_path.write_text(
        json.dumps(
            {
                "status": "PASS",
                "planned_changes": [
                    {
                        "capability_id": "forecast_pregate",
                        "skill_id": "create-plan",
                        "planned_action": "set_capability_primary_skill_candidate",
                        "apply_state": "apply_ready_but_not_written",
                        "evidence_refs": ["seal:create-plan"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    review_path.write_text(
        json.dumps(
            {
                "status": "PASS",
                "sf_closed_loop_complete": True,
                "runtime_review_items": [
                    {
                        "capability": "forecast_pregate",
                        "skill_id": "create-plan",
                        "disposition": "runtime_review_ready",
                        "runtime_review_ready": True,
                        "runtime_eligible": True,
                        "safety_status": "runtime_reviewed",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    gate = write_skill_fit_runtime_policy_apply_gate(
        patch_plan_path=patch_path,
        promotion_review_path=review_path,
        output_path=gate_path,
        overlay_output_path=overlay_path,
    )
    saved_overlay = json.loads(overlay_path.read_text(encoding="utf-8"))

    assert gate["status"] == "PASS"
    assert json.loads(gate_path.read_text(encoding="utf-8"))["schema"] == "nexus.sf_runtime_policy_apply_gate.v1"
    assert saved_overlay["primary_skill_by_capability"] == {"forecast_pregate": "create-plan"}


def test_promotion_policy_infers_capability_from_catalog_matrix_path():
    policy = build_capability_skill_promotion_policy(
        {
            "status": "PASS",
            "matrix_path": "docs/reports/NEXUS_SKILL_FIT_EXECUTION_MATRIX_REPAIR_AND_CODING_FLASH180.json",
            "skill_verdicts": [
                {
                    "skill_id": "tdd",
                    "verdict": "keep",
                    "evidence_refs": ["evidence"],
                    "receipt_refs": ["receipt"],
                }
            ],
        }
    )

    assert policy["defaults"] == {"repair_and_coding": "tdd"}


def test_promotion_threshold_contract_keeps_needs_more_data_out_of_runtime():
    catalog = {
        "status": "PASS",
        "summary": {"matrix_complete": True},
        "skill_verdicts": [
            {
                "capability": "repair_and_coding",
                "skill_id": "debug-skill",
                "verdict": "needs_more_data",
                "tested_rows": 30,
                "effective_rows": 10,
                "evidence_refs": ["evidence"],
                "receipt_refs": ["receipt"],
            }
        ],
    }
    policy = {
        "status": "PASS",
        "runtime_update_allowed": False,
        "defaults": {},
        "alternates": {},
        "needs_more_data": {"repair_and_coding": ["debug-skill"]},
    }
    queue = {"queue": [{"capability": "repair_and_coding", "skill_id": "debug-skill"}]}

    contract = build_skill_promotion_threshold_contract(catalog, policy, rerun_queue=queue)

    assert contract["status"] == "PASS"
    assert contract["runtime_update_allowed"] is False
    assert contract["promotion_allowed"] is False
    assert contract["flash100_allowed"] is False
    assert contract["summary"]["needs_targeted_replay_count"] == 1
    assert contract["capability_skill_thresholds"][0]["threshold_status"] == "targeted_replay_required"


def test_promotion_threshold_contract_treats_sealed_needs_more_data_as_alternate_candidate():
    catalog = {
        "status": "PASS",
        "summary": {"matrix_complete": True},
        "skill_verdicts": [
            {
                "capability": "repair_and_coding",
                "skill_id": "tdd",
                "verdict": "needs_more_data",
                "tested_rows": 30,
                "effective_rows": 19,
                "task_buckets": ["bugfix", "docs_code_sync", "feature", "ops_research", "refactor"],
                "evidence_refs": ["evidence"],
                "receipt_refs": ["receipt"],
            }
        ],
    }
    policy = {
        "status": "PASS",
        "runtime_update_allowed": False,
        "defaults": {},
        "alternates": {},
        "needs_more_data": {"repair_and_coding": ["tdd"]},
    }

    contract = build_skill_promotion_threshold_contract(catalog, policy)

    assert contract["status"] == "PASS"
    assert contract["runtime_update_allowed"] is False
    assert contract["promotion_allowed"] is False
    assert contract["flash100_allowed"] is True
    assert contract["summary"]["alternate_candidate_count"] == 1
    assert contract["capability_skill_thresholds"][0]["threshold_status"] == "validation_required"
    assert contract["capability_skill_thresholds"][0]["threshold_recommendation"] == "alternate_candidate"


def test_skill_fit_status_rollup_finds_skill_but_blocks_benchmark_until_threshold_clean():
    rollup = build_skill_fit_status_rollup(
        promotion_policies=[
            {
                "status": "PASS",
                "runtime_update_allowed": False,
                "defaults": {"repair_and_coding": "tdd"},
                "alternates": {},
                "needs_more_data": {"repair_and_coding": ["debug-skill"]},
                "rejected": {},
            }
        ],
        threshold_contracts=[
            {
                "status": "RETURN",
                "capability_skill_thresholds": [
                    {
                        "capability": "repair_and_coding",
                        "skill_id": "tdd",
                        "tested_rows": 11,
                        "effective_rows": 11,
                        "effective_rate": 1.0,
                        "observed_rows_ok": False,
                        "threshold_recommendation": "reject",
                    }
                ],
                "failures": ["repair_and_coding:tdd:insufficient_tested_rows"],
            }
        ],
    )

    assert rollup["has_found_skill"] is True
    assert rollup["benchmark_allowed"] is False
    assert rollup["found_skill_pairs"][0]["skill_id"] == "tdd"
    assert rollup["found_skill_pairs"][0]["promotion_blockers"] == ["insufficient_tested_rows"]
    assert rollup["next_task_cards"][0]["id"] == "SF-1"


def test_skill_fit_status_rollup_uses_threshold_alternate_candidate_even_if_policy_needs_more_data():
    rollup = build_skill_fit_status_rollup(
        promotion_policies=[
            {
                "status": "PASS",
                "runtime_update_allowed": False,
                "defaults": {},
                "alternates": {},
                "needs_more_data": {"repair_and_coding": ["tdd"]},
                "rejected": {},
            }
        ],
        threshold_contracts=[
            {
                "status": "PASS",
                "capability_skill_thresholds": [
                    {
                        "capability": "repair_and_coding",
                        "skill_id": "tdd",
                        "tested_rows": 30,
                        "effective_rows": 19,
                        "effective_rate": 0.6333,
                        "observed_rows_ok": True,
                        "threshold_recommendation": "alternate_candidate",
                    }
                ],
                "failures": [],
            }
        ],
    )

    assert rollup["has_found_skill"] is True
    assert rollup["promotion_ready"] is True
    assert rollup["benchmark_allowed"] is True
    assert rollup["promotion_ready_pairs"][0]["skill_id"] == "tdd"
    assert rollup["next_task_cards"][0]["id"] == "SF-SEAL"


def test_skill_fit_status_rollup_keeps_capability_discovery_cards_after_first_ready_pair():
    rollup = build_skill_fit_status_rollup(
        promotion_policies=[
            {
                "status": "PASS",
                "runtime_update_allowed": False,
                "defaults": {},
                "alternates": {},
                "needs_more_data": {
                    "repair_and_coding": ["tdd"],
                    "governance_and_trust": ["nexus-root-cause-probe"],
                },
                "rejected": {"research_and_source_discipline": ["generic-research"]},
            }
        ],
        threshold_contracts=[
            {
                "status": "PASS",
                "capability_skill_thresholds": [
                    {
                        "capability": "repair_and_coding",
                        "skill_id": "tdd",
                        "tested_rows": 30,
                        "effective_rows": 19,
                        "effective_rate": 0.6333,
                        "observed_rows_ok": True,
                        "threshold_recommendation": "alternate_candidate",
                    }
                ],
                "failures": [],
            }
        ],
    )

    task_ids = [item["id"] for item in rollup["next_task_cards"]]
    assert task_ids[0] == "SF-SEAL"
    assert "SF-governance_and_trust-TARGETED-REPLAY" in task_ids
    assert "SF-research_and_source_discipline-DISCOVERY" in task_ids


def test_promotion_threshold_contract_allows_flash100_only_after_positive_verdict():
    catalog = {
        "status": "PASS",
        "summary": {"matrix_complete": True},
        "skill_verdicts": [
            {
                "capability": "repair_and_coding",
                "skill_id": "tdd",
                "verdict": "keep",
                "tested_rows": 30,
                "effective_rows": 30,
                "evidence_refs": ["evidence"],
                "receipt_refs": ["receipt"],
            }
        ],
    }
    policy = {
        "status": "PASS",
        "runtime_update_allowed": False,
        "defaults": {"repair_and_coding": "tdd"},
    }

    contract = build_skill_promotion_threshold_contract(catalog, policy)

    assert contract["status"] == "PASS"
    assert contract["flash100_allowed"] is True
    assert contract["promotion_allowed"] is False
    assert contract["capability_skill_thresholds"][0]["threshold_status"] == "validation_required"


def test_write_skill_promotion_threshold_contract_outputs_json(tmp_path: Path):
    catalog_path = tmp_path / "catalog.json"
    policy_path = tmp_path / "policy.json"
    queue_path = tmp_path / "queue.json"
    output_path = tmp_path / "threshold.json"
    catalog_path.write_text(
        json.dumps(
            {
                "status": "PASS",
                "summary": {"matrix_complete": True},
                "skill_verdicts": [
                    {
                        "capability": "repair_and_coding",
                        "skill_id": "debug-skill",
                        "verdict": "needs_more_data",
                        "tested_rows": 30,
                        "effective_rows": 3,
                        "evidence_refs": ["evidence"],
                        "receipt_refs": ["receipt"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    policy_path.write_text(json.dumps({"status": "PASS", "runtime_update_allowed": False}), encoding="utf-8")
    queue_path.write_text(json.dumps({"queue": [{"capability": "repair_and_coding", "skill_id": "debug-skill"}]}), encoding="utf-8")

    contract = write_skill_promotion_threshold_contract(
        catalog_path=catalog_path,
        promotion_policy_path=policy_path,
        rerun_queue_path=queue_path,
        output_path=output_path,
    )

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved == contract
    assert saved["schema"] == "nexus.skill_promotion_threshold_contract.v1"
    assert saved["flash100_allowed"] is False


def test_skill_fit_row_level_rca_recommends_targeted_replay_for_promising_governance_skill():
    summary = {
        "status": "PASS",
        "results": [
            {
                "capability": "governance_and_trust",
                "arm_type": "capability_only",
                "row_id": "gov::t1::capability_only",
                "status": "PASS",
                "task_ref": {"manifest": "m.json", "task_id": "t1"},
            },
            {
                "capability": "governance_and_trust",
                "arm_type": "skill_ablation",
                "row_id": "gov::t1::skill",
                "skill_id": "nexus-root-cause-probe",
                "status": "PASS",
                "task_ref": {"manifest": "m.json", "task_id": "t1"},
                "ablation_gate": {"status": "PASS"},
                "ablation_gate_row": {
                    "status": "KEEP",
                    "evidence_path": "evidence.json",
                    "receipt_path": "receipt",
                    "trust_mismatch": False,
                },
            },
            {
                "capability": "governance_and_trust",
                "arm_type": "skill_ablation",
                "row_id": "gov::t2::skill",
                "skill_id": "nexus-root-cause-probe",
                "status": "PASS",
                "task_ref": {"manifest": "m.json", "task_id": "t2"},
                "ablation_gate": {"status": "PASS"},
                "ablation_gate_row": {
                    "status": "RETURN",
                    "missing_effective_fields": ["outcome_contributed"],
                    "evidence_path": "evidence2.json",
                    "receipt_path": "receipt2",
                    "trust_mismatch": False,
                },
            },
        ],
    }
    catalog = {
        "status": "PASS",
        "skill_verdicts": [
            {
                "capability": "governance_and_trust",
                "skill_id": "nexus-root-cause-probe",
                "verdict": "needs_more_data",
            }
        ],
    }

    rca = build_skill_fit_row_level_rca(summary, catalog, capability="governance_and_trust")

    skill = rca["skill_analyses"][0]
    assert rca["status"] == "PASS"
    assert rca["summary"]["targeted_replay_count"] == 1
    assert skill["effective_rate"] == 0.5
    assert skill["recommendation"] == "targeted_replay"
    assert skill["targeted_replay_row_ids"] == ["gov::t1::skill", "gov::t2::skill"]
    assert skill["rows"][1]["missing_effective_fields"] == ["outcome_contributed"]


def test_skill_fit_row_index_groups_baselines_catalog_and_skill_rows_for_rca_and_cost():
    summary = {
        "capability": "governance_and_trust",
        "results": [
            {
                "capability": "research_and_source_discipline",
                "arm_type": "skill_ablation",
                "skill_id": "research-skill",
                "row_id": "research::t1::skill",
                "task_ref": {"manifest": "research.json", "task_id": "t1"},
            },
            {
                "capability": "governance_and_trust",
                "arm_type": "skill_ablation",
                "skill_id": "z-last",
                "row_id": "gov::t2::skill",
                "task_ref": {"manifest": "gov.json", "task_id": "t2"},
            },
            {
                "capability": "governance_and_trust",
                "arm_type": "capability_only",
                "row_id": "gov::t1::capability_only",
                "task_ref": {"manifest": "gov.json", "task_id": "t1"},
            },
            {
                "capability": "governance_and_trust",
                "arm_type": "skill_ablation",
                "skill_id": "a-first",
                "row_id": "gov::t1::skill",
                "task_ref": {"manifest": "gov.json", "task_id": "t1"},
            },
        ],
    }
    catalog = {
        "skill_verdicts": [
            {"capability": "governance_and_trust", "skill_id": "z-last", "verdict": "reject"},
            {"capability": "governance_and_trust", "skill_id": "a-first", "verdict": "needs_more_data"},
        ],
    }

    index = SkillFitRowIndex.from_run_summary(summary, catalog, capability="governance_and_trust")

    assert index.capability == "governance_and_trust"
    assert [row["row_id"] for row in index.rows] == [
        "gov::t2::skill",
        "gov::t1::capability_only",
        "gov::t1::skill",
    ]
    assert index.baseline_by_task["gov.json::t1"]["row_id"] == "gov::t1::capability_only"
    assert index.skill_ids == ("a-first", "z-last")
    assert [row["row_id"] for row in index.rows_by_skill["a-first"]] == ["gov::t1::skill"]
    assert index.catalog_by_skill["a-first"]["verdict"] == "needs_more_data"
    assert isinstance(index.rows, tuple)
    assert isinstance(index.rows_by_skill["z-last"], tuple)


def test_research_candidate_v2_report_excludes_rejected_and_selects_source_discipline_candidates():
    pool = {
        "schema": "nexus.fair_skill_candidate_pool.v1",
        "source_status_report_schema": "nexus.skill_status.v1",
        "candidates": [
            {
                "skill_id": "browserbase-search",
                "source_root": "agents",
                "source_type": "reference",
                "path": "/skills/browserbase-search/SKILL.md",
                "sha256": "a",
                "capability_candidates": ["research_and_source_discipline"],
                "ablation_eligible": True,
                "runtime_eligible": False,
                "safety_status": "ablation_only",
                "load_when": "Search the web.",
                "evidence_refs": ["status"],
            },
            {
                "skill_id": "gbrain-data-research",
                "source_root": "agents",
                "source_type": "reference",
                "path": "/skills/gbrain-data-research/SKILL.md",
                "sha256": "b",
                "capability_candidates": ["research_and_source_discipline"],
                "ablation_eligible": True,
                "runtime_eligible": False,
                "safety_status": "ablation_only",
                "load_when": "Search sources, archive raw sources, keep a canonical tracker, deduplicate structured data evidence.",
                "evidence_refs": ["status"],
            },
            {
                "skill_id": "browserbase-company-research-2",
                "source_root": "agents",
                "source_type": "reference",
                "path": "/skills/company/SKILL.md",
                "sha256": "c",
                "capability_candidates": ["research_and_source_discipline"],
                "ablation_eligible": True,
                "runtime_eligible": False,
                "safety_status": "ablation_only",
                "load_when": "Company research for sales ICP with Browserbase automation.",
                "evidence_refs": ["status"],
            },
            {
                "skill_id": "wrong-skill",
                "source_root": "agents",
                "source_type": "quarantine",
                "path": "/skills/wrong/SKILL.md",
                "sha256": "d",
                "capability_candidates": ["planning_and_handoff"],
                "ablation_eligible": False,
                "runtime_eligible": False,
                "safety_status": "quarantined",
                "load_when": "Planning only.",
                "evidence_refs": ["status"],
            },
        ],
    }
    previous_catalog = {
        "skill_verdicts": [
            {
                "capability": "research_and_source_discipline",
                "skill_id": "browserbase-search",
                "verdict": "reject",
            }
        ]
    }

    report = build_research_candidate_v2_report(pool, previous_catalog, max_candidates=2)

    assert report["status"] == "PASS"
    assert report["runtime_update_allowed"] is False
    assert [item["skill_id"] for item in report["selected_candidates"]] == ["gbrain-data-research"]
    skipped = {item["skill_id"]: item["candidate_decision"] for item in report["skipped_candidates"]}
    assert skipped["browserbase-search"] == "skip_previously_rejected"
    assert skipped["browserbase-company-research-2"] == "skip_platform_or_sales_heavy"
    assert report["candidate_pool_v2"]["summary"]["selected_candidate_count"] == 1
    assert report["candidate_pool_v2"]["summary"]["negative_control_count"] == 1


def test_research_candidate_v3_requires_observable_source_discipline_behaviors():
    pool = {
        "schema": "nexus.fair_skill_candidate_pool.v1",
        "source_status_report_schema": "nexus.skill_status.v1",
        "candidates": [
            {
                "skill_id": "generic-research",
                "source_root": "agents",
                "source_type": "reference",
                "path": "/skills/generic-research/SKILL.md",
                "sha256": "a",
                "capability_candidates": ["research_and_source_discipline"],
                "ablation_eligible": True,
                "runtime_eligible": False,
                "safety_status": "ablation_only",
                "load_when": "Search the web and summarize general research.",
                "evidence_refs": ["status"],
            },
            {
                "skill_id": "source-discipline-audit",
                "source_root": "agents",
                "source_type": "reference",
                "path": "/skills/source-discipline-audit/SKILL.md",
                "sha256": "b",
                "capability_candidates": ["research_and_source_discipline"],
                "ablation_eligible": True,
                "runtime_eligible": False,
                "safety_status": "ablation_only",
                "load_when": "Build a citation chain, resolve source conflict, and keep raw source provenance for source validation.",
                "evidence_refs": ["status"],
            },
            {
                "skill_id": "wrong-skill",
                "source_root": "agents",
                "source_type": "quarantine",
                "path": "/skills/wrong/SKILL.md",
                "sha256": "c",
                "capability_candidates": ["planning_and_handoff"],
                "ablation_eligible": False,
                "runtime_eligible": False,
                "safety_status": "quarantined",
                "load_when": "Planning only.",
                "evidence_refs": ["status"],
            },
        ],
    }
    previous_catalog = {"skill_verdicts": []}

    report = build_research_candidate_v3_report(pool, previous_catalog, max_candidates=2)

    assert report["status"] == "PASS"
    assert report["runtime_update_allowed"] is False
    assert [item["skill_id"] for item in report["selected_candidates"]] == ["source-discipline-audit"]
    selected = report["selected_candidates"][0]
    assert selected["behavior_group_count"] == 3
    skipped = {item["skill_id"]: item["candidate_decision"] for item in report["skipped_candidates"]}
    assert skipped["generic-research"] == "skip_missing_observable_source_discipline_behavior"
    assert report["candidate_pool_v3"]["summary"]["negative_control_count"] == 1


def test_research_skill_supply_gap_contract_blocks_rejected_reuse_and_defines_ingest_guard():
    pool = {
        "schema": "nexus.fair_skill_candidate_pool.v1",
        "candidates": [
            {
                "skill_id": "gbrain-academic-verify",
                "source_root": "agents",
                "source_type": "reference",
                "path": "/skills/gbrain-academic-verify/SKILL.md",
                "capability_candidates": ["research_and_source_discipline"],
                "ablation_eligible": True,
                "runtime_eligible": False,
                "safety_status": "ablation_only",
                "load_when": "Verify academic source citations.",
            },
            {
                "skill_id": "blogwatcher",
                "source_root": "hermes",
                "source_type": "reference",
                "path": "/skills/blogwatcher/SKILL.md",
                "capability_candidates": ["research_and_source_discipline"],
                "ablation_eligible": True,
                "runtime_eligible": False,
                "safety_status": "ablation_only",
                "load_when": "Watch blogs and summarize source updates.",
            },
        ],
    }
    v1_catalog = {
        "skill_verdicts": [
            {
                "capability": "research_and_source_discipline",
                "skill_id": "gbrain-academic-verify",
                "verdict": "reject",
            }
        ]
    }
    v3_report = {"summary": {"selected_candidate_count": 0}}

    contract = build_research_skill_supply_gap_contract(pool, [v1_catalog], v3_report=v3_report)

    decisions = {item["skill_id"]: item["decision"] for item in contract["candidate_decisions"]}
    assert contract["status"] == "PASS"
    assert contract["research_live_allowed"] is False
    assert contract["summary"]["ready_candidate_count"] == 0
    assert "gbrain-academic-verify" in contract["rejected_existing_candidate_ids"]
    assert decisions["gbrain-academic-verify"] == "already_rejected_do_not_rerun"
    assert decisions["blogwatcher"] == "supply_gap_missing_observable_source_discipline_behavior"
    assert contract["github_ingest_guard"]["runtime_mount_allowed"] is False
    assert len(contract["creation_specs"]) == 3


def test_research_source_discipline_specs_keep_live_blocked_until_v3_candidates_exist():
    supply_gap = {
        "status": "PASS",
        "summary": {"supply_gap": True},
        "creation_specs": [
            {
                "skill_id": "research-citation-chain-verifier",
                "behavior_groups": ["citation_chain", "source_validation"],
                "required_receipts": ["claim_to_source_refs"],
            }
        ],
        "github_ingest_guard": {
            "lane": "external_candidate_pool_only",
            "runtime_mount_allowed": False,
            "required_checks": ["commit_sha_pinned"],
        },
    }

    contract = build_research_source_discipline_skill_specs(supply_gap)

    assert contract["status"] == "PASS"
    assert contract["research_live_allowed"] is False
    assert contract["runtime_update_allowed"] is False
    assert contract["summary"]["creation_spec_count"] == 1
    assert contract["external_ingest_guard"]["runtime_mount_allowed"] is False


def test_research_external_ingest_guard_is_candidate_pool_only():
    source_specs = {
        "required_behavior_groups": ["citation_chain", "source_validation"],
        "external_ingest_guard": {
            "runtime_mount_allowed": False,
            "required_fields": ["source_url", "commit_sha", "license", "security_receipt"],
            "required_checks": ["commit_sha_pinned", "license_allowlist_pass"],
            "fail_fast": ["unversioned_external_source"],
        },
    }

    guard = build_research_external_ingest_guard(source_specs)

    assert guard["status"] == "PASS"
    assert guard["runtime_update_allowed"] is False
    assert guard["candidate_pool_update_allowed"] is True
    assert guard["network_fetch_performed"] is False
    assert guard["summary"]["ingested_candidate_count"] == 0


def test_research_external_candidate_pool_generates_v3_selectable_metadata_only_candidates():
    source_specs = {
        "creation_specs": [
            {
                "skill_id": "research-citation-chain-verifier",
                "behavior_groups": ["citation_chain", "source_validation"],
                "load_when": "Load when citation chain and source validation are required.",
                "required_receipts": ["claim_to_source_refs"],
            }
        ]
    }

    pool = build_research_external_candidate_pool(source_specs)
    report = build_research_candidate_v3_report(pool, {"skill_verdicts": []})

    assert pool["status"] == "PASS"
    assert pool["summary"]["candidate_count"] == 1
    assert pool["candidates"][0]["runtime_eligible"] is False
    assert pool["candidates"][0]["ablation_eligible"] is True
    assert report["status"] == "PASS"
    assert report["summary"]["selected_candidate_count"] == 1


def test_research_external_candidate_pool_preserves_source_specs_ref():
    source_specs = {
        "creation_specs": [
            {
                "skill_id": "research-citation-chain-verifier",
                "behavior_groups": ["citation_chain", "source_validation"],
                "load_when": "Load when citation chain and source validation are required.",
                "required_receipts": ["claim_to_source_refs"],
            }
        ]
    }

    pool = build_research_external_candidate_pool(source_specs, source_specs_ref="docs/reports/specs-current.json")

    assert pool["candidates"][0]["source_url"] == (
        "local-spec://docs/reports/specs-current.json#research-citation-chain-verifier"
    )


def test_governance_candidate_v2_report_selects_policy_and_audit_candidates():
    pool = {
        "schema": "nexus.fair_skill_candidate_pool.v1",
        "source_status_report_schema": "nexus.skill_status.v1",
        "candidates": [
            {
                "skill_id": "old-root-cause",
                "source_root": "nexus_repo",
                "source_type": "nexus_local",
                "path": "/skills/old-root-cause/SKILL.md",
                "sha256": "a",
                "capability_candidates": ["governance_and_trust"],
                "ablation_eligible": True,
                "runtime_eligible": True,
                "safety_status": "runtime_reviewed",
                "load_when": "Root cause governance incidents.",
                "evidence_refs": ["status"],
            },
            {
                "skill_id": "claim-audit-hardening",
                "source_root": "agents",
                "source_type": "reference",
                "path": "/skills/claim-audit-hardening/SKILL.md",
                "sha256": "b",
                "capability_candidates": ["governance_and_trust"],
                "ablation_eligible": True,
                "runtime_eligible": False,
                "safety_status": "ablation_only",
                "load_when": "Audit trust claims, evidence paths, policy boundaries, and fail-closed governance.",
                "evidence_refs": ["status"],
            },
            {
                "skill_id": "brand-creative",
                "source_root": "agents",
                "source_type": "reference",
                "path": "/skills/brand-creative/SKILL.md",
                "sha256": "c",
                "capability_candidates": ["governance_and_trust"],
                "ablation_eligible": True,
                "runtime_eligible": False,
                "safety_status": "ablation_only",
                "load_when": "Creative image and canvas work.",
                "evidence_refs": ["status"],
            },
            {
                "skill_id": "wrong-skill",
                "source_root": "agents",
                "source_type": "quarantine",
                "path": "/skills/wrong/SKILL.md",
                "sha256": "d",
                "capability_candidates": ["research_and_source_discipline"],
                "ablation_eligible": False,
                "runtime_eligible": False,
                "safety_status": "quarantined",
                "load_when": "Research only.",
                "evidence_refs": ["status"],
            },
        ],
    }
    previous_catalog = {
        "skill_verdicts": [
            {"capability": "governance_and_trust", "skill_id": "old-root-cause", "verdict": "reject"}
        ]
    }

    report = build_governance_candidate_v2_report(pool, previous_catalog, max_candidates=2)

    assert report["status"] == "PASS"
    assert report["runtime_update_allowed"] is False
    assert [item["skill_id"] for item in report["selected_candidates"]] == ["claim-audit-hardening"]
    skipped = {item["skill_id"]: item["candidate_decision"] for item in report["skipped_candidates"]}
    assert skipped["old-root-cause"] == "skip_previously_rejected"
    assert skipped["brand-creative"] == "skip_platform_or_unrelated_heavy"
    assert report["candidate_pool_v2"]["summary"]["negative_control_count"] == 1


def test_skill_fit_cost_phase_contract_separates_cost_from_delivery_claims():
    summary = {
        "results": [
            {
                "capability": "governance_and_trust",
                "arm_type": "skill_ablation",
                "skill_id": "claim-audit-hardening",
                "row_id": "r1",
                "status": "PASS",
                "task_ref": {"task_id": "t1"},
                "benchmark_row": {
                    "wall_duration_sec": 10,
                    "total_tokens": 100,
                    "model_calls": 1,
                    "phase_wall_p_sec": 2,
                    "phase_wall_r_sec": 8,
                },
                "ablation_gate": {"status": "PASS"},
                "ablation_gate_row": {
                    "status": "KEEP",
                    "evidence_path": "e.json",
                    "receipt_path": "receipt",
                    "trust_mismatch": False,
                },
            },
            {
                "capability": "governance_and_trust",
                "arm_type": "skill_ablation",
                "skill_id": "claim-audit-hardening",
                "row_id": "r2",
                "status": "PASS",
                "task_ref": {"task_id": "t2"},
                "benchmark_row": {
                    "wall_duration_sec": 20,
                    "total_tokens": 300,
                    "model_calls": 2,
                    "phase_wall_p_sec": 10,
                    "phase_wall_r_sec": 5,
                },
                "ablation_gate": {"status": "PASS"},
                "ablation_gate_row": {"status": "RETURN", "trust_mismatch": False},
            },
        ]
    }
    catalog = {
        "skill_verdicts": [
            {"capability": "governance_and_trust", "skill_id": "claim-audit-hardening", "verdict": "needs_more_data"}
        ]
    }

    contract = build_skill_fit_cost_phase_contract(summary, catalog, capability="governance_and_trust")

    skill = contract["skill_costs"][0]
    assert contract["status"] == "PASS"
    assert skill["wall_sec"] == 30
    assert skill["tokens"] == 400
    assert skill["model_calls"] == 3
    assert skill["cost_per_effective_row"]["tokens"] == 400
    assert skill["dominant_phase"] == "R"
    assert "delivery improvement claims" in contract["claim_boundary"][1]


def test_skill_fit_redesign_contract_blocks_flash_for_all_rejected_research_and_small_governance():
    research_catalog = {
        "summary": {"capability_only_rows": 22},
        "skill_verdicts": [
            {"capability": "research_and_source_discipline", "skill_id": "r1", "verdict": "reject"},
            {"capability": "research_and_source_discipline", "skill_id": "r2", "verdict": "reject"},
        ],
    }
    governance_catalog = {
        "summary": {"capability_only_rows": 5},
        "skill_verdicts": [
            {"capability": "governance_and_trust", "skill_id": "g1", "verdict": "reject"},
            {"capability": "governance_and_trust", "skill_id": "g2", "verdict": "needs_more_data"},
        ],
    }

    contract = build_skill_fit_redesign_contract({"research": research_catalog, "governance": governance_catalog})

    actions = {item["capability"]: item["recommended_action"] for item in contract["capability_actions"]}
    assert contract["status"] == "PASS"
    assert contract["flash100_allowed"] is False
    assert actions["research_and_source_discipline"] == "research_candidate_v3_required"
    assert actions["governance_and_trust"] == "governance_taskset_expansion_required"


def test_governance_taskset_expansion_contract_reports_bucket_gaps():
    manifests = {
        "m1.json": {
            "tasks": [
                {
                    "id": "redaction-001",
                    "category": "refactor",
                    "fixture_kind": "secret_redaction",
                    "task_desc": "Preserve credential redaction.",
                    "expected_capabilities": ["mempalace_gate", "claim_gate"],
                },
                {
                    "id": "auth-001",
                    "category": "refactor",
                    "fixture_kind": "auth_scope",
                    "task_desc": "Deny missing scopes and unsafe operations.",
                    "expected_capabilities": ["mempalace_gate"],
                },
                {
                    "id": "claim-001",
                    "category": "feature",
                    "fixture_kind": "claim_replay",
                    "task_desc": "Reject unsupported claim receipts without replay.",
                    "expected_capabilities": ["artifact_gate", "claim_gate"],
                },
                {
                    "id": "evidence-001",
                    "category": "feature",
                    "fixture_kind": "evidence_report",
                    "task_desc": "Verify evidence artifact path and report source.",
                    "expected_capabilities": ["artifact_gate"],
                },
            ]
        }
    }

    contract = build_governance_taskset_expansion_contract(
        manifests,
        min_total_tasks=15,
        max_total_tasks=20,
        min_tasks_per_bucket=3,
    )

    assert contract["status"] == "PASS"
    assert contract["live_ready"] is False
    assert contract["preflight_status"] == "BLOCKED_UNTIL_TASKS_MATERIALIZED"
    assert contract["summary"]["selected_existing_task_count"] == 4
    assert contract["summary"]["proposed_new_task_count"] > 0
    proposed_buckets = {item["bucket"] for item in contract["proposed_new_task_specs"]}
    assert {"audit", "redaction", "auth", "claim_gate", "evidence_review"}.issubset(proposed_buckets)


def test_governance_mutant_lane_contract_requires_live_ready_taskset_and_mutants():
    taskset_contract = {
        "live_ready": True,
        "summary": {
            "bucket_counts": {
                "audit": 1,
                "redaction": 1,
                "auth": 1,
                "claim_gate": 1,
                "evidence_review": 1,
            }
        },
        "selected_existing_tasks": [
            {
                "manifest": "m.json",
                "task_id": "audit-001",
                "category": "audit",
                "fixture_kind": "ultra_review",
                "task_desc": "Review audit finding evidence.",
                "expected_capabilities": ["ultra_review"],
                "governance_buckets": ["audit"],
            },
            {
                "manifest": "m.json",
                "task_id": "redaction-001",
                "category": "refactor",
                "fixture_kind": "secret_redaction",
                "task_desc": "Preserve credential secret redaction.",
                "expected_capabilities": ["mempalace_gate"],
                "governance_buckets": ["redaction"],
            },
            {
                "manifest": "m.json",
                "task_id": "auth-001",
                "category": "refactor",
                "fixture_kind": "auth_scope",
                "task_desc": "Deny missing scopes and unsafe operations.",
                "expected_capabilities": ["mempalace_gate"],
                "governance_buckets": ["auth"],
            },
            {
                "manifest": "m.json",
                "task_id": "claim-001",
                "category": "feature",
                "fixture_kind": "claim_replay",
                "task_desc": "Reject unsupported claim receipts without replay.",
                "expected_capabilities": ["artifact_gate", "claim_gate"],
                "governance_buckets": ["claim_gate"],
            },
            {
                "manifest": "m.json",
                "task_id": "evidence-001",
                "category": "feature",
                "fixture_kind": "evidence_report",
                "task_desc": "Verify evidence artifact path and report source.",
                "expected_capabilities": ["artifact_gate"],
                "governance_buckets": ["evidence_review"],
            },
        ],
    }

    contract = build_governance_mutant_lane_contract(taskset_contract)

    assert contract["status"] == "PASS"
    assert contract["live_ready"] is True
    assert contract["summary"]["mutant_count"] == 5
    assert {item["bucket"] for item in contract["mutants"]} == {
        "audit",
        "redaction",
        "auth",
        "claim_gate",
        "evidence_review",
    }
    assert "cannot update runtime policy" in contract["promotion_rule"][2]


def test_governance_mutant_matrix_preflight_and_promotion_gate_fail_closed_without_live_kills():
    taskset_contract = {
        "live_ready": True,
        "selected_existing_tasks": [
            {"task_id": "governance-expansion-audit-003"},
            {"task_id": "governance-expansion-redaction-002"},
            {"task_id": "governance-expansion-redaction-003"},
        ],
    }
    mutant_lane = {
        "status": "PASS",
        "mutants": [
            {
                "mutant_id": "audit-1::forged_pass_without_independent_audit",
                "source_task_id": "governance-expansion-audit-003",
                "bucket": "audit",
                "mutant_kind": "forged_pass_without_independent_audit",
                "required_receipts": [
                    "mutant_source_task_ref",
                    "gate_decision",
                    "reason_code",
                    "evidence_path",
                ],
            }
        ],
    }

    matrix = build_governance_mutant_matrix_preflight(mutant_lane, taskset_contract)
    gate = build_governance_mutant_promotion_gate(matrix)
    live = build_governance_mutant_live_sealing(matrix)

    assert matrix["status"] == "PASS"
    assert matrix["lane_reference_gate"]["missing_required_task_ids"] == []
    assert matrix["lane_reference_gate"]["commercial_50_denominator_mutation_allowed"] is False
    assert live["status"] == "PASS"
    assert live["summary"]["sealed_row_count"] == 1
    assert live["summary"]["candidate_bound_kill_evidence_count"] == 0
    assert live["promotion_allowed"] is False
    assert gate["status"] == "PASS"
    assert gate["gate_verdict"] == "RETURN"
    assert gate["promotion_allowed"] is False
    assert gate["summary"]["missing_live_kill_evidence_count"] == 1


def test_governance_candidate_bound_mutant_matrix_and_catalog_require_skill_binding():
    mutant_matrix = {
        "status": "PASS",
        "rows": [
            {
                "row_id": "governance_mutant::audit-1",
                "source_manifest": "scripts/bench/public_benchmark_commercial_expansion_v1.json",
                "source_task_id": "governance-expansion-audit-003",
                "bucket": "audit",
                "mutant_kind": "forged_pass_without_independent_audit",
            }
        ],
    }
    candidate_report = {
        "selected_candidates": [
            {
                "skill_id": "acceptance-evidence-failclosed",
                "source_root": "agents",
                "runtime_eligible": False,
                "ablation_eligible": True,
            }
        ]
    }

    matrix = build_governance_candidate_bound_mutant_matrix(mutant_matrix, candidate_report)
    catalog = build_governance_candidate_bound_mutant_catalog(
        {
            "results": [
                {
                    "skill_id": "acceptance-evidence-failclosed",
                    "status": "PASS",
                    "trust_mismatch": False,
                    "evidence_path": "evidence.json",
                }
            ]
        }
    )

    assert matrix["status"] == "PASS"
    assert matrix["summary"]["row_count"] == 1
    assert matrix["rows"][0]["skill_mount_requests"] == ["acceptance-evidence-failclosed"]
    assert "NEXUS_GOVERNANCE_MUTANT_KIND" in matrix["rows"][0]["runner_env"]
    assert catalog["promotion_allowed"] is True
    assert catalog["skill_verdicts"][0]["verdict"] == "alternate"
