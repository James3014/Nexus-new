from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.ops.pr_impact_gate import (
    EXACT_GIT_EVIDENCE_ONLY,
    PytestRunResult,
    _git_changed_paths,
    build_impact_plan,
    classify_regression,
    compute_orphan_evidence_digest,
    compute_test_provenance_digest,
    parse_raw_diff_z,
    run_pytest_plan,
    verify_exact_git_deletion_evidence,
)


def _run(
    exit_code: int,
    failures: list[str],
    status: str = "COMPLETE",
    *,
    revision: str = "base",
) -> PytestRunResult:
    if revision == "base":
        revision = "a" * 40
        source_tree = "c" * 40
    elif revision == "head":
        revision = "b" * 40
        source_tree = "e" * 40
    else:
        source_tree = "c" * 40 if revision == "a" * 40 else "e" * 40
    test_inventory_tree = "d" * 40
    plan_digest = "1" * 64
    verifier_digest = "2" * 64
    return PytestRunResult(
        exit_code=exit_code,
        status=status,
        failures=failures,
        junit_path="result.xml",
        stdout_path="stdout.log",
        revision=revision,
        plan_digest=plan_digest,
        selected_targets=["tests/test_contract.py"],
        executed_targets=["tests/test_contract.py"],
        impact_class="SCOPED_IMPLEMENTATION",
        verifier_digest=verifier_digest,
        source_tree=source_tree,
        test_inventory_tree=test_inventory_tree,
        bound_source_tree=source_tree,
        bound_test_inventory_tree=test_inventory_tree,
        terminal_status=status,
        provenance_digest=compute_test_provenance_digest(
            revision=revision,
            source_tree=source_tree,
            test_inventory_tree=test_inventory_tree,
            plan_digest=plan_digest,
            verifier_digest=verifier_digest,
        ),
    )


def _make_exact_git_repo(tmp_path: Path, *, include_addition: bool) -> dict[str, object]:
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args: str, text: bool = True):
        return subprocess.check_output(["git", *args], cwd=repo, text=text)

    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "tests").mkdir()
    (repo / "tests" / "test_smoke.py").write_text("def test_smoke(): pass\n", encoding="utf-8")
    (repo / "old.py").write_text("OLD = True\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Nexus Test",
            "-c",
            "user.email=nexus@example.invalid",
            "commit",
            "-qm",
            "base",
        ],
        cwd=repo,
        check=True,
    )
    base_sha = git("rev-parse", "HEAD").strip()
    base_tree = git("rev-parse", "HEAD^{tree}").strip()
    (repo / "old.py").unlink()
    if include_addition:
        (repo / "replacement.py").write_text("NEW = True\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Nexus Test",
            "-c",
            "user.email=nexus@example.invalid",
            "commit",
            "-qm",
            "target",
        ],
        cwd=repo,
        check=True,
    )
    target_sha = git("rev-parse", "HEAD").strip()
    target_tree = git("rev-parse", "HEAD^{tree}").strip()
    test_inventory_tree = git("rev-parse", f"{target_sha}:tests").strip()
    full_raw = git(
        "diff",
        "--raw",
        "-z",
        "--no-renames",
        base_sha,
        target_sha,
        text=False,
    )
    deletion_subset = git(
        "diff",
        "--raw",
        "-z",
        "--no-renames",
        base_sha,
        target_sha,
        "--",
        "old.py",
        text=False,
    )
    return {
        "root": repo,
        "base_sha": base_sha,
        "target_sha": target_sha,
        "base_tree": base_tree,
        "target_tree": target_tree,
        "test_inventory_tree": test_inventory_tree,
        "full_raw": full_raw,
        "deletion_subset": deletion_subset,
    }


def _exact_git_kwargs(repo: dict[str, object], raw: bytes) -> dict[str, object]:
    base_sha = str(repo["base_sha"])
    base_tree = str(repo["base_tree"])
    return {
        "base_sha": base_sha,
        "target_sha": str(repo["target_sha"]),
        "base_tree": base_tree,
        "target_tree": str(repo["target_tree"]),
        "test_inventory_tree": str(repo["test_inventory_tree"]),
        "raw_stream_a": raw,
        "raw_stream_b": raw,
        "allowed_deletion_manifest": ["old.py"],
        "orphan_evidence": {
            "old.py": {
                "orphan": True,
                "base_tree": base_tree,
                "source_revision": base_sha,
                "evidence_digest": compute_orphan_evidence_digest("old.py", base_tree),
            }
        },
        "dynamic_caller_universe_known": True,
        "root": repo["root"],
    }


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
        json.dumps({
            "base_sha": "a" * 40,
            "head_sha": "b" * 40,
            "base_source_tree": "9" * 40,
            "base_test_inventory_tree": "8" * 40,
            "source_tree": "c" * 40,
            "test_inventory_tree": "d" * 40,
            "impact_class": "SCOPED_IMPLEMENTATION",
            "pytest_targets": ["tests/test_contract.py"],
        }),
        encoding="utf-8",
    )
    junit_path = tmp_path / "result.xml"

    def fake_run(command, **_kwargs):
        if Path(command[0]).name == "git" and command[1] == "rev-parse":
            values = {
                f"{'b' * 40}^{{commit}}": "b" * 40,
                f"{'b' * 40}^{{tree}}": "c" * 40,
                f"{'b' * 40}:tests": "d" * 40,
            }
            return SimpleNamespace(
                returncode=0,
                stdout=values[command[2]] + "\n",
                stderr="",
            )
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
        revision="b" * 40,
    )

    assert status == 0


