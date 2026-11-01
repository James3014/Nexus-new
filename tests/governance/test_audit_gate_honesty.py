"""Gates must report 'not verified' instead of a fake pass (issue #1763 items 1-5)."""

import json
import logging
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from nexus.delivery.anti_drift import AntiDrift
from nexus.delivery.replay_runner import ReplayRunner
from nexus.governance.learning_gate import evaluate_learning_gate
from nexus.infrastructure.storage_implementations import LanceBeliefStore
from nexus.services.mem_palace import MemPalace

ROOT = Path(__file__).resolve().parents[2]


# --- item 1: learning gate ---------------------------------------------------
def test_learning_gate_without_evidence_is_unverified_not_pass(tmp_path):
    result = evaluate_learning_gate(tmp_path / "run", tmp_path)
    assert result.passed is False
    assert result.status == "UNVERIFIED"
    assert result.failure_reasons == ["no_outcome_evidence"]


def test_learning_gate_reads_the_metrics_path_the_writer_uses(tmp_path):
    metrics = tmp_path / ".nexus" / "metrics"
    metrics.mkdir(parents=True)
    event = {"pattern_reuse": 90, "next_run_hit": 90, "lesson_quality": 90}
    (metrics / "skill_outcome_events.jsonl").write_text(json.dumps(event) + "\n")
    result = evaluate_learning_gate(tmp_path / "run", tmp_path)
    assert result.passed is True
    assert result.status == "PASS"


def test_learning_gate_low_metrics_is_fail(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "outcome_event.json").write_text(json.dumps({"pattern_reuse": 1}))
    result = evaluate_learning_gate(run, tmp_path)
    assert result.passed is False
    assert result.status == "FAIL"


def test_health_policy_treats_unverified_gate_as_warning(tmp_path, monkeypatch):
    from nexus.core.state_contracts import NexusState
    from nexus.health.models import HealthSnapshot
    from nexus.health.policy import HealthTriggerPolicy

    gate = SimpleNamespace(
        passed=False, status="UNVERIFIED", failure_reasons=["no_outcome_evidence"]
    )
    monkeypatch.setattr(
        "nexus.governance.learning_gate.evaluate_learning_gate", lambda *a, **k: gate
    )
    state = NexusState(task_id="t")
    snapshot = HealthSnapshot(
        overall_score=95.0,
        outcome_score=95.0,
        phase_average=95.0,
        confidence=0.9,
        status="HEALTHY",
        phase_scores={},
        reasons=[],
    )
    trust_before = state.trust_level
    triggers = HealthTriggerPolicy.evaluate_and_record(state, snapshot, project_root=tmp_path)
    assert state.trust_level == trust_before
    assert dict(state.metadata)["learning_gate_status"] == "UNVERIFIED"
    assert all(t.code != "learning_gate_failed" for t in triggers)


# --- item 2: ultra review dry-run ---------------------------------------------
def test_ultra_gate_rejects_dry_run_status():
    from scripts.ops import ultra_gate

    passed, failures = ultra_gate.evaluate_report({
        "status": "DRY_RUN_NOT_VERIFIED",
        "gate_passed": False,
    })
    assert passed is False
    assert "dry_run_not_verified" in failures


def test_ultra_review_dry_run_empty_worktree_is_not_verified(tmp_path):
    from nexus.engine.ultra_review_service import UltraReviewService

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "i",
        ],
        cwd=tmp_path,
        check=True,
    )
    payload = UltraReviewService(tmp_path).run(task="x", report_path="r.json", sandbox_root="sb")
    assert payload["gate_passed"] is False
    assert payload["status"] != "DRY_RUN_PASS"


# --- item 3: belief constraints -----------------------------------------------
def test_lance_belief_store_exposes_read_failure(tmp_path, monkeypatch, caplog):
    (tmp_path / ".nexus" / "vector_db").mkdir(parents=True)

    def _connect(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setitem(sys.modules, "lancedb", SimpleNamespace(connect=_connect))
    store = LanceBeliefStore(tmp_path)
    with caplog.at_level(logging.WARNING):
        assert store.list_beliefs() == []
    assert store.last_read_status == "unavailable"
    assert "boom" in store.last_read_error
    assert "belief read failed" in caplog.text


def test_mem_palace_constraints_report_unavailable_source(tmp_path):
    store = MagicMock()
    store.list_beliefs.side_effect = RuntimeError("down")
    palace = MemPalace(str(tmp_path), belief_store=store)
    constraints = palace.get_skill_constraints()
    assert constraints["forbid"] == [] and constraints["require"] == []
    assert constraints["constraints_source"] == "unavailable"
    assert "down" in constraints["constraints_unavailable_reason"]


def test_mem_palace_constraints_ok_source(tmp_path):
    store = MagicMock()
    store.list_beliefs.return_value = []
    store.last_read_status = "ok"
    palace = MemPalace(str(tmp_path), belief_store=store)
    assert palace.get_skill_constraints()["constraints_source"] == "ok"


# --- item 4: replay runner ----------------------------------------------------
def test_replay_runner_runs_argv_without_shell(tmp_path, monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        return MagicMock(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    # Replays run through the process-group reaping runner (#3052).
    monkeypatch.setattr("nexus.delivery.replay_runner.run_reaping_process_group", fake_run)
    report = ReplayRunner(tmp_path).run_replay({
        "test_artifacts": [{"command": "pytest -k 'a b' c"}]
    })
    assert report["passed"] is True
    assert seen["argv"] == ["pytest", "-k", "a b", "c"]
    assert not seen["kwargs"].get("shell")


@pytest.mark.parametrize(
    "cmd",
    [
        "echo a; rm -rf x",
        "a | b",
        "a && b",
        "echo $HOME",
        "echo `id`",
        "a > f",
        "a < f",
        "",
        "   ",
        None,
        5,
        ["echo"],
    ],
)
def test_replay_runner_rejects_unsafe_or_invalid_commands(tmp_path, monkeypatch, cmd):
    def boom(*_a, **_k):
        raise AssertionError("subprocess must not run")

    monkeypatch.setattr(subprocess, "run", boom)
    report = ReplayRunner(tmp_path).run_replay({"test_artifacts": [{"command": cmd}]})
    assert report["passed"] is False
    assert report["replay_results"][0]["passed"] is False
    assert report["replay_results"][0]["error"]


def test_replay_runner_source_has_no_shell_true():
    assert "shell=True" not in (ROOT / "nexus/delivery/replay_runner.py").read_text()


# --- item 5: sealed manifest --------------------------------------------------
def test_governance_manifest_matches_immutable_files():
    ok, results = AntiDrift(ROOT, ROOT / "nexus/config/governance_manifest.json").verify_drift()
    assert ok, {k: v for k, v in results.items() if not v["passed"]}
