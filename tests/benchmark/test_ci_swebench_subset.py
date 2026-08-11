from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.bench.fixture_materialization import (
    LocalFixtureSource,
    deterministic_fixture_source,
    materialize_local_fixture,
)
from scripts.ci.run_benchmark_case import run_case
from scripts.ci.run_swebench_subset import (
    _classify_process,
    _valid_result,
    load_cases,
    main,
)


def _case(**overrides: object) -> dict[str, object]:
    case: dict[str, object] = {
        "task_id": "codex-dx-test",
        "fixture_kind": "codex_dx_parser",
        "verifier": "pytest_hidden",
        "patch": "deterministic",
    }
    case.update(overrides)
    return case


def _passing_result(task_id: str = "codex-dx-test") -> dict[str, object]:
    return {
        "task_id": task_id,
        "status": "passed",
        "passed": True,
        "fixture_sha256": "a" * 64,
        "patch_sha256": "b" * 64,
        "verifier_sha256": "c" * 64,
        "verifier_output": "1 passed",
    }


def test_five_cases_apply_patches_and_pass(tmp_path: Path) -> None:
    results = [run_case(case, tmp_path) for case in load_cases("smoke")]

    assert len(results) == 5
    assert all(result["passed"] for result in results)
    assert all(result["fixture_sha256"] for result in results)
    assert all(result["patch_sha256"] for result in results)
    assert all(result["verifier_sha256"] for result in results)


def test_unpatched_fixture_fails_hidden_verifier(tmp_path: Path) -> None:
    target, visible, hidden = deterministic_fixture_source("codex_dx_parser")
    materialized = materialize_local_fixture(
        tmp_path,
        task_id="unpatched",
        source=LocalFixtureSource(target, visible, hidden),
    )

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", materialized.hidden_test_file],
        cwd=materialized.case_dir,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert visible != hidden


@pytest.mark.parametrize(
    ("overrides", "status"),
    [
        ({"task_id": "../escape"}, "path_escape"),
        ({"fixture_kind": "missing"}, "missing_fixture"),
        ({"verifier": ""}, "missing_verifier"),
        ({"patch": ""}, "patch_failed"),
    ],
)
def test_case_negative_controls_fail_closed(
    tmp_path: Path, overrides: dict[str, object], status: str
) -> None:
    assert run_case(_case(**overrides), tmp_path)["status"] == status


def test_timeout_is_classified(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import scripts.ci.run_benchmark_case as module

    def timeout(*_args: object, **_kwargs: object) -> None:
        raise module.subprocess.TimeoutExpired("pytest", 1)

    monkeypatch.setattr(module.subprocess, "run", timeout)
    assert run_case(_case(task_id="slow"), tmp_path)["status"] == "timeout"


def test_false_zero_exit_is_not_pass(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import scripts.ci.run_benchmark_case as module

    process = subprocess.CompletedProcess([], 0, stdout="", stderr="")
    monkeypatch.setattr(module.subprocess, "run", lambda *_args, **_kwargs: process)

    assert run_case(_case(task_id="false-zero"), tmp_path)["passed"] is False


def test_aggregator_rejects_tampered_or_nonzero_results() -> None:
    passing = _passing_result()
    nonzero = subprocess.CompletedProcess([], 1, stdout=json.dumps(passing), stderr="")
    mismatch = subprocess.CompletedProcess(
        [], 0, stdout=json.dumps({**passing, "task_id": "wrong"}), stderr=""
    )

    assert _classify_process(nonzero, "codex-dx-test")["passed"] is False
    assert _classify_process(mismatch, "codex-dx-test")["passed"] is False
    assert not _valid_result({**passing, "verifier_output": "x" * 4097}, "codex-dx-test")


@pytest.mark.parametrize("cases", [[], [{"task_id": "duplicate"}] * 5])
def test_catalog_rejects_empty_or_duplicate_cases(
    tmp_path: Path, cases: list[dict[str, object]]
) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"cases": cases}), encoding="utf-8")

    with pytest.raises(ValueError, match="five|schema|unique"):
        load_cases("smoke", catalog)


def test_smoke_uses_temp_materialization_and_leaves_repo_cases_unchanged(
    tmp_path: Path,
) -> None:
    repo_cases = Path(".nexus/bench_cases")
    before = (
        sorted(path.as_posix() for path in repo_cases.rglob("*")) if repo_cases.exists() else []
    )
    output = tmp_path / "results.jsonl"

    assert main(["--mode", "smoke", "--output", str(output), "--timeout", "30"]) == 0

    after = sorted(path.as_posix() for path in repo_cases.rglob("*")) if repo_cases.exists() else []
    assert after == before
    assert len(output.read_text(encoding="utf-8").splitlines()) == 5


def test_workflow_matches_local_provider_free_command() -> None:
    workflow = Path(".github/workflows/benchmark-ci.yml").read_text(encoding="utf-8")

    assert 'python-version: "3.12"' in workflow
    assert "uv sync --frozen --all-groups" in workflow
    assert "run_swebench_subset.py" in workflow
    assert '--mode "$MODE"' in workflow
    assert "GEMINI_API_KEY" not in workflow
    assert "OPENAI_API_KEY" not in workflow
    assert "docker info" not in workflow
    assert "lite" not in workflow.lower()