def test_pytest_run_rejects_missing_or_drifted_plan_tree_binding(monkeypatch, tmp_path: Path):
    plan_path = tmp_path / "plan.json"
    result_path = tmp_path / "run.json"
    stdout_path = tmp_path / "stdout.log"
    plan_path.write_text(
        json.dumps({
            "base_sha": "a" * 40,
            "head_sha": "b" * 40,
            "base_source_tree": "9" * 40,
            "base_test_inventory_tree": "8" * 40,
            "source_tree": "c" * 40,
            "test_inventory_tree": "d" * 40,
            "impact_class": "SCOPED_IMPLEMENTATION",
            "pytest_targets": ["tests/test_contract.py"],
        }),
        encoding="utf-8",
    )

    def fake_run(command, **_kwargs):
        values = {
            f"{'b' * 40}^{{commit}}": "b" * 40,
            f"{'b' * 40}^{{tree}}": "0" * 40,
            f"{'b' * 40}:tests": "d" * 40,
        }
        assert Path(command[0]).name == "git" and command[1] == "rev-parse"
        return SimpleNamespace(returncode=0, stdout=values[command[2]] + "\n", stderr="")

    monkeypatch.setattr("scripts.ops.pr_impact_gate.subprocess.run", fake_run)

    status = run_pytest_plan(
        plan_path,
        result_path,
        tmp_path / "junit.xml",
        stdout_path,
        cwd=tmp_path,
        revision="b" * 40,
    )

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert status == 5
    assert payload["status"] == "IMPACT_UNKNOWN"
    assert "drifted" in stdout_path.read_text(encoding="utf-8")


def test_raw_diff_parser_rejects_malformed_duplicate_and_divergent_streams():
    deletion = b":100644 000000 abcdef1 0000000 D\x00old.py\x00"
    assert parse_raw_diff_z(deletion) == [
        {
            "old_mode": "100644",
            "new_mode": "000000",
            "old_sha": "abcdef1",
            "new_sha": "0000000",
            "status": "D",
            "path": "old.py",
        }
    ]
    for stream in (b"not-a-raw-record", deletion + deletion[:-1]):
        try:
            parse_raw_diff_z(stream)
        except ValueError:
            pass
        else:
            raise AssertionError("malformed raw diff must fail closed")
    divergent = b":100644 000000 abcdef1 0000000 D\x00other.py\x00"
    result = verify_exact_git_deletion_evidence(
        base_sha="a" * 40,
        target_sha="b" * 40,
        base_tree="c" * 40,
        target_tree="d" * 40,
        test_inventory_tree="e" * 40,
        raw_stream_a=deletion,
        raw_stream_b=divergent,
        allowed_deletion_manifest=["old.py"],
        orphan_evidence={"old.py": {"orphan": True}},
        dynamic_caller_universe_known=True,
    )
    assert result["status"] == "IMPACT_UNKNOWN"
    assert result["claim"] == "IMPACT_UNKNOWN"


def test_exact_git_evidence_rejects_stale_manifest_replacement_and_unknown_dynamic_callers():
    raw = b":100644 000000 abcdef1 0000000 D\x00old.py\x00"
    kwargs = dict(
        base_sha="a" * 40,
        target_sha="b" * 40,
        base_tree="c" * 40,
        target_tree="d" * 40,
        test_inventory_tree="e" * 40,
        raw_stream_a=raw,
        raw_stream_b=raw,
        allowed_deletion_manifest=["wrong.py"],
        orphan_evidence={"old.py": {"orphan": True}},
    )
    assert verify_exact_git_deletion_evidence(**kwargs)["status"] == "IMPACT_UNKNOWN"
    kwargs["allowed_deletion_manifest"] = ["old.py"]
    kwargs["dynamic_caller_universe_known"] = False
    assert verify_exact_git_deletion_evidence(**kwargs)["status"] == "IMPACT_UNKNOWN"


