"""Gating tests: durable Armor artifact storage + receipt replay."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from nexus.services.local_heal.armor_artifact_storage import (
    ENV_ARMOR_ALLOW_EPHEMERAL,
    ENV_ARMOR_ARTIFACT_ROOT,
    assert_durable_path,
    default_local_heal_reports_root,
    is_ephemeral_path,
    load_decision_for_replay,
    make_isolated_workspace,
    reconstruct_decision_from_receipt,
    resolve_armor_artifact_root,
    resolve_repro_script_dir,
)
from nexus.services.local_heal.pipeline import HealContext
from nexus.services.local_heal.receipt import replay_repair_decision, write_repair_receipt


def test_default_reports_root_is_workspace_relative(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_ARMOR_ARTIFACT_ROOT, raising=False)
    root = default_local_heal_reports_root(workspace_root=tmp_path, env={})
    assert root == (tmp_path / ".nexus/reports/local_heal").resolve()


def test_artifact_root_env_override(tmp_path):
    target = tmp_path / "custom_artifacts"
    env = {
        ENV_ARMOR_ARTIFACT_ROOT: str(target),
        ENV_ARMOR_ALLOW_EPHEMERAL: "1",
    }
    root = resolve_armor_artifact_root(env=env)
    assert root == target.resolve()


def test_reject_ephemeral_artifact_root():
    system_tmp = Path(tempfile.gettempdir()).resolve()
    with pytest.raises(ValueError, match="ephemeral"):
        resolve_armor_artifact_root(
            env={ENV_ARMOR_ARTIFACT_ROOT: str(system_tmp)}
        )


def test_is_ephemeral_detects_system_temp():
    system_tmp = Path(tempfile.gettempdir()) / "armor-probe"
    assert is_ephemeral_path(system_tmp)


def test_make_isolated_workspace_under_parent(tmp_path):
    ws = make_isolated_workspace(work_dir=tmp_path / "iso", prefix="t-")
    assert ws.is_dir()
    assert ws.parent == (tmp_path / "iso").resolve()


def test_make_isolated_workspace_default_uses_artifact_root(tmp_path):
    art = tmp_path / "art"
    env = {
        ENV_ARMOR_ARTIFACT_ROOT: str(art),
        ENV_ARMOR_ALLOW_EPHEMERAL: "1",
    }
    ws = make_isolated_workspace(env=env)
    assert ws.is_dir()
    assert str(art.resolve()) in str(ws.resolve())


def test_repro_script_dir_under_artifact_root(tmp_path):
    art = tmp_path / "art"
    env = {
        ENV_ARMOR_ARTIFACT_ROOT: str(art),
        ENV_ARMOR_ALLOW_EPHEMERAL: "1",
    }
    directory = resolve_repro_script_dir(env=env)
    assert directory.is_dir()
    assert "repro" in str(directory)
    assert str(art.resolve()) in str(directory.resolve())


def test_write_repair_receipt_lands_and_replays(tmp_path):
    reports_root = tmp_path / "reports" / "local_heal"
    ctx = HealContext(
        instance_id="armor-durability-task-001",
        repo_dir=tmp_path,
        problem_statement="prove durable receipt + replay",
        final_patch="--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-a\n+b\n",
        repro_evidence="AssertionError: bug",
        evaluation_report="=== VISIBLE ===\n[PASS]\n",
        reproduced=True,
        hidden_verifier_passed=True,
        runner_completed=True,
        solve_eligible=True,
        model_decisions=[
            {
                "phase": "patch",
                "model": "qwen2.5-coder:7b",
                "timeout_seconds": 60,
            }
        ],
    )
    receipt_path = write_repair_receipt(
        ctx,
        model_name="qwen2.5-coder:7b",
        reports_root=reports_root,
    )

    assert receipt_path.is_file()
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert payload["schema"] == "nexus.local_heal.repair_receipt.v1"
    assert payload["artifact_storage"] == "nexus_workspace_durable"
    assert payload["final_receipt_path"]

    decision = replay_repair_decision(receipt_path)
    assert decision["task_id"] == "armor-durability-task-001"
    assert decision["verifier_result"] in ("pass", "fail", "blocked", "not_run")
    assert "routing" in decision
    assert decision["claim_boundary"]["public_claim_allowed"] is False
    assert isinstance(decision["model_decisions"], list)


def test_reconstruct_decision_from_receipt_in_memory():
    receipt = {
        "schema": "nexus.local_heal.repair_receipt.v1",
        "task_id": "t-replay",
        "instance_id": "t-replay",
        "gate_passed": False,
        "solve_eligible": False,
        "failure_reason": "VERIFICATION_FAILED",
        "evidence_refs": ["patch.diff"],
        "telemetries": {
            "model_decisions": [{"phase": "patch", "model": "qwen"}],
            "local_armor_execution_profile": "STANDARD",
        },
        "latency_ledger": {"total_ms": 12},
        "public_claim_allowed": False,
        "production_ready": False,
    }
    decision = reconstruct_decision_from_receipt(receipt)
    assert decision["task_id"] == "t-replay"
    assert decision["verifier_result"] == "fail"
    assert decision["routing"]["local_armor_execution_profile"] == "STANDARD"
    assert decision["latency_ledger"]["total_ms"] == 12
    assert decision["replayable"] is True


def test_assert_durable_path_blocks_tmp():
    with pytest.raises(ValueError, match="durable"):
        assert_durable_path(Path(tempfile.gettempdir()) / "bad", label="reports_root")


def test_load_decision_reconstructs_and_flags_ephemeral_source(tmp_path):
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(
        json.dumps(
            {
                "schema": "nexus.local_heal.repair_receipt.v1",
                "task_id": "eph",
                "instance_id": "eph",
                "gate_passed": True,
                "evidence_refs": [],
            }
        ),
        encoding="utf-8",
    )
    decision = load_decision_for_replay(receipt_path)
    assert decision["task_id"] == "eph"
    assert decision["source_is_ephemeral"] is True
    assert decision["replayable"] is False
    assert "source_path_ephemeral" in decision.get("replay_missing_fields", [])
