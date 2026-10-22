"""Second-batch wiring fixes (2026-10-13): receipts must reflect the real inputs.

learn_mode / learn_phase_slo read the project learn store, learn_scheduler evaluates the
request workspace, the phase policy reads the real SLO summary schema, file_lock refuses a
second task, registry_sync fails closed, jit_validation says SIMULATED, and the
entropy_guard_v2 executor is ready but not registered until its runtime node exists (#1907).
"""

from __future__ import annotations

import json
import shutil
import socket
from pathlib import Path

import pytest

from nexus.core.belief_contracts import CapabilityExecutionPlan
from nexus.core.capability_executor_registry import (
    EXECUTOR_REGISTRY,
    PENDING_PLANNER_NODE_EXECUTORS,
)
from nexus.research.learn.phase_policy import derive_phase_actions, phase_slo_pass_rate
from nexus.research.learn_mode import LearnModeService

FIXTURES = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "wiring_fixtures"


def _plan(task_id: str, **constraints: object) -> CapabilityExecutionPlan:
    return CapabilityExecutionPlan(
        plan_id=f"plan-{task_id}", task_id=task_id, phases=["R"], constraints=dict(constraints)
    )


def _seed_writebacks(root: Path) -> None:
    dest = root / ".nexus" / "reports" / "learn" / "phase_writeback.jsonl"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIXTURES / "learn_phase_slo" / "phase_writeback.jsonl", dest)


def _write_summary(root: Path, phases: dict[str, dict[str, float]]) -> None:
    path = root / ".nexus" / "reports" / "learn" / "phase_slo_summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    # #2715: a real summary says phase_slo_pass; without it the phase policy fails closed.
    payload = {"status": "SUCCESS", "phase_slo_pass": True, "phases": phases}
    path.write_text(json.dumps(payload), encoding="utf-8")


# ── learn_mode / learn_phase_slo ─────────────────────────────────