def test_exact_git_evidence_validates_recomputed_orphan_digest_and_authority_ceiling(
    tmp_path: Path,
    monkeypatch,
):
    repo = _make_exact_git_repo(tmp_path, include_addition=False)
    kwargs = _exact_git_kwargs(repo, repo["full_raw"])
    result = verify_exact_git_deletion_evidence(**kwargs)
    assert result["status"] == "EXACT_GIT_EVIDENCE_ONLY"
    assert result["claim"] == EXACT_GIT_EVIDENCE_ONLY
    assert result["candidate_commit_allowed"] is False
    assert result["public_claim_allowed"] is False
    assert result["merge_authority"] is False
    assert "resolve_attempt" not in result["consumers"]

    wrong_tree = dict(kwargs)
    wrong_tree["target_tree"] = "0" * 40
    wrong_endpoint = verify_exact_git_deletion_evidence(**wrong_tree)
    assert wrong_endpoint["status"] == "IMPACT_UNKNOWN"
    assert wrong_endpoint["claim"] == "IMPACT_UNKNOWN"

    from scripts.ops import pr_impact_gate

    trusted_runner = pr_impact_gate._run_trusted_git

    def fail_diff(root, args, *, text):
        if args[0] == "diff":
            empty = "" if text else b""
            return subprocess.CompletedProcess(args, 1, stdout=empty, stderr=empty)
        return trusted_runner(root, args, text=text)

    monkeypatch.setattr(pr_impact_gate, "_run_trusted_git", fail_diff)
    git_failure = verify_exact_git_deletion_evidence(**kwargs)
    assert git_failure["status"] == "IMPACT_UNKNOWN"
    assert "complete exact Git raw diff could not be produced" in git_failure["reasons"]


def test_metadata_node_digest_and_terminal_status_drift_is_impact_unknown():
    base = replace(
        _run(0, [], revision="base"),
        source_tree="c" * 40,
        test_inventory_tree="d" * 40,
        collection_count=1,
        node_ids=["tests.test_contract::test_one"],
        passed_node_ids=["tests.test_contract::test_one"],
        terminal_status="COMPLETE",
    )
    head = replace(base, node_ids=["tests.test_contract::test_two"])
    assert classify_regression(base, head).classification == "IMPACT_UNKNOWN"
    head = replace(base, terminal_status="CI_BOOTSTRAP_DEFECT")
    assert classify_regression(base, head).classification == "IMPACT_UNKNOWN"


def test_raw_diff_parser_consumes_every_record_and_rejects_hidden_tail_evidence():
    first = b":100644 000000 abcdef1 0000000 D\x00old.py\x00"
    second = b":100644 000000 abcdef2 0000000 D\x00other.py\x00"
    addition = b":000000 100644 0000000 abcdef3 A\x00replacement.py\x00"

    assert [entry["path"] for entry in parse_raw_diff_z(first + second)] == [
        "old.py",
        "other.py",
    ]
    for hostile in (
        first + first,
        first + addition,
        first + b":100644 000000 abcdef2 0000000 D\x00",
        first + b"garbage\x00hidden.py\x00",
    ):
        with pytest.raises(ValueError):
            parse_raw_diff_z(hostile)

    result = verify_exact_git_deletion_evidence(
        base_sha="a" * 40,
        target_sha="b" * 40,
        base_tree="c" * 40,
        target_tree="d" * 40,
        test_inventory_tree="e" * 40,
        raw_stream_a=first + second,
        raw_stream_b=first + b":100644 000000 abcdef3 0000000 D\x00third.py\x00",
        allowed_deletion_manifest=["old.py", "other.py"],
        orphan_evidence={},
        dynamic_caller_universe_known=True,
    )
    assert result["status"] == "IMPACT_UNKNOWN"
    assert "independent raw diff streams diverge" in result["reasons"]


