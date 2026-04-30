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
            "expected_capability_receipt_coverage": {
                "expected": ["hyper"],
                "public_safe": ["hyper"],
                "missing": [],
                "failure_reasons": {},
            },
        },
        {
            "task_id": "missing",
            "status": "SUCCESS",
            "semantic_status": "VERIFIED",
            "expected_capability_receipt_coverage": {
                "expected": ["memory"],
                "public_safe": [],
                "missing": ["memory"],
                "failure_reasons": {"memory": "missing_receipt"},
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
        }
    ]


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
