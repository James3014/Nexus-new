from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from scripts.ops.pr_impact_gate import (
    PytestRunResult,
    _git_changed_paths,
    build_impact_plan,
    classify_regression,
    run_pytest_plan,
)


def _run(
    exit_code: int,
    failures: list[str],
    status: str = "COMPLETE",
    *,
    revision: str = "base",
) -> PytestRunResult:
    return PytestRunResult(
        exit_code=exit_code,
        status=status,
        failures=failures,
        junit_path="result.xml",
        stdout_path="stdout.log",
        revision=revision,
        plan_digest="plan-digest",
        selected_targets=["tests/test_contract.py"],
        executed_targets=["tests/test_contract.py"],
        impact_class="SCOPED_IMPLEMENTATION",
        verifier_digest="verifier-digest",
    )


def test_docs_only_change_selects_tier1_governance_verification():
    plan = build_impact_plan(["docs/governance/merge-policy.md"])

    assert plan.tier == 1
    assert plan.impact_class == "DOCS_GOVERNANCE"
    assert plan.pytest_required is True
    assert "tests/ops/test_select_tests.py" in plan.pytest_targets
    assert "tests/core" not in plan.pytest_targets


def test_python_source_change_selects_relevant_pytest():
    plan = build_impact_plan(["nexus/app/research_receipt_runtime.py"])

    assert plan.pytest_required is True
    assert any(target.startswith("tests/app") for target in plan.pytest_targets)
    assert plan.impact_class in {"SCOPED_IMPLEMENTATION", "HIGH_RISK_INTEGRATION"}


def test_test_only_change_runs_changed_and_related_tests():
    plan = build_impact_plan(["tests/ops/test_select_tests.py"])

    assert "tests/ops/test_select_tests.py" in plan.pytest_targets
    assert plan.pytest_required is True


def test_contract_or_authority_change_escalates_to_tier2():
    plan = build_impact_plan(["nexus/contracts/hybrid_route.py"])

    assert plan.tier == 2
    assert plan.impact_class == "HIGH_RISK_INTEGRATION"
    assert "tests/ops/test_pr_impact_gate.py" in plan.pytest_targets
    assert "tests/services/test_policy_gate.py" in plan.pytest_targets


def test_ci_workflow_change_selects_ci_machinery_regressions():
    plan = build_impact_plan([".github/workflows/pytest.yml"])

    assert plan.tier == 2
    assert plan.impact_class == "CI_INFRASTRUCTURE"
    assert plan.workflow_validation_required is True
    assert "tests/ops/test_pr_impact_gate.py" in plan.pytest_targets
    assert "tests/ops/test_ci_gate_report_trust_audit.py" in plan.pytest_targets


def test_unknown_impact_fails_closed_to_broader_verification():
    plan = build_impact_plan(["mystery/runtime.surface"])

    assert plan.tier == 2
    assert plan.impact_class == "IMPACT_UNKNOWN"
    assert plan.pytest_required is True
    assert plan.unmatched_paths == ["mystery/runtime.surface"]
    assert "tests/ops/test_pr_impact_gate.py" in plan.pytest_targets


def test_preexisting_exact_base_failure_is_distinguished_from_new_regression():
    result = classify_regression(
        _run(1, ["tests.test_contract::test_existing_debt"], revision="base"),
        _run(1, ["tests.test_contract::test_existing_debt"], revision="head"),
    )

    assert result.classification == "EXACT_BASELINE_DEBT"
    assert result.blocking is False
    assert result.new_failures == []


def test_new_failure_cannot_be_hidden_by_baseline_mechanism():
    result = classify_regression(
        _run(1, ["tests.test_contract::test_existing_debt"], revision="base"),
        _run(
            1,
            [
                "tests.test_contract::test_existing_debt",
                "tests.test_contract::test_new_regression",
            ],
            revision="head",
        ),
    )

    assert result.classification == "NEW_REGRESSION"
    assert result.blocking is True
    assert result.new_failures == ["tests.test_contract::test_new_regression"]


def test_untrustworthy_execution_is_impact_unknown_and_blocking():
    result = classify_regression(
        _run(2, [], status="IMPACT_UNKNOWN", revision="base"),
        _run(1, ["tests.test_contract::test_failure"], revision="head"),
    )

    assert result.classification == "IMPACT_UNKNOWN"
    assert result.blocking is True


