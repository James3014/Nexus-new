from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from scripts.ops import capability_route_smoke


def test_build_command_keeps_manifest_and_max_tasks_order():
    suite = capability_route_smoke.SMOKE_SUITES[0]
    cmd = capability_route_smoke.build_command(Path("."), suite)

    assert cmd[:4] == ["uv", "run", "python", "scripts/bench/capability_ab_runner.py"]
    assert cmd[cmd.index("--tasks-file") + 1] == "scripts/bench/public_benchmark_route_oracles_v1.json"
    assert cmd[cmd.index("--max-tasks") + 1] == "8"
    assert cmd[cmd.index("--task-id-filter") + 1].startswith("route-oracle-autoreason-001,")
    assert "--with-llm-mode" in cmd
    assert cmd[cmd.index("--with-llm-mode") + 1] == "off"


def test_smoke_suites_cover_core_governance_and_belief_gates():
    suites = {suite.name: suite for suite in capability_route_smoke.SMOKE_SUITES}

    assert "core_governance_gates" in suites
    assert suites["core_governance_gates"].task_ids == (
        "nexus-value-gov-001",
        "nexus-value-evidence-001",
    )
    assert "belief_gate" in suites
    assert suites["belief_gate"].task_ids == ("rlm-harder-v2-belief-001",)


