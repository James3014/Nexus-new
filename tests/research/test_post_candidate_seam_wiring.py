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
    assert report["post_candidate_seam"]["hidden_paths_forbidden"] == 1

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
