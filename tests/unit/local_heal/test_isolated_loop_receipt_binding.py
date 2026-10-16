"""#1869: LocalHeal producers emit the verifier/source-hash binding the receipt adapter validates."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile

from nexus.contracts.hybrid_route import RouteMode
from nexus.engine.capability_receipt_adapters import RECEIPT_ADAPTERS
from nexus.services.local_heal.isolated_local_solve_loop import (
    IsolatedLocalSolveRequest,
    run_isolated_local_solve_loop,
)

_DIFF = "--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-print('hello')\n+print('world')\n"
_PASS_CMD = (
    "python3",
    "-c",
    "f=open('f.py'); assert 'world' in f.read()",
)
_FAIL_CMD = ("python3", "-c", "raise SystemExit(1)")


def _run(verifier_command, *, verifier_allowed=True):
    with tempfile.TemporaryDirectory() as src_root:
        with open(os.path.join(src_root, "f.py"), "w", encoding="utf-8") as handle:
            handle.write("print('hello')\n")
        resp = run_isolated_local_solve_loop(
            IsolatedLocalSolveRequest(
                task_id="t1869",
                source_root=src_root,
                problem_statement="fix code",
                evidence_refs=("ref1",),
                model_output=f"```diff\n{_DIFF}```",
                verifier_command=verifier_command,
                local_model_called=True,
                mutation_allowed=True,
                verifier_allowed=verifier_allowed,
                target_file="f.py",
            )
        )
        patched = ""
        ws = resp.apply_receipt.workspace_path
        if ws and os.path.isfile(os.path.join(ws, "f.py")):
            with open(os.path.join(ws, "f.py"), "rb") as handle:
                patched = "sha256:" + hashlib.sha256(handle.read()).hexdigest()
        if ws and os.path.exists(ws):
            shutil.rmtree(ws, ignore_errors=True)
        return resp, patched


def test_verified_local_only_run_emits_binding_and_gate_passes() -> None:
    resp, patched_hash = _run(_PASS_CMD)
    payload = resp.capability_payload
    assert resp.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_EXECUTED
    assert payload["verifier_status"] == "pass"
    # typed hash of the real verified (patched) bytes, not a constant
    assert payload["source_hash"] == patched_hash
    assert payload["source_hash"] != "sha256:" + hashlib.sha256(b"print('hello')\n").hexdigest()
    assert payload["gate_passed"] is True
    receipt = RECEIPT_ADAPTERS["local_heal"].build(claim_verified=True, payload=payload)
    assert receipt.gate_passed is True
    assert receipt.failure_reason == ""
    assert receipt.outcome_contributed is False  # #453 stays fail-closed


def test_producer_gate_follows_the_same_binding_as_the_adapter() -> None:
    resp, _ = _run(_PASS_CMD)
    for drop in ("source_hash", "verifier_status"):
        payload = {k: v for k, v in resp.capability_payload.items() if k != drop}
        assert (
            RECEIPT_ADAPTERS["local_heal"].build(claim_verified=True, payload=payload).gate_passed
            is False
        )


def test_failed_verifier_run_stays_unbound_and_false() -> None:
    resp, _ = _run(_FAIL_CMD)
    payload = resp.capability_payload
    assert payload["verifier_status"] == "fail"
    assert payload["gate_passed"] is False
    receipt = RECEIPT_ADAPTERS["local_heal"].build(claim_verified=True, payload=payload)
    assert receipt.gate_passed is False


def test_run_without_verifier_evidence_has_no_gate() -> None:
    resp, _ = _run((), verifier_allowed=False)
    payload = resp.capability_payload
    assert payload["gate_passed"] is False
    assert (
        RECEIPT_ADAPTERS["local_heal"].build(claim_verified=True, payload=payload).gate_passed
        is False
    )


def test_executed_route_without_source_hash_has_producer_gate_false(monkeypatch) -> None:
    from nexus.services.local_heal import isolated_local_solve_loop as loop

    monkeypatch.setattr(loop, "_verified_source_hash", lambda _receipt: "")
    resp, _ = _run(_PASS_CMD)
    payload = resp.capability_payload
    assert resp.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_EXECUTED
    assert "source_hash" not in payload
    assert payload["gate_passed"] is False
    assert (
        RECEIPT_ADAPTERS["local_heal"].build(claim_verified=True, payload=payload).gate_passed
        is False
    )