def test_real_git_rejects_deletion_only_pathspec_subset_hiding_addition(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args: str, text: bool = True):
        return subprocess.check_output(["git", *args], cwd=repo, text=text)

    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "tests").mkdir()
    (repo / "tests" / "test_smoke.py").write_text("def test_smoke(): pass\n", encoding="utf-8")
    (repo / "old.py").write_text("OLD = True\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Nexus Test",
            "-c",
            "user.email=nexus@example.invalid",
            "commit",
            "-qm",
            "base",
        ],
        cwd=repo,
        check=True,
    )
    base_sha = git("rev-parse", "HEAD").strip()
    base_tree = git("rev-parse", "HEAD^{tree}").strip()
    (repo / "old.py").unlink()
    (repo / "replacement.py").write_text("NEW = True\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Nexus Test",
            "-c",
            "user.email=nexus@example.invalid",
            "commit",
            "-qm",
            "target",
        ],
        cwd=repo,
        check=True,
    )
    target_sha = git("rev-parse", "HEAD").strip()
    target_tree = git("rev-parse", "HEAD^{tree}").strip()
    test_inventory_tree = git("rev-parse", f"{target_sha}:tests").strip()
    deletion_subset = git(
        "diff",
        "--raw",
        "-z",
        "--no-renames",
        base_sha,
        target_sha,
        "--",
        "old.py",
        text=False,
    )

    result = verify_exact_git_deletion_evidence(
        base_sha=base_sha,
        target_sha=target_sha,
        base_tree=base_tree,
        target_tree=target_tree,
        test_inventory_tree=test_inventory_tree,
        raw_stream_a=deletion_subset,
        raw_stream_b=deletion_subset,
        allowed_deletion_manifest=["old.py"],
        orphan_evidence={
            "old.py": {
                "orphan": True,
                "base_tree": base_tree,
                "source_revision": base_sha,
                "evidence_digest": compute_orphan_evidence_digest("old.py", base_tree),
            }
        },
        dynamic_caller_universe_known=True,
        root=repo,
    )

    assert result["status"] == "IMPACT_UNKNOWN"
    assert result["blocking"] is True
    assert "supplied raw evidence identity does not match complete Git diff" in result["reasons"]


def test_build_plan_binds_exact_head_and_test_inventory_trees():
    root = Path(__file__).resolve().parents[2]
    head_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    base_sha = subprocess.check_output(
        ["git", "rev-parse", f"{head_sha}^"], cwd=root, text=True
    ).strip()
    expected_source_tree = subprocess.check_output(
        ["git", "rev-parse", f"{head_sha}^{{tree}}"], cwd=root, text=True
    ).strip()
    expected_test_tree = subprocess.check_output(
        ["git", "rev-parse", f"{head_sha}:tests"], cwd=root, text=True
    ).strip()

    plan = build_impact_plan(
        ["scripts/ops/pr_impact_gate.py"],
        base_sha=base_sha,
        head_sha=head_sha,
        root=root,
    )

    assert plan.source_tree == expected_source_tree
    assert plan.test_inventory_tree == expected_test_tree


def test_missing_or_drifted_tree_metadata_cannot_classify_pass():
    missing = classify_regression(
        replace(
            _run(0, [], revision="a" * 40),
            source_tree="",
            test_inventory_tree="",
            bound_source_tree="",
            bound_test_inventory_tree="",
            provenance_digest="",
        ),
        _run(0, [], revision="b" * 40),
    )
    assert missing.classification == "IMPACT_UNKNOWN"

    base = _run(0, [], revision="a" * 40)
    head = _run(0, [], revision="b" * 40)
    assert classify_regression(base, head).classification == "PASS"
    assert classify_regression(base, replace(head, source_tree="0" * 40)).classification == (
        "IMPACT_UNKNOWN"
    )


def test_exact_git_result_cannot_enter_current_resolution_or_candidate_commit_path(
    tmp_path: Path,
):
    from nexus.executors.worker_contract import (
        AttemptResolutionVerdict,
        WorkerExecutionReceipt,
        WorkerOutcome,
        resolve_attempt,
    )
    from nexus.orchestrator.candidate_commit import CandidateCommitter

    repo = _make_exact_git_repo(tmp_path, include_addition=False)
    evidence = verify_exact_git_deletion_evidence(**_exact_git_kwargs(repo, repo["full_raw"]))
    execution = WorkerExecutionReceipt(
        provider="codex",
        task_id="issue-75-negative",
        target_worktree="/tmp/unused",
        worker_status="COMPLETED",
        outcome=WorkerOutcome.EXECUTION_COMPLETED.value,
        exit_code=0,
        executable_identity="/bin/codex",
        argv=(),
        stdout_sha256="",
        stderr_sha256="",
        wall_time_ms=1,
        process_group_id=None,
        process_group_killed=False,
        timed_out=False,
        provider_calls=1,
        evidence_complete=True,
        commit_created=False,
        merge_performed=False,
        push_performed=False,
    )

    resolution = resolve_attempt(
        execution,
        SimpleNamespace(**evidence),
        SimpleNamespace(**evidence),
    )
    assert resolution.verdict == AttemptResolutionVerdict.FAILED.value
    assert resolution.verified is False
    with pytest.raises(AttributeError, match="verified"):
        CandidateCommitter.create_candidate_commit(
            object.__new__(CandidateCommitter),
            None,
            None,
            SimpleNamespace(**evidence),
        )
