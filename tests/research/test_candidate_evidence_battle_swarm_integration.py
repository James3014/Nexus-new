from __future__ import annotations

import json
import subprocess
from pathlib import Path

from nexus.core.state_contracts import NexusState
from nexus.engine.battle_swarm import BattleSwarm
from nexus.engine.repair_attempt_service import RepairAttemptService


class _FakeBattleSwarm:
    def __init__(self, worktree: Path) -> None:
        self.worktree = worktree
        self.default_workers = 1
        self.cleaned = False

    def trigger_battle(self, *, task_id, desc, context, execute_fn):
        target = self.worktree / "candidate.txt"
        target.write_text("changed\n", encoding="utf-8")
        strategy = {"name": "conservative", "params": {"temperature": 0.2}}
        raw = execute_fn(strategy, str(self.worktree), task_id, desc, context)
        item = {
            "strategy": "conservative",
            "params": strategy["params"],
            **raw,
        }
        return {
            "status": "winner_found",
            "winner": item,
            "all_results": [item],
            "branches_to_clean": [],
            "worktrees_to_clean": [],
        }

    def cleanup(self, _result):
        self.cleaned = True


def _git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=path,
        check=True,
    )
    (path / "candidate.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "candidate.txt"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=path, check=True, capture_output=True)


def test_parallel_repair_collects_diff_and_mechanical_gate(tmp_path: Path, monkeypatch) -> None:
    _git_repo(tmp_path)
    evidence_root = tmp_path / "candidate-evidence"
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", str(evidence_root))
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ENABLED", "1")
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_RATE_PERCENT", "100")

    def run_cli(*, project_root, commands):
        return True, [
            {
                "cmd": commands[0],
                "exit_code": 0,
                "passed": True,
                "stdout_tail": "1 passed",
                "stderr_tail": "",
            }
        ]

    state = NexusState(task_id="battle-task")
    battle = _FakeBattleSwarm(tmp_path)
    service = RepairAttemptService(
        project_root=tmp_path,
        run_cli_pregate_fn=run_cli,
    )
    out = service.execute_attempt(
        task_id="battle-task",
        task_desc="repair candidate.txt",
        state=state,
        attempt=2,
        verify_cmds=["pytest -q"],
        run_dir=tmp_path,
        skip_pregate_for_isolated_workspace=False,
        battle_swarm=battle,
    )
    assert out["passed"] is True
    assert battle.cleaned is True
    assert state.metadata["candidate_evidence_collection_status"] == "COLLECTED"
    assert state.metadata["candidate_evidence_collection_rows"] == 1
    assert state.metadata["candidate_evidence_collection_eligible_rows"] == 1
    group_sha = state.metadata["candidate_evidence_collection_group_sha256"]
    row_path = next((evidence_root / "groups" / group_sha).glob("*.json"))
    row = json.loads(row_path.read_text(encoding="utf-8"))
    assert row["label_quality"] == "MECHANICAL_GATE"
    assert row["verifier_status"] == "PASS"
    assert row["dataset_eligible"] is True
    payload = (evidence_root / row["candidate_payload_ref"]).read_text(encoding="utf-8")
    assert "-base" in payload
    assert "+changed" in payload
    verifier = json.loads(
        (evidence_root / row["verifier_evidence_ref"]).read_text(encoding="utf-8")
    )
    gate = verifier["gate_results"][0]
    assert "cmd" not in gate
    assert gate["cmd_sha256"]
    assert "stdout_tail" not in gate
    assert gate["stdout_sha256"]


def test_battle_swarm_preserves_candidate_evidence_fields(tmp_path: Path, monkeypatch):
    swarm = BattleSwarm(str(tmp_path), default_workers=1, run_dir=str(tmp_path / "runs"))
    worktree = tmp_path / "fake-worktree"
    worktree.mkdir()
    monkeypatch.setattr(
        swarm,
        "_create_worktree",
        lambda _strategy, _branch: worktree,
    )

    def execute_fn(_strategy, _wt, _task_id, _desc, _context):
        return {
            "passed": False,
            "score": 2.5,
            "verifier_status": "fail",
            "gate_results": [{"cmd": "pytest -q", "passed": False}],
            "candidate_payload": "diff-body",
            "candidate_payload_sha256": "a" * 64,
            "candidate_state_hash": "b" * 64,
        }

    result = swarm.trigger_battle(
        task_id="battle-fields",
        desc="test",
        context={},
        execute_fn=execute_fn,
    )
    assert len(result["all_results"]) == 1
    row = result["all_results"][0]
    assert row["candidate_payload"] == "diff-body"
    assert row["candidate_payload_sha256"] == "a" * 64
    assert row["candidate_state_hash"] == "b" * 64
    assert row["gate_results"][0]["cmd"] == "pytest -q"
    assert row["verifier_status"] == "fail"
