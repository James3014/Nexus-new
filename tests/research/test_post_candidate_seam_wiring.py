"""PR-2 wiring on a bench-like task: the executing planner still selects sandbox/ultra_review/
file_lock (preflight gate: SKIPPED_POLICY_NOT_TRIGGERED) and the post-candidate seam now
invokes them; the flow receipts then report them as invoked with simulated=false."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

import nexus.engine.sandboxed_lane as lane
from nexus.app import research_flow_service as rfs
from nexus.research.flow.unified_capability_projection import overlay_unified_capability_receipts
from nexus.services import post_candidate_seam as seam
from nexus.services.capability_registry import SKIP_POLICY_NOT_TRIGGERED

REAL_BARRIER = lane.os_sandbox_available()
GOV_TASK = (
    "Refactor a credential scrubber while preserving the governance boundary: "
    "never weaken secret redaction to make tests pass."
)
LEDGER_TASK = (
    "Building the owner learning projection from a ledger markdown file sometimes yields fewer "
    "domains than the table contains, and no error is raised."
)
ORIGINAL = "def add(a, b):\n    return a - b\n"
CANDIDATE = "def add(a, b):\n    return a + b\n"


@pytest.fixture
def barrier(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []
    original_run = subprocess.run

    def recording_run(cmd: Any, *args: Any, **kwargs: Any) -> Any:
        argv = [str(part) for part in cmd] if isinstance(cmd, (list, tuple)) else [str(cmd)]
        calls.append(argv)
        if argv and os.path.basename(argv[0]) == "sandbox-exec" and not REAL_BARRIER:
            cmd = list(cmd)[3:]
        return original_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", recording_run)
    monkeypatch.setattr(lane, "os_sandbox_available", lambda: True)
    monkeypatch.setattr("nexus.engine.ultra_review_service.os_sandbox_available", lambda: True)
    return calls


def _runtime_receipt(task_statement: str, tmp_path: Path) -> dict[str, Any]:
    from nexus.services.mainchain_entry import run_mainchain
    from nexus.services.unified_runtime import UnifiedRuntimeRequest, build_online_route

    task_id = "sprint-abc-s0-a1"
    route = build_online_route(
        recommended_flow="direct", gateway_provider="agy", local_enabled=False
    )
    route["with_nexus_armor"] = True
    request = UnifiedRuntimeRequest(
        task_id=task_id,
        workspace_revision="fixture-rev",
        task_statement=task_statement,
        task_type="repair",
        route=route,
        online_prompt="p",
        online_payload="x",
        online_phase="R",
        online_model_name="gemini-3.8-flash-medium",
        online_output_schema={"status": "APPROVED | FAIL"},
    )

    def online(_context: Any) -> dict[str, Any]:
        return {
            "task_id": task_id,
            "invoked": True,
            "status": "SUCCEEDED",
            "gate_passed": True,
            "response": {"status": "APPROVED", "patch": CANDIDATE},
            "evidence_refs": [f"online:{task_id}"],
        }

    online.provider = "agy"  # type: ignore[attr-defined]
    online.online_invoker_provider = "agy"  # type: ignore[attr-defined]

    def verifier(_context: Any) -> dict[str, Any]:
        return {
            "task_id": task_id,
            "status": "pass",
            "evidence": "ok",
            "evidence_refs": [f"verifier:{task_id}"],
        }

    return dict(
        run_mainchain(
            request,
            online_invoker=online,
            verifier=verifier,
            receipt_path=tmp_path / "unified.json",
            with_nexus_armor=True,
        )
    )


def _case(tmp_path: Path) -> Path:
    case = tmp_path / "ws" / "bench_fixtures" / "online_ab_hard_v1" / "demo"
    case.mkdir(parents=True)
    (case / "target.py").write_text(ORIGINAL, encoding="utf-8")
    (case / "test_visible.py").write_text(
        "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).parent))\n"
        "from target import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    (case / "test_hidden.py").write_text(
        "from pathlib import Path\nPath(__file__).with_name('HIDDEN_RAN').write_text('x')\n",
        encoding="utf-8",
    )
    return case


def _stage_rows(receipt: dict[str, Any], names: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    return {
        str(c.get("name")): c for c in receipt.get("capabilities", []) if c.get("name") in names
    }


def test_bench_like_refactor_task_sandbox_and_ultra_review_now_invoked(
    governed_admission: None, barrier: list[list[str]], tmp_path: Path
) -> None:
    unified = _runtime_receipt(GOV_TASK, tmp_path)
    preflight = _stage_rows(unified, ("sandbox", "ultra_review"))
    # The planner still selects them; the preflight escalate gate still skips them.
    assert set(preflight) == {"sandbox", "ultra_review"}
    assert all(row["status"] == "SKIPPED" for row in preflight.values())
    assert all(
        SKIP_POLICY_NOT_TRIGGERED in str(row.get("skip_reason")) for row in preflight.values()
    )

    case = _case(tmp_path)
    report: dict[str, Any] = {}
    rfs._apply_post_candidate_seam(
        report,
        generation_meta={"unified_runtime_receipt": unified},
        task_id="auto-flow:demo",
        target_path=case / "target.py",
        test_file=case / "test_visible.py",
        original_code=ORIGINAL,
        candidate_code=CANDIDATE,
        pre_stages=[],
        released={},
    )

    stages = {row["name"]: row for row in report["unified_runtime_capability_stages"]}
    for name in ("sandbox", "ultra_review"):
        assert stages[name]["status"] == "INVOKED" and stages[name]["invoked"] is True
        assert stages[name]["simulated"] is False
        assert stages[name]["trigger_source"] == "post_candidate_seam:post_candidate"
    assert report["post_candidate_seam"]["capabilities"] == ["sandbox", "ultra_review"]
    assert report["post_candidate_seam"]["hidden_paths_forbidden"] == 2

    flow = overlay_unified_capability_receipts(
        [
            {"name": name, "selected": True, "invoked": False}
            for name in ("sandbox", "ultra_review")
        ],
        report["unified_runtime_capability_stages"],
    )
    for receipt in flow:
        assert receipt["invoked"] is True
        assert receipt["claim_boundary"]["simulated"] is False
    assert not any(part.endswith("test_hidden.py") for argv in barrier for part in argv)
    assert not (case / "HIDDEN_RAN").exists()


def test_bench_like_bugfix_task_file_lock_now_invoked_and_released(
    governed_admission: None, tmp_path: Path
) -> None:
    unified = _runtime_receipt(LEDGER_TASK, tmp_path)
    assert _stage_rows(unified, ("file_lock",))["file_lock"]["status"] == "SKIPPED"

    workspace = tmp_path / "ws"
    workspace.mkdir()
    lock_task, pre = seam.lock_target_if_selected(
        unified_receipt=unified,
        task_id="auto-flow:ledger",
        workspace_root=workspace,
        target_file="target.py",
    )
    released = seam.release_target_lock(lock_task)
    report: dict[str, Any] = {}
    rfs._apply_post_candidate_seam(
        report,
        generation_meta={"unified_runtime_receipt": unified},
        task_id="auto-flow:ledger",
        target_path=workspace / "target.py",
        test_file=workspace / "test_visible.py",
        original_code=ORIGINAL,
        candidate_code=CANDIDATE,
        pre_stages=pre,
        released=released,
    )

    stages = {row["name"]: row for row in report["unified_runtime_capability_stages"]}
    assert stages["file_lock"]["status"] == "INVOKED" and stages["file_lock"]["simulated"] is False
    assert stages["file_lock"]["trigger_source"] == "post_candidate_seam:pre_attempt"
    assert list(report["post_candidate_seam"]["file_lock_released"].values()) == [["target.py"]]
    assert seam.release_target_lock("auto-flow:ledger") == {}


def test_report_untouched_when_runtime_selected_nothing(tmp_path: Path) -> None:
    report: dict[str, Any] = {"unified_runtime_capability_stages": [{"name": "pregate"}]}
    case = _case(tmp_path)

    rfs._apply_post_candidate_seam(
        report,
        generation_meta={"unified_runtime_receipt": {"capabilities": []}},
        task_id="t",
        target_path=case / "target.py",
        test_file=case / "test_visible.py",
        original_code=ORIGINAL,
        candidate_code=CANDIDATE,
        pre_stages=[],
        released={},
    )

    assert report == {"unified_runtime_capability_stages": [{"name": "pregate"}]}


def test_lock_held_by_another_task_blocks_candidate_delivery(tmp_path: Path, monkeypatch) -> None:
    """HIGH-2: a denied file_lock means the candidate is never written to the target."""

    import json as _json

    original = "def value():\n    return 1\n"
    (tmp_path / "demo.py").write_text(original, encoding="utf-8")
    (tmp_path / "test_demo.py").write_text(
        "from demo import value\n\ndef test_value():\n    assert value() == 2\n", encoding="utf-8"
    )
    holder = seam.acquire_target_lock(
        task_id="other-task", workspace_root=tmp_path, target_file="demo.py"
    )
    assert holder["gate_passed"] is True
    runtime = {
        "task_id": "sprint-x-s0-a1",
        "capabilities": [
            {
                "name": "file_lock",
                "status": "SKIPPED",
                "invoked": False,
                "skip_reason": SKIP_POLICY_NOT_TRIGGERED,
            }
        ],
    }

    class FakeLLMGenerator:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        def generate(self, **_kwargs: Any):
            return "def value():\n    return 2\n", {
                "source": "llm",
                "model_calls": 1,
                "model_name": "gemini-3-flash-preview",
                "tokens_used": 10,
                "token_capture_status": "measured",
                "model_patch_generated": True,
                "unified_runtime_receipt": runtime,
            }

    pytest_calls: list[Any] = []
    monkeypatch.setenv("NEXUS_SYMMETRIC_PROMPT", "1")
    monkeypatch.setattr(rfs, "LLMCandidateGenerator", FakeLLMGenerator)
    monkeypatch.setattr(rfs, "_build_codeintel_evidence", lambda *_a, **_k: {"status": "ok"})
    monkeypatch.setattr(
        rfs.subprocess,
        "run",
        lambda *a, **k: pytest_calls.append(a[0]) or subprocess.CompletedProcess(a[0], 0, "", ""),
    )
    try:
        payload, _ = rfs.run_auto_flow(
            repo_root=tmp_path,
            task_desc="Fix value bug",
            target_file="demo.py",
            test_file="test_demo.py",
            task_type="bug",
            candidate_count=1,
            root_cause_confidence=1.0,
            findings_query=None,
            llm_mode=True,
            llm_baseline=True,
            llm_baseline_required=True,
            timeout_sec=30,
            stage1_timeout_sec=10,
            max_time_ratio_guard=1.5,
            baseline_fast_sec=0.0,
            history_window=1,
            history_fail_threshold=999,
            dynamic_timeout_multiplier=2.5,
            min_dynamic_stage1_timeout=1,
            force_flow="baseline",
            report_file=".nexus/reports/research/auto-flow-report.json",
            output_file=None,
            task_id="case-lock-denied",
        )
    finally:
        seam.release_target_lock("other-task")

    assert (tmp_path / "demo.py").read_text(encoding="utf-8") == original
    assert not any(
        "test_demo.py" in " ".join(map(str, call))
        for call in pytest_calls
        if isinstance(call, list)
    )
    text = _json.dumps(payload, default=str)
    assert "file_lock_denied" in text
    assert payload.get("status") != "SUCCESS"


def _sprint(tmp_path: Path, monkeypatch, *, task: str = GOV_TASK, executed: list | None = None):
    from nexus.research.sprint_service import CandidateEval, SprintConfig, run_hyper_sprint

    case = _case(tmp_path)
    workspace = tmp_path / "ws"
    target_rel = str((case / "target.py").relative_to(workspace))
    visible_rel = str((case / "test_visible.py").relative_to(workspace))
    phase_slo = workspace / ".nexus" / "reports" / "learn" / "phase_slo_summary.json"
    phase_slo.parent.mkdir(parents=True, exist_ok=True)
    phase_slo.write_text(
        '{"phase_slo_pass": true, "global": {"required_done_ratio": 1.0}}', encoding="utf-8"
    )
    runtime = _runtime_receipt(task, tmp_path)  # real executing-planner receipt

    class FakeLLMGenerator:
        model_chain = ["gemini-3.8-flash-medium"]

        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        def generate(self, *_a: Any, **_k: Any):
            return CANDIDATE, {
                "source": "llm",
                "model_calls": 1,
                "model_name": "gemini-3.8-flash-medium",
                "tokens_used": 10,
                "token_capture_status": "measured",
                "unified_runtime_receipt": runtime,
            }

    class FakeExecutor:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        def evaluate_candidate(self, **kwargs: Any):
            if executed is not None:
                executed.append(kwargs["code"])
            return CandidateEval(
                seed=kwargs["seed"],
                score=1.0,
                candidate_code=kwargs["code"],
                source=kwargs["source"],
                stdout="1 passed",
            )

    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", FakeLLMGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.InPlaceSprintExecutor", FakeExecutor)
    monkeypatch.setenv("NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL", "0")
    monkeypatch.setenv("NEXUS_DISABLE_HIDDEN_INVARIANT_SHADOW", "1")
    monkeypatch.setenv("NEXUS_DISABLE_HIDDEN_CONTRACT_FAST_PATH", "1")
    monkeypatch.setenv("NEXUS_DISABLE_LOCAL_PREFLIGHT_BEFORE_LLM", "1")
    monkeypatch.setenv("NEXUS_FORCE_INPLACE_EXECUTOR", "1")
    monkeypatch.setenv("NEXUS_DISABLE_DAYSHIFT_OPTIMIZER", "1")
    cfg = SprintConfig(
        task=task,
        target_file=target_rel,
        test_file=visible_rel,
        candidate_count=1,
        llm_mode=True,
        safe_mode=True,
    )
    return case, workspace, target_rel, cfg, run_hyper_sprint


def test_hyper_sprint_path_invokes_sandbox_and_ultra_review(
    governed_admission: None, barrier: list[list[str]], tmp_path: Path, monkeypatch
) -> None:
    """CRITICAL-2: the counted lane's hyper_sprint path runs the seam too (shared helper)."""
    from nexus.research.flow.unified_capability_projection import project_unified_capability_stages

    case, workspace, _target, cfg, run_hyper_sprint = _sprint(tmp_path, monkeypatch)
    result = run_hyper_sprint(repo_root=workspace, config=cfg)

    stages = {
        row["name"]: row
        for row in project_unified_capability_stages(result.unified_runtime_receipts)
    }
    for name in ("sandbox", "ultra_review"):
        assert stages[name]["status"] == "INVOKED", (name, stages.get(name))
        assert stages[name]["simulated"] is False
        assert stages[name]["trigger_source"].startswith("post_candidate_seam:")
    assert result.learning_trace["post_candidate_seam"] == ["sandbox", "ultra_review"]
    assert seam.release_target_lock("anything") == {}
    assert not any(part.endswith("test_hidden.py") for argv in barrier for part in argv)
    assert not (case / "HIDDEN_RAN").exists()