def test_pytest_bootstrap_defect_is_classified_separately():
    result = classify_regression(
        _run(2, [], status="CI_BOOTSTRAP_DEFECT", revision="base"),
        _run(2, [], status="CI_BOOTSTRAP_DEFECT", revision="head"),
    )

    assert result.classification == "CI_BOOTSTRAP_DEFECT"
    assert result.blocking is True


def test_head_may_repair_an_exact_base_bootstrap_defect():
    result = classify_regression(
        _run(2, [], status="CI_BOOTSTRAP_DEFECT", revision="base"),
        _run(0, [], status="COMPLETE", revision="head"),
    )

    assert result.classification == "PASS"
    assert result.blocking is False


def test_mismatched_plan_provenance_fails_closed():
    base = _run(0, [], revision="base")
    head = PytestRunResult(
        exit_code=0,
        status="COMPLETE",
        failures=[],
        junit_path="result.xml",
        stdout_path="stdout.log",
        revision="head",
        plan_digest="different-plan",
        selected_targets=["tests/test_contract.py"],
        executed_targets=["tests/test_contract.py"],
        impact_class="SCOPED_IMPLEMENTATION",
        verifier_digest="verifier-digest",
    )

    result = classify_regression(base, head)

    assert result.classification == "IMPACT_UNKNOWN"
    assert result.blocking is True


def test_unexpected_missing_base_target_fails_closed():
    base = PytestRunResult(
        exit_code=0,
        status="COMPLETE",
        failures=[],
        junit_path="result.xml",
        stdout_path="stdout.log",
        revision="base",
        plan_digest="plan-digest",
        selected_targets=["tests/test_contract.py"],
        impact_class="SCOPED_IMPLEMENTATION",
        missing_targets=["tests/test_contract.py"],
        unexpected_missing_targets=["tests/test_contract.py"],
        verifier_digest="verifier-digest",
    )

    result = classify_regression(base, _run(0, [], revision="head"))

    assert result.classification == "IMPACT_UNKNOWN"
    assert result.blocking is True


def test_unrecognized_execution_status_fails_closed():
    result = classify_regression(
        _run(1, ["tests.test_contract::test_failure"], status="UNRECOGNIZED", revision="base"),
        _run(1, ["tests.test_contract::test_failure"], status="UNRECOGNIZED", revision="head"),
    )

    assert result.classification == "IMPACT_UNKNOWN"
    assert result.blocking is True


def test_incomplete_executed_target_set_fails_closed():
    result = classify_regression(
        _run(0, [], revision="base"),
        replace(_run(0, [], revision="head"), executed_targets=[]),
    )

    assert result.classification == "IMPACT_UNKNOWN"
    assert result.blocking is True


def test_complete_status_with_pytest_bootstrap_exit_fails_closed():
    result = classify_regression(
        replace(_run(1, ["tests.test_contract::test_failure"], revision="base"), exit_code=2),
        replace(_run(1, ["tests.test_contract::test_failure"], revision="head"), exit_code=2),
    )

    assert result.classification == "IMPACT_UNKNOWN"
    assert result.blocking is True


def test_exact_endpoint_diff_includes_deleted_paths(monkeypatch, tmp_path: Path):
    captured: list[str] = []

    def fake_run(command, **_kwargs):
        captured.extend(command)
        return SimpleNamespace(returncode=0, stdout="deleted.py\n", stderr="")

    monkeypatch.setattr("scripts.ops.pr_impact_gate.subprocess.run", fake_run)

    assert _git_changed_paths("base", "head", root=tmp_path) == ["deleted.py"]
    assert captured == ["git", "diff", "--name-only", "base", "head"]


def test_pytest_execution_does_not_fail_fast_after_baseline_failure(monkeypatch, tmp_path: Path):
    test_path = tmp_path / "tests" / "test_contract.py"
    test_path.parent.mkdir()
    test_path.write_text("def test_contract(): pass\n", encoding="utf-8")
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "impact_class": "SCOPED_IMPLEMENTATION",
                "pytest_targets": ["tests/test_contract.py"],
            }
        ),
        encoding="utf-8",
    )
    junit_path = tmp_path / "result.xml"

    def fake_run(command, **_kwargs):
        assert "-x" not in command
        junit_path.write_text('<testsuite tests="1" failures="0"/>', encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("scripts.ops.pr_impact_gate.subprocess.run", fake_run)

    status = run_pytest_plan(
        plan_path,
        tmp_path / "run.json",
        junit_path,
        tmp_path / "stdout.log",
        cwd=tmp_path,
        revision="head",
    )

    assert status == 0
