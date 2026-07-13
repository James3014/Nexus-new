from pathlib import Path

from nexus.research.day_shift_optimizer import DayShiftOptimizer


def test_dayshift_generation_uses_unified_runtime_on_revisioned_workspace(monkeypatch, tmp_path: Path):
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
        model="gemini-test",
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