def test_hyper_sprint_file_lock_invoked_and_released(
    governed_admission: None, tmp_path: Path, monkeypatch
) -> None:
    from nexus.research.flow.unified_capability_projection import project_unified_capability_stages

    _case_dir, workspace, _target, cfg, run_hyper_sprint = _sprint(
        tmp_path, monkeypatch, task=LEDGER_TASK
    )
    result = run_hyper_sprint(repo_root=workspace, config=cfg)

    stages = {
        row["name"]: row
        for row in project_unified_capability_stages(result.unified_runtime_receipts)
    }
    assert stages["file_lock"]["status"] == "INVOKED" and stages["file_lock"]["simulated"] is False
    assert stages["file_lock"]["trigger_source"] == "post_candidate_seam:pre_attempt"
    merged = result.unified_runtime_receipts[-1]
    assert list(merged["file_lock_released"].values()) == [[cfg.target_file]]


def test_hyper_sprint_lock_held_by_another_task_never_writes_the_candidate(
    governed_admission: None, tmp_path: Path, monkeypatch
) -> None:
    executed: list[str] = []
    case, workspace, target_rel, cfg, run_hyper_sprint = _sprint(
        tmp_path, monkeypatch, task=LEDGER_TASK, executed=executed
    )
    holder = seam.acquire_target_lock(
        task_id="other-task", workspace_root=workspace, target_file=target_rel
    )
    assert holder["gate_passed"] is True
    try:
        result = run_hyper_sprint(repo_root=workspace, config=cfg)
    finally:
        seam.release_target_lock("other-task")

    assert CANDIDATE not in executed  # the model candidate was never applied to the target
    assert "file_lock_denied" in result.error_codes
    # Only a non-model (local) fallback can win; the model candidate is never delivered.
    assert result.patch != CANDIDATE and not result.winner_source.startswith("llm")
    assert result.learning_trace.get("file_lock_denied") is True
    assert (case / "target.py").read_text(encoding="utf-8") == ORIGINAL
