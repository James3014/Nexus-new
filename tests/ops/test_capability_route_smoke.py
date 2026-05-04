from __future__ import annotations

import json
from pathlib import Path

from scripts.ops import capability_route_smoke


def test_build_command_keeps_manifest_and_max_tasks_order():
    suite = capability_route_smoke.SMOKE_SUITES[0]
    cmd = capability_route_smoke.build_command(Path("."), suite)

    assert cmd[1] == "scripts/bench/capability_ab_runner.py"
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
