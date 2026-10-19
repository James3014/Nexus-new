"""#2732: ultra_review is retired as a completion gate; its result is record-only.

The #2701 pilot showed the review cannot judge completion (NO_SIGNAL in both forms), so a
FAIL / BLOCK / crash of the review must never fail the receipt, the host invoker, the seam
stage, the wiring audit's control or the ci_gate strict lane, while the findings stay recorded.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest

from nexus.core import capability_executor_registry as reg
from nexus.services import capability_registry
from nexus.services import post_candidate_seam as seam
from scripts.ops import capability_wiring_audit as audit
from scripts.ops import ci_gate

# belief_contracts re-exports the plan type dynamically (static checkers cannot see it).
CapabilityExecutionPlan = importlib.import_module(
    "nexus.core.belief_contracts"
).CapabilityExecutionPlan

_FINDINGS = [
    {
        "lane": "security_sentry",
        "rule_id": "bandit:B307",
        "state": "VERIFIED_FINDING",
        "severity": "high",
        "file": "app.py",
        "line": 5,
        "summary": "eval of user input",
    },
    {
        "lane": "ghost_regression",
        "rule_id": "regression_test_failed",
        "state": "VERIFIED_FINDING",
        "severity": "high",
        "file": "tests/test_app.py",
        "line": 1,
        "summary": "mapped test failed",
    },
]


def _fail_payload() -> dict[str, Any]:
    return {
        "run_id": "r1",
        "status": "FAIL",
        "gate_passed": False,
        "mode": "review",
        "report_path": ".nexus/reports/ultra_review/t_capability_report.json",
        "artifacts": {"diff": ".nexus/reports/ultra_review/t.diff"},
        "diff": {"bytes": 120, "changed_files": ["app.py"]},
        "fleet": [
            {
                "lane": "security_sentry",
                "status": "FAIL",
                "executed_checks": ["bandit", "ruff-security"],
            },
            {"lane": "logic_breaker", "status": "PASS", "executed_checks": ["py_compile"]},
            {
                "lane": "ghost_regression",
                "status": "FAIL",
                "executed_checks": ["tests/test_app.py"],
            },
        ],
        "findings": list(_FINDINGS),
        "ghost_regression": {"executed_tests": ["tests/test_app.py"]},
    }


def _fake_service(payload: dict[str, Any] | None = None, exc: Exception | None = None):
    class _Service:
        def __init__(self, project_root):
            self.project_root = project_root

        def run(self, **_kwargs):
            if exc is not None:
                raise exc
            return dict(payload or {})

    return _Service


def _plan(tmp_path) -> Any:
    return CapabilityExecutionPlan(
        plan_id="p-2732",
        task_id="t-2732",
        phases=["R"],
        constraints={"workspace_root": str(tmp_path)},
    )


def _bind(monkeypatch, service) -> None:
    monkeypatch.setattr(
        reg,
        "_try_port",
        lambda port: service if port == "ultra_review.UltraReviewService" else None,
    )


def test_fail_review_receipt_never_fails_the_gate_and_keeps_findings(tmp_path, monkeypatch) -> None:
    _bind(monkeypatch, _fake_service(_fail_payload()))
    receipt = reg._exec_ultra_review(_plan(tmp_path), "review")
    assert receipt.invoked is True
    assert receipt.gate_passed is True
    out = receipt.outcome
    assert out["semantic_status"] == "SUCCEEDED"
    assert out["advisory_only"] is True
    assert out["retired_reason"] == "ultra_review_retired_as_completion_gate_2701"
    assert out["review_status"] == "FAIL"
    assert out["review_passed"] is False
    assert out["result"]["review_status"] == "FAIL"
    assert out["result"]["verified_findings"] == 2
    assert {f["rule_id"] for f in out["findings"]} == {"bandit:B307", "regression_test_failed"}
    assert "error" not in out
    assert out["report_path"].endswith("t_capability_report.json")
    # The review's own verdict survives the semantic success guard untouched.
    invoked, gate, _ = reg.apply_semantic_success_guard(invoked=True, gate_passed=True, outcome=out)
    assert (invoked, gate) == (True, True)


def test_pass_review_receipt_is_also_advisory(tmp_path, monkeypatch) -> None:
    payload = {**_fail_payload(), "status": "PASS", "gate_passed": True, "findings": []}
    _bind(monkeypatch, _fake_service(payload))
    receipt = reg._exec_ultra_review(_plan(tmp_path), "review")
    assert receipt.gate_passed is True
    assert receipt.outcome["review_status"] == "PASS"
    assert receipt.outcome["review_passed"] is True
    assert receipt.outcome["advisory_only"] is True


@pytest.mark.parametrize(
    ("status", "blocked_reason"),
    [("BLOCKED", "no_diff_to_review"), ("BLOCKED", "ghost_regression_not_executed:no_os_barrier")],
)
def test_blocked_review_is_recorded_not_blocking(
    tmp_path, monkeypatch, status, blocked_reason
) -> None:
    payload = {
        **_fail_payload(),
        "status": status,
        "gate_passed": False,
        "blocked_reason": blocked_reason,
    }
    _bind(monkeypatch, _fake_service(payload))
    receipt = reg._exec_ultra_review(_plan(tmp_path), "review")
    assert receipt.gate_passed is True
    assert receipt.outcome["review_status"] == "BLOCKED"
    assert receipt.outcome["review_error"] == blocked_reason
    assert "error" not in receipt.outcome


def test_review_crash_is_recorded_not_blocking(tmp_path, monkeypatch) -> None:
    _bind(monkeypatch, _fake_service(exc=RuntimeError("sandbox exploded")))
    receipt = reg._exec_ultra_review(_plan(tmp_path), "review")
    assert receipt.invoked is True
    assert receipt.gate_passed is True
    assert receipt.outcome["review_status"] == "ERROR"
    assert receipt.outcome["review_error"] == "sandbox exploded"
    assert receipt.outcome["evidence_refs"] == ["ev_ultra_review_err_t-2732"]
    assert "error" not in receipt.outcome


def test_unavailable_review_service_is_recorded_not_blocking(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(reg, "_try_port", lambda port: None)
    receipt = reg._exec_ultra_review(_plan(tmp_path), "review")
    assert receipt.gate_passed is True
    assert receipt.outcome["review_status"] == "UNAVAILABLE"
    assert receipt.outcome["review_error"].endswith("ultra_review.UltraReviewService")


def _context(tmp_path) -> dict[str, Any]:
    return {
        "task_id": "t-2732",
        "task_statement": "review",
        "route": {"workspace_root": str(tmp_path)},
    }


def test_host_invoker_reports_fail_review_as_succeeded_record(tmp_path, monkeypatch) -> None:
    _bind(monkeypatch, _fake_service(_fail_payload()))
    invoker = capability_registry.build_real_executor_invoker("ultra_review")
    assert invoker is not None
    out = invoker(_context(tmp_path))
    assert out["invoked"] is True
    assert out["gate_passed"] is True
    assert out["status"] == "SUCCEEDED"
    outcome = out["response"]["outcome"]
    assert outcome["review_status"] == "FAIL"
    assert len(outcome["findings"]) == 2
    assert "advisory_contract_violations" not in out["response"]


def test_host_invoker_does_not_block_an_advisory_contract_shortfall(tmp_path, monkeypatch) -> None:
    # The review crashed, so no lanes ran: the execution contract is short, but the
    # record-only capability reports the shortfall instead of blocking.
    _bind(monkeypatch, _fake_service(exc=RuntimeError("boom")))
    invoker = capability_registry.build_real_executor_invoker("ultra_review")
    assert invoker is not None
    out = invoker(_context(tmp_path))
    assert out["gate_passed"] is True
    assert out["status"] == "SUCCEEDED"
    violations = out["response"]["advisory_contract_violations"]
    assert "missing_outcome_field:lanes" in violations
    assert out["response"]["outcome"]["review_error"] == "boom"


def test_advisory_bypass_is_limited_to_ultra_review() -> None:
    assert capability_registry._is_advisory_only_outcome("ultra_review", {"advisory_only": True})
    assert not capability_registry._is_advisory_only_outcome("ultra_review", {})
    assert not capability_registry._is_advisory_only_outcome("sandbox", {"advisory_only": True})
    assert not capability_registry._is_advisory_only_outcome("claim_gate", {"advisory_only": True})


def test_seam_stage_keeps_the_advisory_record(tmp_path, monkeypatch) -> None:
    _bind(monkeypatch, _fake_service(_fail_payload()))
    invoker = capability_registry.build_real_executor_invoker("ultra_review")
    assert invoker is not None
    out = invoker(_context(tmp_path))
    stage = seam.stage_from_invocation("ultra_review", out, phase="post_candidate")
    assert stage["gate_passed"] is True
    kept = stage["outcome"]
    assert kept["advisory_only"] is True
    assert kept["retired_reason"] == "ultra_review_retired_as_completion_gate_2701"
    assert kept["review_status"] == "FAIL"
    assert kept["review_passed"] is False
    assert kept["review_error"] == ""
    assert len(kept["findings"]) == 2


def test_seam_stage_keeps_the_infra_review_error(tmp_path, monkeypatch) -> None:
    _bind(monkeypatch, _fake_service(exc=RuntimeError("sandbox exploded")))
    invoker = capability_registry.build_real_executor_invoker("ultra_review")
    assert invoker is not None
    stage = seam.stage_from_invocation(
        "ultra_review", invoker(_context(tmp_path)), phase="post_candidate"
    )
    assert stage["gate_passed"] is True
    assert stage["outcome"]["review_status"] == "ERROR"
    assert stage["outcome"]["review_error"] == "sandbox exploded"


def _observed(tmp_path, monkeypatch, service) -> dict[str, Any]:
    from nexus.orchestrator.self_hosted_task_service_parts import worker_dispatch

    _bind(monkeypatch, service)
    invoker = capability_registry.build_real_executor_invoker("ultra_review")
    assert invoker is not None
    out = invoker(_context(tmp_path))
    results = {"ultra_review": {"status": out["status"], "response": {"response": out["response"]}}}
    return worker_dispatch._capability_observations(results)["ultra_review"]


def test_worker_observation_persists_the_fail_verdict(tmp_path, monkeypatch) -> None:
    entry = _observed(tmp_path, monkeypatch, _fake_service(_fail_payload()))
    assert entry["advisory_only"] is True
    assert entry["review_status"] == "FAIL"
    assert entry["review_passed"] is False
    assert entry["review_findings_count"] == 2
    assert "review_error_present" not in entry


def test_worker_observation_persists_the_crash_without_its_text(tmp_path, monkeypatch) -> None:
    entry = _observed(tmp_path, monkeypatch, _fake_service(exc=RuntimeError("secret task text")))
    assert entry["review_status"] == "ERROR"
    assert entry["review_error_present"] is True
    assert "secret task text" not in repr(entry)


def _obs(gate_passed: bool, outcome: dict[str, Any]) -> audit.Obs:
    return audit.Obs(source="registry", row={"gate_passed": gate_passed}, outcome=outcome)


def test_wiring_audit_negative_control_expects_recorded_advisory_findings() -> None:
    pos = _obs(True, {"result": {"review_status": "PASS"}, "advisory_only": True})
    neg_outcome = {
        "result": {"review_status": "FAIL"},
        "advisory_only": True,
        "review_passed": False,
        "findings": list(_FINDINGS),
    }
    assert audit.neg_ultra_review(pos, _obs(True, neg_outcome)).passed is True
    # The old blocking shape (gate failed) no longer satisfies the control.
    assert audit.neg_ultra_review(pos, _obs(False, neg_outcome)).passed is False
    # Findings must still be recorded.
    assert audit.neg_ultra_review(pos, _obs(True, {**neg_outcome, "findings": []})).passed is False


def test_ci_gate_strict_lane_does_not_exit_on_ultra_review_fail(monkeypatch, capsys) -> None:
    calls: list[str] = []

    class _Stop(Exception):
        pass

    def _protocol(dry_run):
        calls.append("protocol")
        raise _Stop

    monkeypatch.setattr(ci_gate, "run_changed_only_check", lambda changed_paths: True)
    monkeypatch.setattr(ci_gate, "requires_ultra_review", lambda changed_paths: True)
    monkeypatch.setattr(ci_gate, "run_ultra_review_check", lambda: calls.append("ultra") or False)
    monkeypatch.setattr(ci_gate, "run_protocol_check", _protocol)
    monkeypatch.setattr(
        "sys.argv",
        ["ci_gate.py", "--strict", "--changed-paths", "nexus/engine/ultra_review_service.py"],
    )
    exits: list[Any] = []
    monkeypatch.setattr("sys.exit", lambda code=0: exits.append(code))
    with pytest.raises(_Stop):
        ci_gate.main()
    assert calls == ["ultra", "protocol"]
    assert exits == []
    assert "advisory only" in capsys.readouterr().out
