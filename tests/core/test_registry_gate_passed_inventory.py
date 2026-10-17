"""#1869: registry gate_passed=True sites are bound (claim gate) or documented non-claim."""

from __future__ import annotations

import ast
import inspect
from unittest import mock

from nexus.core import capability_executor_registry as reg
from nexus.core.belief_contracts import CapabilityExecutionPlan


def _calls():
    tree = ast.parse(inspect.getsource(reg))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_make_receipt":
            yield node


def test_make_receipt_callers_never_rely_on_default_true() -> None:
    omitted = [
        (n.lineno, n.args[0].value)
        for n in _calls()
        if n.args
        and isinstance(n.args[0], ast.Constant)
        and not any(k.arg == "gate_passed" for k in n.keywords)
    ]
    assert omitted == [], omitted


def test_every_constant_true_site_is_non_claim_or_bound() -> None:
    sites = []
    for n in _calls():
        if not n.args or not isinstance(n.args[0], ast.Constant):
            continue
        for k in n.keywords:
            if (
                k.arg == "gate_passed"
                and isinstance(k.value, ast.Constant)
                and k.value.value is True
            ):
                sites.append(n.args[0].value)
    assert sites, "scan found nothing; the AST scan is broken"
    allowed = reg.NON_CLAIM_EXECUTION_HEALTH_RECEIPTS | reg.BOUND_CLAIM_GATE_RECEIPTS
    assert set(sites) <= reg.NON_CLAIM_EXECUTION_HEALTH_RECEIPTS, sorted(set(sites) - allowed)
    assert not (reg.NON_CLAIM_EXECUTION_HEALTH_RECEIPTS & reg.BOUND_CLAIM_GATE_RECEIPTS)


def test_claim_gate_names_are_never_constant_true() -> None:
    for n in _calls():
        if (
            n.args
            and isinstance(n.args[0], ast.Constant)
            and n.args[0].value in ("claim_gate", "artifact_gate")
        ):
            for k in n.keywords:
                if k.arg == "gate_passed":
                    assert not (isinstance(k.value, ast.Constant) and k.value.value is True)


def _plan() -> CapabilityExecutionPlan:
    return CapabilityExecutionPlan(task_id="t1", plan_id="p1")


class _Exec:
    result: object = {}

    def execute(self, ctx):
        return type(self).result


def _run_artifact_gate(result: object):
    _Exec.result = result
    with mock.patch.object(reg, "_try_import_class", return_value=_Exec):
        return reg._exec_artifact_gate(_plan(), "task")


def test_registry_artifact_gate_fails_closed_without_artifact_and_source_hash() -> None:
    receipt = _run_artifact_gate({"ok": True})
    assert receipt.gate_passed is False
    assert receipt.outcome["binding_blockers"] == [
        "missing_verifier_artifact",
        "missing_source_hash",
    ]
    assert _run_artifact_gate("passed").gate_passed is False
    only_status = _run_artifact_gate({"verifier_status": "pass"})
    assert only_status.gate_passed is False


def test_registry_artifact_gate_passes_with_artifact_and_source_hash() -> None:
    receipt = _run_artifact_gate({"verifier_status": "pass", "source_hash": "sha256:" + "c" * 64})
    assert receipt.gate_passed is True


def _real_executor_receipt(constraints: dict):
    from nexus.services.local_heal.local_model_capability_executors import ArtifactGateLocalExecutor

    plan = CapabilityExecutionPlan(task_id="t1", plan_id="p1", constraints=constraints)
    with mock.patch.object(reg, "_try_import_class", return_value=ArtifactGateLocalExecutor):
        return reg._exec_artifact_gate(plan, "task")


def test_registry_artifact_gate_real_executor_valid_run_reaches_bound_true_path() -> None:
    receipt = _real_executor_receipt({
        "evidence_refs": ["ev1"],
        "source_anchor": {"present": True, "hash": "sha256:" + "d" * 64},
    })
    assert "error" not in receipt.outcome, receipt.outcome
    assert receipt.gate_passed is True


def test_registry_artifact_gate_real_executor_invalid_run_is_false_without_exception() -> None:
    no_evidence = _real_executor_receipt({})
    assert no_evidence.gate_passed is False
    assert "error" not in no_evidence.outcome, no_evidence.outcome
    # evidence but no source hash: executor passes, binding still unmet
    no_hash = _real_executor_receipt({"evidence_refs": ["ev1"]})
    assert no_hash.gate_passed is False
    assert "error" not in no_hash.outcome
    assert "missing_source_hash" in no_hash.outcome["binding_blockers"]
