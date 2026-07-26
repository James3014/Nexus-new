from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from nexus.evidence.receipt_base import validate_receipt_base
from nexus.services.unified_runtime import (
    OnlineCliSpec,
    UnifiedRuntime,
    UnifiedRuntimeRequest,
    build_subprocess_online_invoker,
)


def _create_child_script(tmp_path: Path) -> Path:
    script_path = tmp_path / "child_runner.py"
    script_content = """import sys
import json
import os
import hashlib

ledger_path = sys.argv[1]
mode = sys.argv[2] if len(sys.argv) > 2 else "normal"

stdin_data = sys.stdin.read()

records = []
if os.path.exists(ledger_path):
    with open(ledger_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

inv_num = len(records) + 1

record = {
    "pid": os.getpid(),
    "invocation_number": inv_num,
    "stdin_sha256": hashlib.sha256(stdin_data.encode("utf-8")).hexdigest(),
    "stdin_chars": len(stdin_data),
}

with open(ledger_path, "a", encoding="utf-8") as f:
    f.write(json.dumps(record) + "\\n")

if mode == "fail_second" and inv_num == 2:
    sys.stderr.write("Simulated 2nd process failure\\n")
    sys.exit(1)

out = {
    "status": "SUCCEEDED",
    "response": f"child_process_output_attempt_{inv_num}",
    "invocation_number": inv_num,
}
print(json.dumps(out))
"""
    script_path.write_text(script_content, encoding="utf-8")
    return script_path


def _build_request(task_id: str) -> UnifiedRuntimeRequest:
    return UnifiedRuntimeRequest(
        task_id=task_id,
        workspace_revision="rev-subprocess-1",
        task_statement="Sealed physical subprocess test prompt",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )


def _make_dummy_cap_invoker(name: str):
    return lambda ctx: {
        "status": "SUCCEEDED",
        "invoked": True,
        "evidence": "cap ok",
        "evidence_refs": [f"c:{name}:ok"],
        "gate_passed": True,
        "outcome_contributed": True,
    }


def _build_cap_invokers() -> dict[str, Any]:
    names = [
        "baseline",
        "harness_preflight_sensor",
        "delivery_gate",
        "mempalace_gate",
        "artifact_gate",
        "claim_gate",
        "local_model_executor",
        "repair_loop",
    ]
    return {name: _make_dummy_cap_invoker(name) for name in names}


