import os
from pathlib import Path

import pytest

from nexus.research.day_shift_optimizer import DayShiftOptimizer


def test_dayshift_generation_uses_unified_runtime_on_revisioned_workspace(monkeypatch, tmp_path: Path, governed_admission):
    optimizer = DayShiftOptimizer(
        project_root=tmp_path,
        swarm_dir=tmp_path,
        target_file="demo.py",
        task_desc="improve demo",
        max_rounds=1,
        min_round_delay_sec=0,
    )
    monkeypatch.setattr(optimizer, "_workspace_revision", lambda: "revision-001")
    monkeypatch.setattr(
        optimizer.gateway,
        "ask_structured",
        lambda *_args, **_kwargs: ({"status": "APPROVED", "patch": "value = 2\n"}, "raw"),
    )

    response, raw, receipt = optimizer._ask_unified(
        prompt="Return a candidate",
        payload="Return FULL file content.",
        task_statement="improve demo",
        round_id=1,
        attempt=1,
        model="gemini-3.8-flash-medium",
        output_schema={"status": "APPROVED | FAIL", "patch": "full file"},
        task_kind="generation",
    )

    assert response["patch"] == "value = 2\n"
    assert raw == "raw"
    assert receipt["schema"] == "nexus.unified_runtime.receipt.v1"
    assert receipt["task_id"].startswith("dayshift-")
    assert receipt["receipt_complete"] is False
    assert receipt["claim_boundary"]["public_claim_allowed"] is False

    class _Learning:
        def __init__(self, _root):
            pass

        def sync_phase_learning_closure(self, **_kwargs):
            return {"status": "SUCCESS"}

    monkeypatch.setattr("nexus.research.learn_mode.LearnModeService", _Learning)
    optimizer.unified_runtime_receipts = [receipt]
    optimizer._finalize_unified_runtime_receipts(terminal_status="SUCCESS", final_score=0.95)
    assert optimizer.unified_runtime_receipts[0]["task_id"] == receipt["task_id"]
    assert optimizer.unified_runtime_receipts[0]["receipt_complete"] is True
    assert optimizer.unified_runtime_receipts[0]["learning"]["task_id"] == receipt["task_id"]


def _dayshift_layout(tmp_path: Path, monkeypatch, use_llm_scoring: bool):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    (sandbox / "SENTINEL").write_text("keep", encoding="utf-8")
    monkeypatch.chdir(sandbox)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    swarm = tmp_path / "swarm"
    swarm.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("OUTSIDE\n", encoding="utf-8")
    optimizer = DayShiftOptimizer(
        project_root=tmp_path,
        swarm_dir=swarm,
        target_file="demo.py",
        task_desc="improve demo",
        max_rounds=1,
        min_round_delay_sec=0,
        use_llm_scoring=use_llm_scoring,
    )
    return sandbox, swarm, outside, optimizer


def _relink(target: Path, outside: Path) -> None:
    target.unlink()
    os.link(outside, target)


@pytest.mark.parametrize("rollback", ["failed_tests", "low_score"])
def test_dayshift_writes_never_reach_a_file_hard_linked_into_the_swarm(
    tmp_path: Path, monkeypatch, rollback
):
    sandbox, swarm, outside, optimizer = _dayshift_layout(
        tmp_path, monkeypatch, use_llm_scoring=rollback == "low_score"
    )
    target = swarm / "demo.py"
    os.link(outside, target)  # shared before the candidate is written

    def ask(**kwargs):
        if kwargs["task_kind"] == "scoring":
            return {"score": 0.1}, "raw", {}
        return {"status": "APPROVED", "patch": "CANDIDATE\n"}, "raw", {}

    def run_tests():
        assert outside.read_text(encoding="utf-8") == "OUTSIDE\n"
        _relink(target, outside)  # shared again before the rollback
        return (1, "failed") if rollback == "failed_tests" else (0, "passed")

    monkeypatch.setattr(optimizer, "_ask_unified", ask)
    monkeypatch.setattr(optimizer, "_run_tests", run_tests)
    monkeypatch.setattr(optimizer, "_finalize_unified_runtime_receipts", lambda **_kwargs: None)

    result = optimizer.optimize()

    assert result["status"] == "FAILED"
    assert outside.read_text(encoding="utf-8") == "OUTSIDE\n"
    assert target.read_text(encoding="utf-8") == "OUTSIDE\n"
    assert os.stat(target).st_ino != os.stat(outside).st_ino
    assert (sandbox / "SENTINEL").exists()


@pytest.mark.parametrize("target_file", ["../outside.py", "link/outside.py"])
def test_dayshift_candidate_write_stays_inside_the_swarm(tmp_path: Path, monkeypatch, target_file):
    sandbox, swarm, outside, optimizer = _dayshift_layout(tmp_path, monkeypatch, False)
    (swarm / "link").symlink_to(tmp_path, target_is_directory=True)
    optimizer.target_file = target_file
    monkeypatch.setattr(
        optimizer,
        "_ask_unified",
        lambda **_kwargs: ({"status": "APPROVED", "patch": "CANDIDATE\n"}, "raw", {}),
    )
    monkeypatch.setattr(optimizer, "_run_tests", lambda: (1, "failed"))
    monkeypatch.setattr(optimizer, "_finalize_unified_runtime_receipts", lambda **_kwargs: None)

    with pytest.raises((OSError, ValueError)):
        optimizer.optimize()

    assert outside.read_text(encoding="utf-8") == "OUTSIDE\n"
    assert (sandbox / "SENTINEL").exists()
