"""PR-2 wiring on a bench-like task: the executing planner still selects sandbox/ultra_review/
file_lock (preflight gate: SKIPPED_POLICY_NOT_TRIGGERED) and the post-candidate seam now
invokes them; the flow receipts then report them as invoked with simulated=false."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import nexus.engine.sandboxed_lane as lane
from nexus.app import research_flow_service as rfs
from nexus.research.flow.unified_capability_projection import overlay_unified_capability_receipts
from nexus.services import post_candidate_seam as seam
from nexus.services.capability_registry import SKIP_POLICY_NOT_TRIGGERED

REAL_BARRIER = lane.os_sandbox_available()
# The confined lane runs ``python -I``; trusted CI executors put pytest on PYTHONPATH only.
PYTEST_UNDER_ISOLATION = (
    subprocess.run(
        [sys.executable, "-I", "-c", "import pytest"], capture_output=True, check=False
    ).returncode
    == 0
)
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


def _assert_confining_profile(argv: list[str]) -> None:
    """Gemini G11: off macOS nothing can be confined for real, so the confinement claim is
    checked on the generated argv/SBPL profile instead (never "ran unconfined, passed"):
    the absolute barrier binary, default-deny, no network, $HOME read-denied, and no read
    allow for a hidden test, the bench staging parent, $HOME or an ancestor of it."""
    import re

    from nexus.services.post_candidate_seam import BENCH_HIDDEN_STAGING_PARENT

    assert argv[0] == lane.SANDBOX_EXEC and argv[1] == "-p", argv[:2]
    profile = argv[2]
    home = lane.sbpl_path(Path(os.path.expanduser("~")).resolve())
    assert "(deny default)" in profile and "(deny network*)" in profile
    assert f'(deny file-read* (subpath "{home}"))' in profile
    allows = " ".join(
        line for line in profile.splitlines() if line.startswith("(allow file-read* ")
    )
    staging = Path(lane.sbpl_path(BENCH_HIDDEN_STAGING_PARENT.resolve()))
    for root in re.findall(r'\(subpath "([^"]+)"\)', allows):
        assert "test_hidden" not in root, root
        assert root != home and not home.startswith(root.rstrip("/") + "/"), root
        assert Path(root) != staging and staging not in Path(root).parents, root


@pytest.fixture
def barrier(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []
    original_run = subprocess.run

    def recording_run(cmd: Any, *args: Any, **kwargs: Any) -> Any:
        argv = [str(part) for part in cmd] if isinstance(cmd, (list, tuple)) else [str(cmd)]
        calls.append(argv)
        if argv and os.path.basename(argv[0]) == "sandbox-exec" and not REAL_BARRIER:
            # No barrier on this host: the confinement is asserted on the profile, then the
            # command runs only to exercise the wiring (never counted as confined).
            _assert_confining_profile(argv)
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
        # #2212's tighten-only projection attests these runs from the seam-sealed REAL_INVOKED
        # evidence (the attestation markers themselves come from the overlay). Where the
        # confined run cannot import pytest (trusted CI executors put dependencies on
        # PYTHONPATH only, which ``python -I`` ignores) the executor honestly reports a failed
        # run: it ran, so it is never "simulated" by design, and it is never claimed real.
        if PYTEST_UNDER_ISOLATION:
            assert receipt.get("attestation") == "real", receipt
            assert receipt["claim_boundary"]["simulated"] is False
        else:
            assert receipt.get("attestation") in {"real", "failed_or_refused"}, receipt
            if receipt.get("attestation") != "real":
                assert receipt["claim_boundary"]["simulated"] is True  # no real claim
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
    # HIGH-2: with self-heal ON the denial must still stop the whole attempt (no repair round).
    monkeypatch.setenv("NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL", "1")
    holder = seam.acquire_target_lock(
        task_id="other-task", workspace_root=workspace, target_file=target_rel
    )
    assert holder["gate_passed"] is True
    try:
        result = run_hyper_sprint(repo_root=workspace, config=cfg)
    finally:
        seam.release_target_lock("other-task")

    assert executed == []  # nothing was evaluated or applied: no candidate, no self-heal, no rescue
    assert result.status == "FAILED" and result.reason == "file_lock_denied"
    assert result.error_codes == ["file_lock_denied"] and result.winner_source == "file_lock_denied"
    assert result.patch == ""
    assert result.learning_trace.get("file_lock_denied") is True
    assert (case / "target.py").read_text(encoding="utf-8") == ORIGINAL


def test_sprint_target_held_by_other_task_sees_a_foreign_lock_only(
    tmp_path: Path, monkeypatch
) -> None:
    """Coordinator #3 / scanner TOCTOU: the sprint's guard is the acquire itself
    (hold_target_lock with the seam holder id); only a FOREIGN lock refuses it, our own lock
    is re-entrant and kept on release, and with the seam off there is no guard."""
    from nexus.research.sprint_service import SprintConfig

    workspace = tmp_path / "ws"
    workspace.mkdir()
    cfg = SprintConfig(task="t", target_file="pkg/target.py", test_file="pkg/test_visible.py")
    release = seam.hold_target_lock(workspace, cfg.target_file)
    assert release is not None
    release()
    own = seam.seam_holder_id(workspace, cfg.target_file)
    seam.acquire_target_lock(task_id=own, workspace_root=workspace, target_file=cfg.target_file)
    release = seam.hold_target_lock(workspace, cfg.target_file)  # our own holder: granted
    assert release is not None
    release()
    assert seam.target_held_by_other(workspace, cfg.target_file, "x") is True  # still ours
    seam.release_target_lock(own)
    seam.acquire_target_lock(
        task_id="other-task", workspace_root=workspace, target_file=cfg.target_file
    )
    try:
        assert seam.hold_target_lock(workspace, cfg.target_file) is None
        monkeypatch.setenv(seam.SEAM_DISABLE_ENV, "0")
        assert seam.hold_target_lock(workspace, cfg.target_file) is not None  # seam off
    finally:
        seam.release_target_lock("other-task")


@pytest.mark.parametrize("selected", [True, False])
def test_baseline_probe_and_shortcut_never_write_while_another_task_holds_the_target(
    tmp_path: Path, monkeypatch, selected: bool
) -> None:
    """Gemini G6: the probe (and its early-shortcut delivery, and the hyper delivery) write
    model code in place too; with the target held by another task none of them writes."""
    from nexus.research import sprint_service

    original = "def value():\n    return 1\n"
    (tmp_path / "demo.py").write_text(original, encoding="utf-8")
    (tmp_path / "test_demo.py").write_text(
        "from demo import value\n\ndef test_value():\n    assert value() == 2\n", encoding="utf-8"
    )
    phase_slo = tmp_path / ".nexus" / "reports" / "learn" / "phase_slo_summary.json"
    phase_slo.parent.mkdir(parents=True, exist_ok=True)
    phase_slo.write_text(  # learn gate open: the flow probes instead of forcing baseline
        '{"phase_slo_pass": true, "global": {"required_done_ratio": 1.0}}', encoding="utf-8"
    )
    holder = seam.acquire_target_lock(
        task_id="other-task", workspace_root=tmp_path, target_file="demo.py"
    )
    assert holder["gate_passed"] is True
    capabilities = (
        [
            {
                "name": "file_lock",
                "status": "SKIPPED",
                "invoked": False,
                "skip_reason": SKIP_POLICY_NOT_TRIGGERED,
            }
        ]
        if selected
        else []
    )
    runtime = {"task_id": "sprint-x-s0-a1", "capabilities": capabilities}

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

    writes: list[str] = []
    real_write = rfs._write_source_text

    def recording_write(path: Path, text: str) -> None:
        if text != original:
            writes.append(text)
        real_write(path, text)

    monkeypatch.delenv("NEXUS_SYMMETRIC_PROMPT", raising=False)
    monkeypatch.setattr(rfs, "LLMCandidateGenerator", FakeLLMGenerator)
    monkeypatch.setattr(rfs, "_write_source_text", recording_write)
    monkeypatch.setattr(rfs, "_build_codeintel_evidence", lambda *_a, **_k: {"status": "ok"})
    monkeypatch.setattr(
        rfs,
        "run_hyper_sprint",
        lambda *, repo_root, config: sprint_service._lock_denied_result(config, {}),
    )
    monkeypatch.setattr(
        rfs.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "", "")
    )
    try:
        payload, _ = rfs.run_auto_flow(
            repo_root=tmp_path,
            task_desc="Fix flaky websocket normalization timeout",
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
            baseline_fast_sec=999.0,
            history_window=1,
            history_fail_threshold=999,
            dynamic_timeout_multiplier=2.5,
            min_dynamic_stage1_timeout=1,
            force_flow=None,
            report_file=".nexus/reports/research/auto-flow-report.json",
            output_file=None,
            task_id="case-probe-lock-denied",
        )
    finally:
        seam.release_target_lock("other-task")

    guard = payload.get("guard") or {}
    assert guard.get("baseline_probe") is not None  # the probe path ran
    assert guard["baseline_probe"]["error"] == "file_lock_denied"
    assert writes == []  # no in-place write of the model candidate anywhere
    assert (tmp_path / "demo.py").read_text(encoding="utf-8") == original
    assert payload.get("status") != "SUCCESS"


@pytest.mark.parametrize("late_writer", ["early_shortcut", "hyper_delivery"])
def test_lock_taken_after_the_probe_blocks_the_later_in_place_delivery(
    tmp_path: Path, monkeypatch, late_writer: str
) -> None:
    """Gemini G6: the early-shortcut and hyper deliveries re-check the lock right before
    writing (the probe / sprint released theirs); a task that took it since wins."""
    import dataclasses

    from nexus.research import sprint_service

    original = "def value():\n    return 1\n"
    candidate = "def value():\n    return 2\n"
    (tmp_path / "demo.py").write_text(original, encoding="utf-8")
    (tmp_path / "test_demo.py").write_text(
        "from demo import value\n\ndef test_value():\n    assert value() == 2\n", encoding="utf-8"
    )

    class FakeLLMGenerator:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        def generate(self, **_kwargs: Any):
            return candidate, {
                "source": "llm",
                "model_calls": 1,
                "model_name": "gemini-3-flash-preview",
                "tokens_used": 10,
                "token_capture_status": "measured",
                "model_patch_generated": True,
                "unified_runtime_receipt": {"task_id": "s", "capabilities": []},
            }

    def take_lock() -> None:
        seam.acquire_target_lock(
            task_id="other-task", workspace_root=tmp_path, target_file="demo.py"
        )

    def fake_run(*a: Any, **k: Any) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(a[0], 0, "1 passed", "")

    real_hold = seam.hold_target_lock
    probe_holds: list[int] = []

    def hold_then_lose_it(workspace_root: Any, target_file: str, extra_files: Any = ()):
        # The probe holds the lock across its write/test/restore (L1); the moment it releases
        # it, another task takes the target before the early-shortcut delivery.
        release = real_hold(workspace_root, target_file, extra_files)
        if release is None or probe_holds or late_writer != "early_shortcut":
            return release
        probe_holds.append(1)

        def release_and_lose() -> None:
            release()
            take_lock()

        return release_and_lose

    monkeypatch.setattr(seam, "hold_target_lock", hold_then_lose_it)

    def fake_hyper(*, repo_root: Path, config: Any):
        take_lock()
        denied = sprint_service._lock_denied_result(config, {})
        return dataclasses.replace(
            denied,
            status="SUCCESS",
            reason="",
            winner_source="llm",
            patch=candidate,
            error_codes=[],
            final_score=1.0,
        )

    monkeypatch.delenv("NEXUS_SYMMETRIC_PROMPT", raising=False)
    monkeypatch.setattr(rfs, "LLMCandidateGenerator", FakeLLMGenerator)
    monkeypatch.setattr(rfs, "_build_codeintel_evidence", lambda *_a, **_k: {"status": "ok"})
    monkeypatch.setattr(rfs, "run_hyper_sprint", fake_hyper)
    monkeypatch.setattr(rfs.subprocess, "run", fake_run)
    try:
        payload, _ = rfs.run_auto_flow(
            repo_root=tmp_path,
            task_desc="Fix flaky websocket normalization timeout",
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
            max_time_ratio_guard=1000.0,
            baseline_fast_sec=999.0 if late_writer == "early_shortcut" else 0.0,
            history_window=1,
            history_fail_threshold=999,
            dynamic_timeout_multiplier=2.5,
            min_dynamic_stage1_timeout=1,
            force_flow=None,
            report_file=".nexus/reports/research/auto-flow-report.json",
            output_file=None,
            task_id=f"case-late-{late_writer}",
        )
    finally:
        seam.release_target_lock("other-task")

    assert (tmp_path / "demo.py").read_text(encoding="utf-8") == original
    assert payload["result"]["status"] != "SUCCESS"
    assert payload["result"]["error"] == "file_lock_denied"
    if late_writer == "early_shortcut":
        assert payload["guard"]["early_baseline_shortcut"] is True
    else:
        assert payload["result"]["flow"] == "hyper_sprint"


@pytest.mark.parametrize("late_writer", ["early_shortcut", "hyper_delivery"])
def test_in_place_delivery_writes_while_holding_the_target_lock(
    tmp_path: Path, monkeypatch, late_writer: str
) -> None:
    """Reviewer L1: the early-shortcut and hyper deliveries hold the target lock DURING the
    write (acquire -> write -> release), not only a check before it."""
    import dataclasses

    from nexus.research import sprint_service

    original = "def value():\n    return 1\n"
    candidate = "def value():\n    return 2\n"
    (tmp_path / "demo.py").write_text(original, encoding="utf-8")
    (tmp_path / "test_demo.py").write_text(
        "from demo import value\n\ndef test_value():\n    assert value() == 2\n", encoding="utf-8"
    )

    class FakeLLMGenerator:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        def generate(self, **_kwargs: Any):
            return candidate, {
                "source": "llm",
                "model_calls": 1,
                "model_name": "gemini-3-flash-preview",
                "tokens_used": 10,
                "token_capture_status": "measured",
                "model_patch_generated": True,
                "unified_runtime_receipt": {"task_id": "s", "capabilities": []},
            }

    held_during_write: list[bool] = []
    real_write = rfs._write_source_text

    def take_lock() -> None:
        return None

    def recording_write(path: Path, text: str) -> None:
        if text == candidate and path.name == "demo.py":
            held_during_write.append(seam.target_held_by_other(tmp_path, "demo.py", "someone-else"))
        real_write(path, text)

    def fake_run(*a: Any, **k: Any) -> subprocess.CompletedProcess:
        if late_writer == "early_shortcut":
            take_lock()  # another task takes the target while the probe's test runs
        return subprocess.CompletedProcess(a[0], 0, "1 passed", "")

    def fake_hyper(*, repo_root: Path, config: Any):
        take_lock()
        denied = sprint_service._lock_denied_result(config, {})
        return dataclasses.replace(
            denied,
            status="SUCCESS",
            reason="",
            winner_source="llm",
            patch=candidate,
            error_codes=[],
            final_score=1.0,
        )

    monkeypatch.delenv("NEXUS_SYMMETRIC_PROMPT", raising=False)
    monkeypatch.setattr(rfs, "LLMCandidateGenerator", FakeLLMGenerator)
    monkeypatch.setattr(rfs, "_build_codeintel_evidence", lambda *_a, **_k: {"status": "ok"})
    monkeypatch.setattr(rfs, "run_hyper_sprint", fake_hyper)
    monkeypatch.setattr(rfs.subprocess, "run", fake_run)
    monkeypatch.setattr(rfs, "_write_source_text", recording_write)
    try:
        payload, _ = rfs.run_auto_flow(
            repo_root=tmp_path,
            task_desc="Fix flaky websocket normalization timeout",
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
            max_time_ratio_guard=1000.0,
            baseline_fast_sec=999.0 if late_writer == "early_shortcut" else 0.0,
            history_window=1,
            history_fail_threshold=999,
            dynamic_timeout_multiplier=2.5,
            min_dynamic_stage1_timeout=1,
            force_flow=None,
            report_file=".nexus/reports/research/auto-flow-report.json",
            output_file=None,
            task_id=f"case-late-{late_writer}",
        )
    finally:
        seam.release_target_lock("other-task")

    assert held_during_write and all(held_during_write)  # every delivery write was locked
    assert seam.target_held_by_other(tmp_path, "demo.py", "someone-else") is False  # released
    assert payload["result"]["status"] == "SUCCESS"


def test_baseline_apply_refuses_when_a_companion_file_is_held(tmp_path: Path, monkeypatch) -> None:
    """Gemini N3: baseline apply's companion edits are locked with the target; a companion
    held by another task refuses the whole delivery (nothing written). Since #2339 only a
    no-model local patch carries companion edits, so this runs the local mode."""
    original = "def value():\n    return 1\n"
    (tmp_path / "demo.py").write_text(original, encoding="utf-8")
    (tmp_path / "test_demo.py").write_text(
        "from demo import value\n\ndef test_value():\n    assert value() == 2\n", encoding="utf-8"
    )

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
                "unified_runtime_receipt": {"task_id": "s", "capabilities": []},
            }

    monkeypatch.delenv("NEXUS_SYMMETRIC_PROMPT", raising=False)
    monkeypatch.setattr(rfs, "LLMCandidateGenerator", FakeLLMGenerator)
    monkeypatch.setattr(rfs, "_build_codeintel_evidence", lambda *_a, **_k: {"status": "ok"})
    monkeypatch.setattr(
        rfs, "generate_local_candidate", lambda *a, **k: "def value():\n    return 2\n"
    )
    monkeypatch.setattr(
        rfs,
        "generate_local_companion_edits",
        lambda *a, **k: {tmp_path / "helper.py": "X = 2\n"},
    )
    monkeypatch.setattr(
        rfs.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "", "")
    )
    seam.acquire_target_lock(task_id="other-task", workspace_root=tmp_path, target_file="helper.py")
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
            llm_mode=False,
            llm_baseline=False,
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
            task_id="case-companion-held",
        )
    finally:
        seam.release_target_lock("other-task")
    assert (tmp_path / "demo.py").read_text(encoding="utf-8") == original
    assert not (tmp_path / "helper.py").exists()
    assert payload["result"]["error"] == "file_lock_denied"


def test_runtime_visible_verifier_goes_through_confined_evaluation_and_is_refused_on_a_held_lock(
    governed_admission: None, tmp_path: Path, monkeypatch
) -> None:
    """Post-#2212 merge: the runtime verifier (inside generate(), before the seam's lock)
    evaluates only through InPlaceSprintExecutor.evaluate_candidate_confined; while another
    task holds the target that raises _SprintLockDenied (never a memoisable denial), so the
    attempt ends file_lock_denied with nothing written or delivered."""
    import nexus.research.sprint_service as sprint_service

    real_executor = sprint_service.InPlaceSprintExecutor
    case, workspace, target_rel, cfg, run_hyper_sprint = _sprint(
        tmp_path, monkeypatch, task=LEDGER_TASK
    )
    confined_calls: list[str] = []
    plain_calls: list[str] = []

    class SpyExecutor(real_executor):  # type: ignore[misc, valid-type]
        def evaluate_candidate(self, **kwargs: Any):
            plain_calls.append(kwargs["code"])
            return super().evaluate_candidate(**kwargs)

        def evaluate_candidate_confined(self, **kwargs: Any):
            confined_calls.append(kwargs["code"])
            return super().evaluate_candidate_confined(**kwargs)

    plain_generator = sprint_service.LLMCandidateGenerator
    verdicts: list[Any] = []

    class VerifyingGenerator(plain_generator):  # type: ignore[misc, valid-type]
        visible_verifier = None

        def generate(self, *a: Any, **k: Any):
            if self.visible_verifier is not None:  # what #2212's response_contract does
                verdicts.append(self.visible_verifier(CANDIDATE, 0))
            return super().generate(*a, **k)

    monkeypatch.setattr(sprint_service, "InPlaceSprintExecutor", SpyExecutor)
    monkeypatch.setattr(sprint_service, "LLMCandidateGenerator", VerifyingGenerator)
    monkeypatch.setenv(seam.CONFINE_VISIBLE_TEST_ENV, "1")
    holder = seam.acquire_target_lock(
        task_id="other-task", workspace_root=workspace, target_file=target_rel
    )
    assert holder["gate_passed"] is True
    try:
        result = run_hyper_sprint(repo_root=workspace, config=cfg)
    finally:
        seam.release_target_lock("other-task")

    assert confined_calls == [CANDIDATE]  # the verifier used the confined entry point only
    assert verdicts == []  # it never returned a (memoisable) verdict: the attempt stopped
    assert plain_calls == []
    assert result.status == "FAILED" and result.reason == "file_lock_denied"
    assert result.patch == ""
    assert (case / "target.py").read_text(encoding="utf-8") == ORIGINAL