def test_physical_subprocess_light_to_standard_replan_lifecycle(tmp_path: Path):
    script_path = _create_child_script(tmp_path)
    ledger_path = tmp_path / "ledger.jsonl"
    receipt1_path = tmp_path / "receipt1.json"
    receipt2_path = tmp_path / "receipt2.json"

    spec = OnlineCliSpec(
        provider="gemini",
        command=(sys.executable, str(script_path), str(ledger_path), "normal"),
    )
    invoker = build_subprocess_online_invoker(spec)
    runtime = UnifiedRuntime()
    req = _build_request("task-sub-lifecycle-1")

    cap_invokers = _build_cap_invokers()

    # Attempt 1: real subprocess execution
    r1 = runtime.run(
        req,
        online_invoker=invoker,
        capability_invokers=cap_invokers,
        verifier=lambda ctx: {
            "task_id": ctx["task_id"],
            "invoked": True,
            "gate_passed": False,
            "status": "FAILED",
            "evidence": "attempt 1 failed verifier check",
            "evidence_refs": ["v:fail1"],
        },
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence": "l1", "evidence_refs": ["l:1"], "gate_passed": True},
        receipt_path=receipt1_path,
    )

    assert receipt1_path.exists()
    attempt1_bytes = receipt1_path.read_bytes()
    assert r1["terminal_status"] == "INCOMPLETE"
    assert r1["execution_depth"] == "LIGHT"
    assert r1["execution_replan_request"]["requested_execution_depth"] == "STANDARD"

    previous_receipt = json.loads(receipt1_path.read_text(encoding="utf-8"))

    # Attempt 2: real subprocess execution
    r2 = runtime.run_replan(
        previous_receipt,
        req,
        online_invoker=invoker,
        capability_invokers=cap_invokers,
        verifier=lambda ctx: {
            "task_id": ctx["task_id"],
            "invoked": True,
            "gate_passed": True,
            "status": "SUCCEEDED",
            "evidence": "attempt 2 passed verifier check",
            "evidence_refs": ["v:pass2"],
        },
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence": "l2", "evidence_refs": ["l:2"], "gate_passed": True},
        receipt_path=receipt2_path,
    )

    assert receipt2_path.exists()
    assert r2["terminal_status"] == "SUCCEEDED"
    assert r2["execution_depth"] == "STANDARD"

    # Invariance check: Attempt 1 file bytes remain unchanged after Attempt 2
    assert receipt1_path.read_bytes() == attempt1_bytes

    # Physical invocation ledger checks
    ledger_lines = [line.strip() for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(ledger_lines) == 2
    rec1 = json.loads(ledger_lines[0])
    rec2 = json.loads(ledger_lines[1])

    assert isinstance(rec1["pid"], int) and rec1["pid"] > 0
    assert isinstance(rec2["pid"], int) and rec2["pid"] > 0
    assert rec1["invocation_number"] == 1
    assert rec2["invocation_number"] == 2
    assert len(rec1["stdin_sha256"]) == 64
    assert len(rec2["stdin_sha256"]) == 64
    assert rec1["stdin_chars"] > 0
    assert rec2["stdin_chars"] > 0

    # Lineage and strict validation checks
    v1_res = validate_receipt_base(r1, mode="strict")
    assert v1_res["ok"] is True, f"Attempt 1 strict validation failed: {v1_res['blockers']}"

    v2_res = validate_receipt_base(r2, mode="strict")
    assert v2_res["ok"] is True, f"Attempt 2 strict validation failed: {v2_res['blockers']}"

    assert r2["receipt_base"]["parent_receipt_hashes"] == [r2["receipt_base"]["run_anchor_hash"]]
    assert r2["execution_attempt"]["parent_receipt_hash"] == r1["receipt_base"]["receipt_hash"]
    assert r2["execution_attempt"]["parent_run_anchor_hash"] == r1["receipt_base"]["run_anchor_hash"]
    assert r2["execution_attempt"]["source_replan_request_id"] == r1["execution_replan_request"]["replan_request_id"]
    assert r2["planner_decision_id"] != r1["planner_decision_id"]
    assert r2["execution_attempt"]["attempt_number"] == 2


def test_physical_subprocess_receipts_form_strict_valid_lineage(tmp_path: Path):
    script_path = _create_child_script(tmp_path)
    ledger_path = tmp_path / "ledger_lineage.jsonl"

    spec = OnlineCliSpec(
        provider="gemini",
        command=(sys.executable, str(script_path), str(ledger_path), "normal"),
    )
    invoker = build_subprocess_online_invoker(spec)
    runtime = UnifiedRuntime()
    req = _build_request("task-sub-lineage-1")

    r1 = runtime.run(
        req,
        online_invoker=invoker,
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "fail", "evidence_refs": ["v:f1"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    r2 = runtime.run_replan(
        r1,
        req,
        online_invoker=invoker,
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "SUCCEEDED", "evidence": "ok", "evidence_refs": ["v:ok2"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    assert validate_receipt_base(r1, mode="strict")["ok"] is True
    assert validate_receipt_base(r2, mode="strict")["ok"] is True
    assert r2["execution_attempt"]["parent_receipt_hash"] == r1["receipt_base"]["receipt_hash"]


def test_physical_subprocess_attempt_one_bytes_remain_unchanged(tmp_path: Path):
    script_path = _create_child_script(tmp_path)
    ledger_path = tmp_path / "ledger_bytes.jsonl"
    r1_path = tmp_path / "r1_bytes.json"

    spec = OnlineCliSpec(
        provider="gemini",
        command=(sys.executable, str(script_path), str(ledger_path), "normal"),
    )
    invoker = build_subprocess_online_invoker(spec)
    runtime = UnifiedRuntime()
    req = _build_request("task-sub-bytes-1")

    r1 = runtime.run(
        req,
        online_invoker=invoker,
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "fail", "evidence_refs": ["v:f1"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        receipt_path=r1_path,
    )
    bytes_before = r1_path.read_bytes()

    runtime.run_replan(
        r1,
        req,
        online_invoker=invoker,
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "SUCCEEDED", "evidence": "ok", "evidence_refs": ["v:ok2"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    bytes_after = r1_path.read_bytes()
    assert bytes_before == bytes_after


def test_physical_subprocess_invoked_exactly_twice(tmp_path: Path):
    script_path = _create_child_script(tmp_path)
    ledger_path = tmp_path / "ledger_twice.jsonl"

    spec = OnlineCliSpec(
        provider="gemini",
        command=(sys.executable, str(script_path), str(ledger_path), "normal"),
    )
    invoker = build_subprocess_online_invoker(spec)
    runtime = UnifiedRuntime()
    req = _build_request("task-sub-twice-1")

    r1 = runtime.run(
        req,
        online_invoker=invoker,
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "fail", "evidence_refs": ["v:f1"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    runtime.run_replan(
        r1,
        req,
        online_invoker=invoker,
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "SUCCEEDED", "evidence": "ok", "evidence_refs": ["v:ok2"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    records = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(records) == 2


def test_physical_subprocess_second_failure_stops_without_third_attempt(tmp_path: Path):
    script_path = _create_child_script(tmp_path)
    ledger_path = tmp_path / "ledger_fail_second.jsonl"

    spec = OnlineCliSpec(
        provider="gemini",
        command=(sys.executable, str(script_path), str(ledger_path), "fail_second"),
    )
    invoker = build_subprocess_online_invoker(spec)
    runtime = UnifiedRuntime()
    req = _build_request("task-sub-fail2-1")

    r1 = runtime.run(
        req,
        online_invoker=invoker,
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "fail", "evidence_refs": ["v:f1"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    r2 = runtime.run_replan(
        r1,
        req,
        online_invoker=invoker,
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "SUCCEEDED", "evidence": "ok", "evidence_refs": ["v:ok2"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    assert r2["terminal_status"] == "INCOMPLETE"
    assert r2["receipt_complete"] is False

    records = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(records) == 2


def test_physical_subprocess_second_verifier_failure_stops_without_third_attempt(tmp_path: Path):
    script_path = _create_child_script(tmp_path)
    ledger_path = tmp_path / "ledger_fail_v2.jsonl"

    spec = OnlineCliSpec(
        provider="gemini",
        command=(sys.executable, str(script_path), str(ledger_path), "normal"),
    )
    invoker = build_subprocess_online_invoker(spec)
    runtime = UnifiedRuntime()
    req = _build_request("task-sub-v2-1")

    r1 = runtime.run(
        req,
        online_invoker=invoker,
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "fail1", "evidence_refs": ["v:f1"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    r2 = runtime.run_replan(
        r1,
        req,
        online_invoker=invoker,
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "fail2", "evidence_refs": ["v:f2"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    assert r2["terminal_status"] == "INCOMPLETE"
    records = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(records) == 2

    # Attempting a 3rd attempt budget fails
    with pytest.raises(ValueError, match="replan_attempt_budget_exhausted"):
        runtime.run_replan(
            r2,
            req,
            online_invoker=invoker,
            verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "SUCCEEDED", "evidence": "ok", "evidence_refs": ["v:ok"]},
            learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        )

    records_after = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(records_after) == 2


def test_physical_subprocess_tampered_prior_receipt_blocks_before_second_process(tmp_path: Path):
    script_path = _create_child_script(tmp_path)
    ledger_path = tmp_path / "ledger_tamper_block.jsonl"

    spec = OnlineCliSpec(
        provider="gemini",
        command=(sys.executable, str(script_path), str(ledger_path), "normal"),
    )
    invoker = build_subprocess_online_invoker(spec)
    runtime = UnifiedRuntime()
    req = _build_request("task-sub-tamper-1")

    r1 = runtime.run(
        req,
        online_invoker=invoker,
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "fail1", "evidence_refs": ["v:f1"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    tampered_r1 = dict(r1)
    tampered_r1["verifier"] = {"task_id": req.task_id, "invoked": True, "gate_passed": True, "status": "SUCCEEDED"}

    with pytest.raises(ValueError):
        runtime.run_replan(
            tampered_r1,
            req,
            online_invoker=invoker,
            verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "SUCCEEDED", "evidence": "ok", "evidence_refs": ["v:ok"]},
            learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        )

    records = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(records) == 1


def test_physical_subprocess_receipt_does_not_claim_live_model_provider(tmp_path: Path):
    script_path = _create_child_script(tmp_path)
    ledger_path = tmp_path / "ledger_claim.jsonl"

    spec = OnlineCliSpec(
        provider="gemini",
        command=(sys.executable, str(script_path), str(ledger_path), "normal"),
    )
    invoker = build_subprocess_online_invoker(spec)
    runtime = UnifiedRuntime()
    req = _build_request("task-sub-claim-1")

    r1 = runtime.run(
        req,
        online_invoker=invoker,
        verifier=lambda ctx: {"task_id": ctx["task_id"], "invoked": True, "gate_passed": True, "status": "SUCCEEDED", "evidence": "ok", "evidence_refs": ["v:ok"]},
        learning=lambda ctx: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )

    base = r1["receipt_base"]
    assert base["source_world"] == "A"
    assert base["source_component"] == "unified_runtime"
    assert base["public_claim_allowed"] is False
    assert base["production_ready"] is False
    assert r1["online"]["response"]["transport"] == "registered_cli"