def test_learn_mode_counts_project_claims(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    shutil.copyfile(FIXTURES / "learn_mode" / "notes.md", tmp_path / "notes.md")
    LearnModeService(project_root=tmp_path).ingest(
        source="local", source_file=str(tmp_path / "notes.md"), topic="refund policy"
    )
    seeded = EXECUTOR_REGISTRY["learn_mode"](_plan("lm-a", workspace_root=str(tmp_path)), "learn")
    empty_ws = tmp_path / "empty"
    empty_ws.mkdir()
    unseeded = EXECUTOR_REGISTRY["learn_mode"](_plan("lm-b", workspace_root=str(empty_ws)), "learn")
    assert seeded.gate_passed, seeded.outcome
    assert int(seeded.outcome["result"]["claims_count"]) >= 1
    assert seeded.outcome["resolved_run_root"] == str(tmp_path.resolve())
    assert int(unseeded.outcome["result"]["claims_count"]) == 0


def test_learn_phase_slo_reads_project_ledger(tmp_path: Path) -> None:
    _seed_writebacks(tmp_path)
    receipt = EXECUTOR_REGISTRY["learn_phase_slo"](
        _plan("slo-a", workspace_root=str(tmp_path)), "slo"
    )
    result = receipt.outcome["result"]
    assert result["phase_slo_pass"] is False
    assert int(result["global"]["writeback_required"]) == 3
    assert result["window"] == 300
    # Nothing written into a per-task runtime directory.
    assert not (tmp_path / ".nexus" / "runtime").exists()


# ── phase policy (nightshift / learn_scheduler readiness) ───────


def test_phase_slo_pass_rate_reads_real_summary_schema() -> None:
    # #2715: real-schema rows (writeback_required, phase_slo_pass); see test_phase_policy_fail_closed_2715
    ok = {"total": 4, "writeback_required": 4, "required_done_ratio": 1.0, "success_ratio": 1.0}
    bad = {"total": 2, "writeback_required": 2, "required_done_ratio": 0.0, "success_ratio": 0.0}
    unseen = {"total": 0, "writeback_required": 0, "required_done_ratio": 1.0, "success_ratio": 1.0}
    assert (
        phase_slo_pass_rate({
            "status": "SUCCESS",
            "phase_slo_pass": True,
            "phases": {"X": ok, "R": ok},
        })
        == 1.0
    )
    assert (
        phase_slo_pass_rate({
            "status": "SUCCESS",
            "phase_slo_pass": True,
            "phases": {"X": ok, "R": bad, "D": unseen},
        })
        == 0.5
    )
    assert (
        phase_slo_pass_rate({"status": "SUCCESS", "phase_slo_pass": True, "phases": {"D": unseen}})
        == 0.0
    )
    assert (
        phase_slo_pass_rate({"status": "UNAVAILABLE", "reason": "phase_slo_summary_missing"}) == 0.0
    )
    assert (
        phase_slo_pass_rate({
            "overall_pass_rate": 0.85,
            "phase_slo_pass": True,
            "status": "SUCCESS",
        })
        == 0.85
    )
    actions = derive_phase_actions(
        {"status": "SUCCESS", "phase_slo_pass": True, "phases": {"X": ok}}, "bug", "standard"
    )
    assert actions.allow_research is True
    missing = derive_phase_actions(
        {"status": "UNAVAILABLE", "reason": "phase_slo_summary_missing"}, "bug", "standard"
    )
    assert missing.allow_research is False
    assert "phase_slo_summary_missing" in missing.reasoning


def test_learn_scheduler_evaluates_request_workspace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # keep any stray write out of the checkout
    ready = tmp_path / "ready"
    _write_summary(
        ready,
        {
            "X": {
                "total": 3,
                "writeback_required": 3,
                "required_done_ratio": 1.0,
                "success_ratio": 1.0,
            }
        },
    )
    not_ready = tmp_path / "not_ready"
    not_ready.mkdir()
    # The store is the process store (cwd here, no state root), never a constraint (#2829).
    monkeypatch.chdir(ready)
    ok = EXECUTOR_REGISTRY["learn_scheduler_service"](_plan("sched-a"), "schedule")
    monkeypatch.chdir(not_ready)
    blocked = EXECUTOR_REGISTRY["learn_scheduler_service"](_plan("sched-b"), "schedule")
    assert ok.gate_passed, ok.outcome
    assert ok.outcome["result"]["exit_code"] == 0
    assert str(ready.resolve()) in ok.outcome["result"]["policy_command"]
    assert blocked.gate_passed is False
    assert blocked.outcome["result"]["exit_code"] == 2


# ── file_lock ────────────────────────────────────────────────────


def test_file_lock_refuses_second_task_and_is_idempotent(tmp_path: Path) -> None:
    lock = EXECUTOR_REGISTRY["file_lock_security_gate"]
    ctx = {"workspace_root": str(tmp_path), "target_files": ["target.py"]}
    first = lock(_plan("lock-a", **ctx), "lock")
    again = lock(_plan("lock-a", **ctx), "lock")
    second = lock(_plan("lock-b", **ctx), "lock")
    other_file = lock(
        _plan("lock-b", workspace_root=str(tmp_path), target_files=["other.py"]), "lock"
    )
    assert first.gate_passed and again.gate_passed
    assert first.outcome["lock_file"] == second.outcome["lock_file"]
    assert second.gate_passed is False
    assert second.outcome["holders"] == {"target.py": "lock-a"}
    assert "FILE_LOCK_HELD_BY_OTHER_TASK:target.py@lock-a" in second.outcome["error"]
    assert other_file.gate_passed


def test_file_lock_stale_lock_is_taken_over(tmp_path: Path) -> None:
    lock = EXECUTOR_REGISTRY["file_lock_security_gate"]
    ctx = {"workspace_root": str(tmp_path), "target_files": ["target.py"]}
    lock(_plan("lock-a", **ctx), "lock")
    lock_file = tmp_path / ".nexus" / "multi_agent" / "locks" / "file_locks.json"
    data = json.loads(lock_file.read_text())
    data["acquired_at"]["target.py"] = 0.0
    lock_file.write_text(json.dumps(data))
    takeover = lock(_plan("lock-b", **ctx), "lock")
    assert takeover.gate_passed, takeover.outcome
    assert takeover.outcome["stale_taken_over"] == {"target.py": "lock-a"}


# ── registry_sync ────────────────────────────────────────────────


def test_registry_sync_unreachable_peer_is_blocked(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
    receipt = EXECUTOR_REGISTRY["registry_skills_sync"](
        _plan(
            "sync-a",
            workspace_root=str(tmp_path),
            registry_peer_host="127.0.0.1",
            registry_peer_port=port,
            registry_query_tokens=["wiring"],
        ),
        "sync",
    )
    assert receipt.gate_passed is False
    assert receipt.outcome["semantic_status"] == "BLOCKED"
    assert receipt.outcome["peer_contacted"] is False
    assert receipt.outcome["error"] == "REGISTRY_PEER_UNAVAILABLE:ConnectionRefusedError"


# ── jit_validation ───────────────────────────────────────────────


def test_jit_validation_receipt_says_simulated() -> None:
    receipt = EXECUTOR_REGISTRY["jit_validation"](
        _plan("jit-a", jit_all_tools=["read_file", "run_test"], jit_token_usage=10), "核驗"
    )
    assert receipt.outcome["simulated"] is True
    assert receipt.outcome["mask_kind"] == "keyword_mock"
    assert receipt.outcome["claim_boundary"]["claim"] == "SIMULATED"


# ── entropy_guard_v2 (#1907) ─────────────────────────────────────


def test_entropy_guard_v2_ready_but_not_registered() -> None:
    # Node id kept; since the runtime 68e86ed pin (node: nexus-runtime #198) the executor
    # is registered and nothing is pending.
    assert "entropy_guard_v2" not in PENDING_PLANNER_NODE_EXECUTORS
    run = EXECUTOR_REGISTRY["entropy_guard_v2"]
    low = run(_plan("ent-low", entropy_audit_text="the total is the sum of the line items"), "x")
    high = run(
        _plan("ent-high", entropy_audit_text="sk-Q7f!9zLp#2Xv@Kq8$wRt5^Ym3&Nb6*Hc1(Jd4)Ue0"), "x"
    )
    missing = run(_plan("ent-none"), "task text is not the output")
    assert low.gate_passed and low.outcome["result"]["status"] == "PASSED"
    assert high.gate_passed is False and high.outcome["result"]["status"] == "VETOED"
    assert high.outcome["result"]["max_segment_entropy"] > 4.1
    assert high.outcome["result"]["high_entropy_segments"] == 1
    assert missing.gate_passed is False
    assert missing.outcome["error"] == "ENTROPY_AUDIT_TEXT_REQUIRED"


@pytest.mark.parametrize("files", [["a.py"], ["a.py", "b.py"]])
def test_file_lock_registry_cross_instance_exclusion(tmp_path: Path, files: list[str]) -> None:
    from nexus.orchestrator.file_lock_registry import FileLockRegistry

    path = str(tmp_path / "locks.json")
    a, b = FileLockRegistry(lock_file=path), FileLockRegistry(lock_file=path)
    assert a.acquire("T1", files) == []
    # b was constructed before T1 locked: acquire must re-read the shared file.
    assert b.acquire("T2", files) == files
    assert b.holder(files[0]) == "T1"
    assert a.acquire("T1", files) == []
    b.release("T2")  # releasing another task's files is a no-op
    assert FileLockRegistry(lock_file=path).check_access("T1", files[0])
