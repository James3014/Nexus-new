from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.ops.pr_impact_gate import (
    EXACT_CONFIG_TARGETS,
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
    selected_targets: list[str] | None = None,
    executed_targets: list[str] | None = None,
    missing_targets: list[str] | None = None,
    unexpected_missing_targets: list[str] | None = None,
    impact_class: str = "SCOPED_IMPLEMENTATION",
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
    selected_targets = selected_targets or ["tests/test_contract.py"]
    executed_targets = selected_targets if executed_targets is None else executed_targets
    missing_targets = missing_targets or []
    unexpected_missing_targets = unexpected_missing_targets or []
    node_ids = sorted(
        set(failures)
        | {
            "tests.test_contract::test_existing_debt",
            "tests.test_contract::test_new_regression",
        }
    )
    passed_node_ids = sorted(set(node_ids) - set(failures))
    return PytestRunResult(
        exit_code=exit_code,
        status=status,
        failures=failures,
        junit_path="result.xml",
        stdout_path="stdout.log",
        revision=revision,
        plan_digest=plan_digest,
        selected_targets=selected_targets,
        executed_targets=executed_targets,
        missing_targets=missing_targets,
        impact_class=impact_class,
        unexpected_missing_targets=unexpected_missing_targets,
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
            collection_count=len(node_ids),
            node_ids=node_ids,
            passed_node_ids=passed_node_ids,
            failed_node_ids=sorted(set(failures)),
            terminal_status=status,
            exit_code=exit_code,
            status=status,
            failures=failures,
            executed_targets=executed_targets,
            selected_targets=selected_targets,
            unexpected_missing_targets=unexpected_missing_targets,
            impact_class=impact_class,
            missing_targets=missing_targets,
        ),
        node_ids=node_ids,
        collection_count=len(node_ids),
        passed_node_ids=passed_node_ids,
        failed_node_ids=sorted(set(failures)),
    )