def test_summarize_jsonl_requires_success_verified_and_public_safe_receipts(tmp_path: Path):
    path = tmp_path / "with_nexus_1.jsonl"
    rows = [
        {
            "task_id": "ok",
            "status": "SUCCESS",
            "semantic_status": "VERIFIED",
            "route_decision_schema_version": "nexus_route_decision_v1",
            "route_decision_selected_count": 3,
            "route_decision_invoked_count": 3,
            "route_decision_evidence_count": 3,
            "route_decision_outcome_count": 3,
            "brain_hub_guidance_present": True,
            "brain_hub_guidance_audit_passed": True,
            "expected_capability_receipt_coverage": {
                "expected": ["hyper"],
                "public_safe": ["hyper"],
                "missing": [],
                "failure_reasons": {},
                "all_public_safe": True,
            },
        },
        {
            "task_id": "missing",
            "status": "SUCCESS",
            "semantic_status": "VERIFIED",
            "route_decision_schema_version": "nexus_route_decision_v1",
            "route_decision_selected_count": 3,
            "route_decision_invoked_count": 2,
            "route_decision_evidence_count": 2,
            "route_decision_outcome_count": 2,
            "expected_capability_receipt_coverage": {
                "expected": ["memory"],
                "public_safe": [],
                "missing": ["memory"],
                "failure_reasons": {"memory": "missing_receipt"},
                "all_public_safe": False,
            },
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    out = capability_route_smoke.summarize_jsonl(path)

    assert out["tasks"] == 2
    assert out["expected_capabilities"] == ["hyper", "memory"]
    assert out["public_safe_capabilities"] == ["hyper"]
    assert out["route_quality"]["selected_total"] == 6
    assert out["route_quality"]["invoked_total"] == 5
    assert out["brain_hub_guidance"]["present_total"] == 1
    assert out["brain_hub_guidance"]["audit_passed_total"] == 1
    assert out["failures"] == [
        {
            "task_id": "missing",
            "status": "SUCCESS",
            "semantic_status": "VERIFIED",
            "missing": ["memory"],
            "failure_reasons": {"memory": "missing_receipt"},
            "row_failures": [
                "expected_capability_not_public_safe",
                "expected_capability_coverage_incomplete",
            ],
        }
    ]


def test_summarize_jsonl_route_quality_uses_actionable_receipts(tmp_path: Path):
    path = tmp_path / "with_nexus_1.jsonl"
    row = {
        "task_id": "ok",
        "status": "SUCCESS",
        "semantic_status": "VERIFIED",
        "route_decision_schema_version": "nexus_route_decision_v1",
        "route_decision_selected_count": 18,
        "route_decision_invoked_count": 0,
        "route_decision_evidence_count": 0,
        "route_decision_outcome_count": 0,
        "expected_capability_receipt_coverage": {
            "expected": ["artifact_gate"],
            "public_safe": ["artifact_gate"],
            "missing": [],
            "failure_reasons": {},
            "all_public_safe": True,
        },
        "capability_receipts": [
            {
                "name": "artifact_gate",
                "selected": True,
                "invoked": True,
                "evidence_present": True,
                "gate_passed": True,
                "outcome_contributed": True,
                "public_claim_safe": True,
            },
            {
                "name": "acceptance_check",
                "selected": True,
                "invoked": False,
                "evidence_present": False,
                "gate_passed": False,
                "outcome_contributed": False,
            },
            {
                "name": "ultra_review",
                "selected": True,
                "invoked": False,
                "evidence_present": False,
                "gate_passed": False,
                "outcome_contributed": False,
                "failure_reason": "feature_flag_disabled",
            },
        ],
    }
    path.write_text(json.dumps(row), encoding="utf-8")

    out = capability_route_smoke.summarize_jsonl(path)

    assert out["route_quality"]["selected_total"] == 1
    assert out["route_quality"]["invoked_total"] == 1
    assert out["route_quality"]["evidence_total"] == 1
    assert out["route_quality"]["outcome_total"] == 1


def test_summarize_jsonl_fails_when_route_decision_missing(tmp_path: Path):
    path = tmp_path / "with_nexus_1.jsonl"
    row = {
        "task_id": "legacy-looking",
        "status": "SUCCESS",
        "semantic_status": "VERIFIED",
        "expected_capability_receipt_coverage": {
            "expected": ["hyper"],
            "public_safe": ["hyper"],
            "missing": [],
            "failure_reasons": {},
            "all_public_safe": True,
        },
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    out = capability_route_smoke.summarize_jsonl(path)

    assert out["failures"][0]["task_id"] == "legacy-looking"
    assert out["failures"][0]["row_failures"] == ["route_decision_missing", "route_decision_empty"]


def test_summarize_jsonl_fails_when_legacy_override_detected(tmp_path: Path):
    path = tmp_path / "with_nexus_1.jsonl"
    row = {
        "task_id": "legacy-override",
        "status": "SUCCESS",
        "semantic_status": "VERIFIED",
        "route_decision_schema_version": "nexus_route_decision_v1",
        "route_decision_selected_count": 2,
        "legacy_override_detected": True,
        "expected_capability_receipt_coverage": {
            "expected": ["hyper"],
            "public_safe": ["hyper"],
            "missing": [],
            "failure_reasons": {},
            "all_public_safe": True,
        },
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    out = capability_route_smoke.summarize_jsonl(path)

    assert out["failures"][0]["task_id"] == "legacy-override"
    assert out["failures"][0]["row_failures"] == ["legacy_override_detected"]


def test_latest_with_nexus_file_excludes_stale_outputs(tmp_path: Path):
    old = tmp_path / "with_nexus_1.jsonl"
    new = tmp_path / "with_nexus_2.jsonl"
    old.write_text("{}\n", encoding="utf-8")
    new.write_text("{}\n", encoding="utf-8")

    assert capability_route_smoke.latest_with_nexus_file(tmp_path, exclude={old}) == new


def test_run_suite_marks_uv_cache_permission_as_infra_invalid(tmp_path: Path, monkeypatch):
    suite = capability_route_smoke.SmokeSuite(
        name="route_oracles",
        manifest="manifest.json",
        output_dir="out",
        task_ids=("t1",),
    )

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(
            returncode=2,
            stdout="",
            stderr="error: failed to open file `/Users/a/.cache/uv/sdists-v9/.git`: Operation not permitted",
        )

    monkeypatch.setattr(capability_route_smoke.subprocess, "run", fake_run)

    summary = capability_route_smoke.run_suite(tmp_path, suite, print_only=False)

    assert summary["infra_invalid"] is True
    assert summary["infra_invalid_reason"] == "uv_cache_permission_denied"
    assert summary["failures"][0]["row_failures"] == ["route_smoke_infra_invalid"]


def test_smoke_env_adds_repo_root_to_pythonpath(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "existing")

    env = capability_route_smoke.smoke_env(tmp_path)

    assert env["NEXUS_ENABLE_SWARM_BENCH_EXECUTOR"] == "1"
    assert env["PYTHONPATH"].startswith(str(tmp_path))
    assert env["PYTHONPATH"].endswith("existing")


def test_nine_capability_identity_union_passes_for_route_oracles_plus_belief(tmp_path: Path):
    summaries = [
        {
            "suite": "route_oracles",
            "expected_capabilities": [
                "autoreason",
                "ddtree",
                "ultra_review",
                "research",
                "lancedb",
                "swarm",
                "drone",
                "nightshift",
            ],
            "public_safe_capabilities": [
                "autoreason",
                "ddtree",
                "ultra_review",
                "research",
                "lancedb",
                "swarm",
                "drone",
                "nightshift",
            ],
            "failures": [],
        },
        {
            "suite": "belief_gate",
            "expected_capabilities": ["belief"],
            "public_safe_capabilities": ["belief"],
            "failures": [],
        },
    ]
    failures = capability_route_smoke.validate_nine_capability_identity(summaries)
    assert failures == []


def test_route_quality_gate_passes_on_thresholds():
    failures = capability_route_smoke.validate_route_quality_gate(
        [
            {
                "suite": "route_oracles",
                "route_quality": {
                    "selected_total": 20,
                    "invoked_total": 15,
                    "evidence_total": 15,
                    "outcome_total": 14,
                },
            }
        ]
    )
    assert failures == []


def test_route_quality_gate_fails_on_over_selection_and_low_funnel():
    failures = capability_route_smoke.validate_route_quality_gate(
        [
            {
                "suite": "route_oracles",
                "route_quality": {
                    "selected_total": 20,
                    "invoked_total": 10,
                    "evidence_total": 8,
                    "outcome_total": 6,
                },
            }
        ]
    )
    codes = {code for item in failures for code in (item.get("row_failures") or [])}
    assert "route_quality_selected_to_invoked_below_threshold" in codes
    assert "route_quality_invoked_to_evidence_below_threshold" in codes
    assert "route_quality_evidence_to_outcome_below_threshold" in codes
    assert "route_quality_unnecessary_selected_above_threshold" in codes


def test_brain_hub_guidance_gate_fails_when_missing_or_audit_failed():
    failures = capability_route_smoke.validate_brain_hub_guidance_gate(
        [
            {
                "suite": "route_oracles",
                "tasks": 2,
                "brain_hub_guidance": {
                    "present_total": 1,
                    "audit_passed_total": 0,
                },
            }
        ]
    )

    codes = {code for item in failures for code in (item.get("row_failures") or [])}
    assert "brain_hub_guidance_missing" in codes
    assert "brain_hub_guidance_audit_failed" in codes


def test_nine_capability_identity_union_fails_when_belief_missing():
    summaries = [
        {
            "suite": "route_oracles",
            "expected_capabilities": [
                "autoreason",
                "ddtree",
                "ultra_review",
                "research",
                "lancedb",
                "swarm",
                "drone",
                "nightshift",
            ],
            "public_safe_capabilities": [
                "autoreason",
                "ddtree",
                "ultra_review",
                "research",
                "lancedb",
                "swarm",
                "drone",
                "nightshift",
            ],
            "failures": [],
        },
        {
            "suite": "belief_gate",
            "expected_capabilities": [],
            "public_safe_capabilities": [],
            "failures": [],
        },
    ]
    failures = capability_route_smoke.validate_nine_capability_identity(summaries)
    failure_codes = {code for item in failures for code in (item.get("row_failures") or [])}
    assert "expected_capability_not_exact_nine" in failure_codes
    assert "public_safe_capability_not_exact_nine" in failure_codes