def _with_node_outcomes(
    run: PytestRunResult,
    *,
    passed: list[str],
    failed: list[str] | None = None,
    errors: list[str] | None = None,
    skipped: list[str] | None = None,
    test_inventory_tree: str | None = None,
) -> PytestRunResult:
    failed = failed or []
    errors = errors or []
    skipped = skipped or []
    node_ids = sorted(set(passed) | set(failed) | set(errors) | set(skipped))
    failures = sorted(set(failed) | set(errors))
    exit_code = 1 if failures else 0
    inventory_tree = test_inventory_tree or run.test_inventory_tree
    return replace(
        run,
        exit_code=exit_code,
        failures=failures,
        test_inventory_tree=inventory_tree,
        bound_test_inventory_tree=inventory_tree,
        collection_count=len(node_ids),
        node_ids=node_ids,
        passed_node_ids=sorted(passed),
        failed_node_ids=sorted(failed),
        error_node_ids=sorted(errors),
        skipped_node_ids=sorted(skipped),
        provenance_digest=compute_test_provenance_digest(
            revision=run.revision,
            source_tree=run.source_tree,
            test_inventory_tree=inventory_tree,
            plan_digest=run.plan_digest,
            verifier_digest=run.verifier_digest,
            collection_count=len(node_ids),
            node_ids=node_ids,
            passed_node_ids=sorted(passed),
            failed_node_ids=sorted(failed),
            error_node_ids=sorted(errors),
            skipped_node_ids=sorted(skipped),
            terminal_status=run.terminal_status,
            exit_code=exit_code,
            status=run.status,
            failures=failures,
            executed_targets=run.executed_targets,
            missing_targets=run.missing_targets,
            selected_targets=run.selected_targets,
            unexpected_missing_targets=run.unexpected_missing_targets,
            impact_class=run.impact_class,
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


def test_codex_dx_failure_prevention_config_selects_exact_test(tmp_path: Path):
    config = tmp_path / "configs" / "codex_dx_failure_prevention.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.touch()
    target = tmp_path / "tests" / "ops" / "test_codex_dx_failure_prevention.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch()

    plan = build_impact_plan(
        ["configs/codex_dx_failure_prevention.json"],
        root=tmp_path,
    )

    assert plan.tier == 1
    assert plan.impact_class == "SCOPED_IMPLEMENTATION"
    assert plan.confidence == 0.9
    assert plan.pytest_required is True
    assert plan.pytest_targets == ["tests/ops/test_codex_dx_failure_prevention.py"]
    assert plan.unmatched_paths == []
    assert plan.reasons == [
        "configs/codex_dx_failure_prevention.json: matched exact config contract"
    ]
    assert plan.workflow_validation_required is False
    assert plan.wiki_required is False


def test_codex_task_context_index_config_selects_exact_test(tmp_path: Path):
    config = tmp_path / "configs" / "codex_task_context_index.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.touch()
    target = tmp_path / "tests" / "ops" / "test_codex_task_context_index.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch()

    plan = build_impact_plan(
        ["configs/codex_task_context_index.json"],
        root=tmp_path,
    )

    assert plan.tier == 1
    assert plan.impact_class == "SCOPED_IMPLEMENTATION"
    assert plan.confidence == 0.9
    assert plan.pytest_required is True
    assert plan.pytest_targets == ["tests/ops/test_codex_task_context_index.py"]
    assert plan.unmatched_paths == []
    assert plan.reasons == ["configs/codex_task_context_index.json: matched exact config contract"]


def test_codex_dx_both_exact_configs_cooccur_in_plan(tmp_path: Path):
    config1 = tmp_path / "configs" / "codex_dx_failure_prevention.json"
    config2 = tmp_path / "configs" / "codex_task_context_index.json"
    config1.parent.mkdir(parents=True, exist_ok=True)
    config1.touch()
    config2.touch()
    target1 = tmp_path / "tests" / "ops" / "test_codex_dx_failure_prevention.py"
    target2 = tmp_path / "tests" / "ops" / "test_codex_task_context_index.py"
    target1.parent.mkdir(parents=True, exist_ok=True)
    target1.touch()
    target2.touch()

    plan = build_impact_plan(
        [
            "configs/codex_dx_failure_prevention.json",
            "configs/codex_task_context_index.json",
        ],
        root=tmp_path,
    )

    assert plan.tier == 1
    assert plan.impact_class == "SCOPED_IMPLEMENTATION"
    assert plan.pytest_required is True
    assert set(plan.pytest_targets) == {
        "tests/ops/test_codex_dx_failure_prevention.py",
        "tests/ops/test_codex_task_context_index.py",
    }
    assert plan.unmatched_paths == []


def test_codex_dx_config_and_mapped_test_diff_selects_only_exact_target(tmp_path: Path):
    config = tmp_path / "configs" / "codex_dx_failure_prevention.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.touch()
    target = tmp_path / "tests" / "ops" / "test_codex_dx_failure_prevention.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch()

    plan = build_impact_plan(
        [
            "configs/codex_dx_failure_prevention.json",
            "tests/ops/test_codex_dx_failure_prevention.py",
        ],
        root=tmp_path,
    )

    assert plan.tier == 1
    assert plan.impact_class == "SCOPED_IMPLEMENTATION"
    assert plan.pytest_required is True
    assert plan.pytest_targets == ["tests/ops/test_codex_dx_failure_prevention.py"]
    assert plan.unmatched_paths == []


def test_codex_dx_before_v1_benchmark_config_selects_exact_tests(tmp_path: Path):
    config = tmp_path / "configs" / "benchmarks" / "codex_dx_before_v1.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.touch()
    target1 = tmp_path / "tests" / "benchmark" / "test_codex_dx_benchmark.py"
    target2 = tmp_path / "tests" / "benchmark" / "test_codex_dx_history.py"
    target1.parent.mkdir(parents=True, exist_ok=True)
    target1.touch()
    target2.touch()

    plan = build_impact_plan(
        ["configs/benchmarks/codex_dx_before_v1.json"],
        root=tmp_path,
    )

    assert plan.tier == 1
    assert plan.impact_class == "SCOPED_IMPLEMENTATION"
    assert plan.confidence == 0.9
    assert plan.pytest_required is True
    assert plan.pytest_targets == [
        "tests/benchmark/test_codex_dx_benchmark.py",
        "tests/benchmark/test_codex_dx_history.py",
    ]
    assert plan.unmatched_paths == []
    assert plan.reasons == [
        "configs/benchmarks/codex_dx_before_v1.json: matched exact config contract"
    ]
    assert plan.workflow_validation_required is False
    assert plan.wiki_required is False


def test_codex_dx_all_exact_configs_cooccur_in_plan(tmp_path: Path):
    config1 = tmp_path / "configs" / "codex_dx_failure_prevention.json"
    config2 = tmp_path / "configs" / "codex_task_context_index.json"
    config3 = tmp_path / "configs" / "benchmarks" / "codex_dx_before_v1.json"
    config1.parent.mkdir(parents=True, exist_ok=True)
    config3.parent.mkdir(parents=True, exist_ok=True)
    config1.touch()
    config2.touch()
    config3.touch()
    target1 = tmp_path / "tests" / "ops" / "test_codex_dx_failure_prevention.py"
    target2 = tmp_path / "tests" / "ops" / "test_codex_task_context_index.py"
    target3 = tmp_path / "tests" / "benchmark" / "test_codex_dx_benchmark.py"
    target4 = tmp_path / "tests" / "benchmark" / "test_codex_dx_history.py"
    target1.parent.mkdir(parents=True, exist_ok=True)
    target3.parent.mkdir(parents=True, exist_ok=True)
    target1.touch()
    target2.touch()
    target3.touch()
    target4.touch()

    plan = build_impact_plan(
        [
            "configs/codex_dx_failure_prevention.json",
            "configs/codex_task_context_index.json",
            "configs/benchmarks/codex_dx_before_v1.json",
        ],
        root=tmp_path,
    )

    assert plan.tier == 1
    assert plan.impact_class == "SCOPED_IMPLEMENTATION"
    assert plan.pytest_required is True
    assert set(plan.pytest_targets) == {
        "tests/ops/test_codex_dx_failure_prevention.py",
        "tests/ops/test_codex_task_context_index.py",
        "tests/benchmark/test_codex_dx_benchmark.py",
        "tests/benchmark/test_codex_dx_history.py",
    }
    assert plan.unmatched_paths == []


def test_codex_dx_before_v1_config_and_single_mapped_test_diff_selects_exact_targets(
    tmp_path: Path,
):
    config = tmp_path / "configs" / "benchmarks" / "codex_dx_before_v1.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.touch()
    target1 = tmp_path / "tests" / "benchmark" / "test_codex_dx_benchmark.py"
    target2 = tmp_path / "tests" / "benchmark" / "test_codex_dx_history.py"
    target1.parent.mkdir(parents=True, exist_ok=True)
    target1.touch()
    target2.touch()

    plan = build_impact_plan(
        [
            "configs/benchmarks/codex_dx_before_v1.json",
            "tests/benchmark/test_codex_dx_benchmark.py",
        ],
        root=tmp_path,
    )

    assert plan.tier == 1
    assert plan.impact_class == "SCOPED_IMPLEMENTATION"
    assert plan.pytest_required is True
    assert plan.pytest_targets == [
        "tests/benchmark/test_codex_dx_benchmark.py",
        "tests/benchmark/test_codex_dx_history.py",
    ]
    assert plan.unmatched_paths == []


def test_codex_dx_before_v1_config_and_both_mapped_tests_diff_selects_exact_targets(
    tmp_path: Path,
):
    config = tmp_path / "configs" / "benchmarks" / "codex_dx_before_v1.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.touch()
    target1 = tmp_path / "tests" / "benchmark" / "test_codex_dx_benchmark.py"
    target2 = tmp_path / "tests" / "benchmark" / "test_codex_dx_history.py"
    target1.parent.mkdir(parents=True, exist_ok=True)
    target1.touch()
    target2.touch()

    plan = build_impact_plan(
        [
            "configs/benchmarks/codex_dx_before_v1.json",
            "tests/benchmark/test_codex_dx_benchmark.py",
            "tests/benchmark/test_codex_dx_history.py",
        ],
        root=tmp_path,
    )

    assert plan.tier == 1
    assert plan.impact_class == "SCOPED_IMPLEMENTATION"
    assert plan.pytest_required is True
    assert plan.pytest_targets == [
        "tests/benchmark/test_codex_dx_benchmark.py",
        "tests/benchmark/test_codex_dx_history.py",
    ]
    assert plan.unmatched_paths == []


@pytest.mark.parametrize(
    "unknown_config",
    [
        "configs/codex_unknown.json",
        "configs/codex_dx_unknown.json",
        "configs/codex_task_context_index_v2.json",
        "configs/benchmarks/codex_dx_unknown.json",
        "configs/benchmarks/codex_dx_after_v1.json",
        "configs/benchmarks/codex_dx_before_v2.json",
        "configs/benchmarks/unknown_benchmark.json",
        "configs/benchmarks/benchmark_manifest.json",
        "configs/ask_policy.yaml",
        "configs/model_candidates/t4_1_frozen_model_candidate_registry.yaml",
    ],
)
def test_unknown_sibling_and_unrelated_configs_fail_closed(unknown_config, tmp_path: Path):
    plan = build_impact_plan([unknown_config], root=tmp_path)

    assert plan.tier == 2
    assert plan.impact_class == "IMPACT_UNKNOWN"
    assert plan.confidence <= 0.4
    assert plan.pytest_required is True
    assert plan.unmatched_paths == [unknown_config]
    assert "unmatched paths fail closed to broader verification" in plan.reasons


@pytest.mark.parametrize(
    "absent_config",
    [
        "configs/codex_dx_failure_prevention.json",
        "configs/codex_task_context_index.json",
        "configs/benchmarks/codex_dx_before_v1.json",
    ],
)
@pytest.mark.parametrize("materialize_target", [False, True])
def test_absent_or_deleted_exact_config_fails_closed_as_unmatched(
    absent_config: str, materialize_target: bool, tmp_path: Path
):
    if materialize_target:
        for target_path in EXACT_CONFIG_TARGETS[absent_config]:
            target = tmp_path / target_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()

    plan = build_impact_plan([absent_config], root=tmp_path)

    assert plan.tier == 2
    assert plan.impact_class == "IMPACT_UNKNOWN"
    assert plan.confidence <= 0.4
    assert plan.pytest_required is True
    assert plan.unmatched_paths == [absent_config]
    assert "unmatched paths fail closed to broader verification" in plan.reasons


@pytest.mark.parametrize(
    "malformed_path",
    [
        "configs/codex_dx_failure_prevention.json.bak",
        "configs/codex_dx_failure_prevention.json/nested",
        "nested/configs/codex_dx_failure_prevention.json",
        "configs/codex_task_context_index.json.tmp",
        "configs/benchmarks/codex_dx_before_v1.json.bak",
        "configs/benchmarks/codex_dx_before_v1.json/nested",
        "nested/configs/benchmarks/codex_dx_before_v1.json",
        "configs/benchmarks/codex_dx_before_v1.json.tmp",
        "configs/benchmarks/codex_dx_before_v1.json.patch",
    ],
)
def test_malformed_and_spoofed_config_paths_fail_closed(malformed_path, tmp_path: Path):
    plan = build_impact_plan([malformed_path], root=tmp_path)

    assert plan.tier == 2
    assert plan.impact_class == "IMPACT_UNKNOWN"
    assert plan.unmatched_paths == [malformed_path]


def test_codex_dx_exact_config_cross_wiring_prevented():
    assert EXACT_CONFIG_TARGETS["configs/codex_dx_failure_prevention.json"] == (
        "tests/ops/test_codex_dx_failure_prevention.py",
    )
    assert EXACT_CONFIG_TARGETS["configs/codex_task_context_index.json"] == (
        "tests/ops/test_codex_task_context_index.py",
    )
    assert EXACT_CONFIG_TARGETS["configs/benchmarks/codex_dx_before_v1.json"] == (
        "tests/benchmark/test_codex_dx_benchmark.py",
        "tests/benchmark/test_codex_dx_history.py",
    )
    assert len(EXACT_CONFIG_TARGETS) == 3


def test_codex_dx_target_omission_fails_closed(tmp_path: Path):
    config = tmp_path / "configs" / "codex_dx_failure_prevention.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.touch()

    plan = build_impact_plan(
        ["configs/codex_dx_failure_prevention.json"],
        root=tmp_path,
    )

    assert plan.tier == 2
    assert plan.impact_class == "IMPACT_UNKNOWN"
    assert "empty verification set failed closed" in plan.reasons


def test_codex_dx_before_v1_target_omission_fails_closed(tmp_path: Path):
    config = tmp_path / "configs" / "benchmarks" / "codex_dx_before_v1.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.touch()

    plan = build_impact_plan(
        ["configs/benchmarks/codex_dx_before_v1.json"],
        root=tmp_path,
    )

    assert plan.tier == 2
    assert plan.impact_class == "IMPACT_UNKNOWN"
    assert "empty verification set failed closed" in plan.reasons


def test_preexisting_exact_base_failure_is_distinguished_from_new_regression():
    result = classify_regression(
        _run(1, ["tests.test_contract::test_existing_debt"], revision="base"),
        _run(1, ["tests.test_contract::test_existing_debt"], revision="head"),
    )

    assert result.classification == "EXACT_BASELINE_DEBT"
    assert result.blocking is False
    assert result.new_failures == []


def test_passing_head_only_tests_preserve_a_trustworthy_exact_base_comparison():
    existing = "tests.test_contract::test_existing"
    added = "tests.test_contract::test_added"
    base = _with_node_outcomes(
        _run(0, [], revision="base"),
        passed=[existing],
    )
    head = _with_node_outcomes(
        _run(0, [], revision="head"),
        passed=[existing, added],
        test_inventory_tree="f" * 40,
    )

    result = classify_regression(base, head)

    assert result.classification == "PASS"
    assert result.blocking is False


def test_head_only_nodes_without_an_exact_test_tree_delta_fail_closed():
    existing = "tests.test_contract::test_existing"
    added = "tests.test_contract::test_unattributed"
    base = _with_node_outcomes(
        _run(0, [], revision="base"),
        passed=[existing],
    )
    head = _with_node_outcomes(
        _run(0, [], revision="head"),
        passed=[existing, added],
        test_inventory_tree=base.test_inventory_tree,
    )

    result = classify_regression(base, head)

    assert result.classification == "IMPACT_UNKNOWN"
    assert result.blocking is True


def test_passing_head_only_tests_preserve_exact_baseline_debt():
    passed = "tests.test_contract::test_passing"
    debt = "tests.test_contract::test_existing_debt"
    added = "tests.test_contract::test_added"
    base = _with_node_outcomes(
        _run(1, [debt], revision="base"),
        passed=[passed],
        failed=[debt],
    )
    head = _with_node_outcomes(
        _run(1, [debt], revision="head"),
        passed=[passed, added],
        failed=[debt],
        test_inventory_tree="f" * 40,
    )

    result = classify_regression(base, head)

    assert result.classification == "EXACT_BASELINE_DEBT"
    assert result.blocking is False
    assert result.new_failures == []


@pytest.mark.parametrize("added_outcome", ["failed", "errors", "skipped"])
def test_nonpassing_head_only_nodes_fail_closed(added_outcome):
    existing = "tests.test_contract::test_existing"
    added = "tests.test_contract::test_added"
    base = _with_node_outcomes(
        _run(0, [], revision="base"),
        passed=[existing],
    )
    outcomes = {
        "passed": [existing],
        "test_inventory_tree": "f" * 40,
        added_outcome: [added],
    }
    head = _with_node_outcomes(_run(0, [], revision="head"), **outcomes)

    result = classify_regression(base, head)

    assert result.classification == "IMPACT_UNKNOWN"
    assert result.blocking is True


def test_missing_base_node_and_replacement_substitution_fail_closed():
    retained = "tests.test_contract::test_retained"
    removed = "tests.test_contract::test_removed"
    replacement = "tests.test_contract::test_replacement"
    base = _with_node_outcomes(
        _run(0, [], revision="base"),
        passed=[retained, removed],
    )

    for head_nodes in ([retained], [retained, replacement]):
        head = _with_node_outcomes(
            _run(0, [], revision="head"),
            passed=head_nodes,
            test_inventory_tree="f" * 40,
        )
        result = classify_regression(base, head)
        assert result.classification == "IMPACT_UNKNOWN"
        assert result.blocking is True


def test_aware_iso_timestamp_parameter_drift_preserves_logical_node_identity():
    base_node = (
        "tests.test_contract::test_expiry[expires_at-2026-08-12T07:32:05.930190+00:00-invalid]"
    )
    head_node = (
        "tests.test_contract::test_expiry[expires_at-2026-08-12T07:40:05.480103+00:00-invalid]"
    )
    base = _with_node_outcomes(_run(0, [], revision="base"), passed=[base_node])
    head = _with_node_outcomes(_run(0, [], revision="head"), passed=[head_node])

    result = classify_regression(base, head)

    assert result.classification == "PASS"
    assert result.blocking is False


def test_dynamic_failure_identity_preserves_raw_evidence_without_false_regression():
    base_node = "tests.test_contract::test_expiry[2026-08-12T07:32:05Z]"
    head_node = "tests.test_contract::test_expiry[2026-08-12T07:40:05+00:00]"
    base = _with_node_outcomes(_run(1, [base_node], revision="base"), passed=[], failed=[base_node])
    head = _with_node_outcomes(_run(1, [head_node], revision="head"), passed=[], failed=[head_node])

    result = classify_regression(base, head)

    assert result.classification == "EXACT_BASELINE_DEBT"
    assert result.base_failures == [base_node]
    assert result.head_failures == [head_node]
    assert result.new_failures == []
    assert result.resolved_failures == []


def test_dynamic_logical_node_downgrade_remains_a_new_regression():
    base_node = "tests.test_contract::test_expiry[2026-08-12T07:32:05Z]"
    head_node = "tests.test_contract::test_expiry[2026-08-12T07:40:05Z]"
    base = _with_node_outcomes(_run(0, [], revision="base"), passed=[base_node])
    head = _with_node_outcomes(_run(1, [head_node], revision="head"), passed=[], failed=[head_node])

    result = classify_regression(base, head)

    assert result.classification == "NEW_REGRESSION"
    assert result.blocking is True
    assert result.new_failures == [head_node]


@pytest.mark.parametrize("collision_side", ["base", "head"])
def test_logical_node_identity_collisions_fail_closed(collision_side):
    first = "tests.test_contract::test_expiry[2026-08-12T07:32:05Z]"
    second = "tests.test_contract::test_expiry[2026-08-12T07:40:05+00:00]"
    stable = "tests.test_contract::test_stable"
    base_nodes = [first, second] if collision_side == "base" else [first, stable]
    head_nodes = [first, second] if collision_side == "head" else [first, stable]
    base = _with_node_outcomes(_run(0, [], revision="base"), passed=base_nodes)
    head = _with_node_outcomes(_run(0, [], revision="head"), passed=head_nodes)

    result = classify_regression(base, head)

    assert result.classification == "IMPACT_UNKNOWN"
    assert result.blocking is True


@pytest.mark.parametrize(
    ("base_token", "head_token"),
    [
        ("2026-02-30T07:32:05Z", "2026-03-01T07:32:05Z"),
        ("2026-08-12T07:32:60Z", "2026-08-12T07:33:00Z"),
        ("2026-08-12T07:32:05+24:00", "2026-08-12T07:32:05+00:00"),
        ("2026-08-12T07:32:05", "2026-08-12T07:33:05"),
        ("2026-08-12", "2026-08-13"),
        ("123", "124"),
        ("a" * 40, "b" * 40),
        ("<ISO_DATETIME>", "2026-08-12T07:32:05Z"),
    ],
)
def test_non_aware_or_arbitrary_parameter_drift_is_not_normalized(base_token, head_token):
    base_node = f"tests.test_contract::test_value[{base_token}]"
    head_node = f"tests.test_contract::test_value[{head_token}]"
    base = _with_node_outcomes(_run(0, [], revision="base"), passed=[base_node])
    head = _with_node_outcomes(_run(0, [], revision="head"), passed=[head_node])

    assert classify_regression(base, head).classification == "IMPACT_UNKNOWN"


def test_timestamp_outside_parameter_id_is_not_normalized():
    base_node = "tests.test_2026-08-12T07:32:05Z::test_value"
    head_node = "tests.test_2026-08-12T07:40:05Z::test_value"
    base = _with_node_outcomes(_run(0, [], revision="base"), passed=[base_node])
    head = _with_node_outcomes(_run(0, [], revision="head"), passed=[head_node])

    assert classify_regression(base, head).classification == "IMPACT_UNKNOWN"


def test_empty_or_downgraded_inventory_metadata_fails_closed():
    existing = "tests.test_contract::test_existing"
    empty_base = _with_node_outcomes(_run(0, [], revision="base"), passed=[])
    populated_head = _with_node_outcomes(
        _run(0, [], revision="head"),
        passed=[existing],
        test_inventory_tree="f" * 40,
    )
    assert classify_regression(empty_base, populated_head).classification == ("IMPACT_UNKNOWN")

    populated_base = _with_node_outcomes(
        _run(0, [], revision="base"),
        passed=[existing],
    )
    empty_head = _with_node_outcomes(
        _run(0, [], revision="head"),
        passed=[],
        test_inventory_tree="f" * 40,
    )
    assert classify_regression(populated_base, empty_head).classification == ("IMPACT_UNKNOWN")

    skipped_head = _with_node_outcomes(
        _run(0, [], revision="head"),
        passed=[],
        skipped=[existing],
    )
    assert classify_regression(populated_base, skipped_head).classification == ("IMPACT_UNKNOWN")


@pytest.mark.parametrize("base_outcome", ["failed", "errors"])
def test_existing_failure_cannot_be_hidden_by_a_head_skip(base_outcome):
    node = "tests.test_contract::test_existing_debt"
    base = _with_node_outcomes(
        _run(1, [node], revision="base"),
        passed=[],
        **{base_outcome: [node]},
    )
    head = _with_node_outcomes(
        _run(0, [], revision="head"),
        passed=[],
        skipped=[node],
    )

    result = classify_regression(base, head)

    assert result.classification == "IMPACT_UNKNOWN"
    assert result.blocking is True


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


@pytest.mark.parametrize(
    ("label", "tamper"),
    [
        ("unexpected omission", lambda run: replace(run, unexpected_missing_targets=[])),
        ("missing omission", lambda run: replace(run, missing_targets=[])),
        (
            "target overlap",
            lambda run: replace(run, executed_targets=["tests/missing.py"]),
        ),
        (
            "target membership substitution",
            lambda run: replace(run, selected_targets=["tests/other.py"]),
        ),
        ("outcome count", lambda run: replace(run, collection_count=3)),
        ("outcome membership", lambda run: replace(run, passed_node_ids=[])),
        ("status", lambda run: replace(run, status="IMPACT_UNKNOWN")),
        ("exit", lambda run: replace(run, exit_code=1)),
        (
            "failure membership",
            lambda run: replace(run, failures=["tests.test_contract::test_new_regression"]),
        ),
    ],
)
def test_decision_field_tampering_omission_overlap_count_membership_fails_closed(label, tamper):
    base = _run(
        0,
        [],
        revision="base",
        selected_targets=["tests/missing.py"],
        executed_targets=[],
        missing_targets=["tests/missing.py"],
        unexpected_missing_targets=["tests/missing.py"],
    )
    head = _run(0, [], revision="head")

    assert classify_regression(tamper(base), head).classification == "IMPACT_UNKNOWN", label


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


def test_tampered_passed_node_partition_cannot_classify_pass():
    node = "tests.test_contract::test_one"
    base = replace(
        _run(0, [], revision="base"),
        collection_count=1,
        node_ids=[node],
        passed_node_ids=[node],
        terminal_status="COMPLETE",
    )
    head = replace(
        _run(0, [], revision="head"),
        collection_count=1,
        node_ids=[node],
        passed_node_ids=[],
        terminal_status="COMPLETE",
    )
    assert classify_regression(base, head).classification == "IMPACT_UNKNOWN"


@pytest.mark.parametrize(
    "tamper",
    [
        lambda run, node: replace(run, passed_node_ids=[]),
        lambda run, node: replace(run, failed_node_ids=[node], failures=[node]),
        lambda run, node: replace(run, collection_count=2),
        lambda run, node: replace(
            run,
            provenance_digest=compute_test_provenance_digest(
                revision=run.revision,
                source_tree=run.source_tree,
                test_inventory_tree=run.test_inventory_tree,
                plan_digest=run.plan_digest,
                verifier_digest=run.verifier_digest,
                collection_count=run.collection_count,
                node_ids=run.node_ids,
                passed_node_ids=run.passed_node_ids,
                failed_node_ids=run.failed_node_ids,
                error_node_ids=run.error_node_ids,
                skipped_node_ids=run.skipped_node_ids,
                terminal_status=run.terminal_status,
                exit_code=run.exit_code,
                status=run.status,
                failures=run.failures,
                executed_targets=run.executed_targets,
                missing_targets=run.missing_targets,
                selected_targets=run.selected_targets,
                unexpected_missing_targets=run.unexpected_missing_targets,
                impact_class=run.impact_class,
            )[:-1]
            + "0",
        ),
    ],
)
def test_outcome_partition_and_digest_tampering_fail_closed(tamper):
    node = "tests.test_contract::test_one"
    base = replace(
        _run(0, [], revision="base"),
        collection_count=1,
        node_ids=[node],
        passed_node_ids=[node],
        failed_node_ids=[],
        terminal_status="COMPLETE",
    )
    head = replace(
        _run(0, [], revision="head"),
        collection_count=1,
        node_ids=[node],
        passed_node_ids=[node],
        failed_node_ids=[],
        terminal_status="COMPLETE",
    )
    assert classify_regression(base, tamper(head, node)).classification == "IMPACT_UNKNOWN"


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
