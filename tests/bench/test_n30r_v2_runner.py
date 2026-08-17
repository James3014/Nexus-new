from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest

from scripts.bench.fixture_materialization import ExternalFixturePolicyError
from scripts.bench import n30r_v2_runner as runner
from scripts.bench.n30r_v2_paired_eval import load_manifest


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/bench/n30r/v2_four_task_paired_manifest.json"


def _manifest() -> dict:
    return load_manifest(str(MANIFEST))


def test_prepare_tasks_uses_one_hash_complete_materialized_source(tmp_path: Path):
    manifest = _manifest()
    prepared = runner._prepare_tasks(manifest, tmp_path)

    assert len(prepared) == 4
    for original, task in zip(manifest["tasks"], prepared):
        assert task["_materialized_source"]
        assert hashlib.sha256(
            (ROOT / original["source_relpath"]).read_bytes()
        ).hexdigest() == original["source_fixture_sha256"]
        case_dir = tmp_path / ".nexus" / "bench_cases" / original["task_id"]
        assert case_dir.is_dir()
        assert task["_materialized_source"] == runner._read_fixture_original(
            original["source_relpath"], materialized_root=case_dir
        )
        spec = task["_task_spec"]
        assert spec.task_id == original["task_id"]
        assert spec.source_sha256 == original["source_fixture_sha256"]
        assert spec.verifier_contract_sha256 == original["verifier_contract_sha256"]
        assert spec.task_bundle_sha256


@pytest.mark.parametrize(
    "mutator",
    [
        lambda task: task.update(source_fixture_sha256="0" * 64),
        lambda task: task.update(source_relpath="../outside.py"),
        lambda task: task.update(task_id="../escape"),
        lambda task: task.update(source_fixture_sha256="not-a-sha"),
    ],
)
def test_malformed_materialization_fails_before_provider_setup(
    tmp_path: Path, mutator
):
    task = copy.deepcopy(_manifest()["tasks"][0])
    mutator(task)
    called = []

    with pytest.raises((ExternalFixturePolicyError, OSError)):
        runner._prepare_tasks({"tasks": [task]}, tmp_path)

    assert called == []


def test_missing_fixture_fails_closed_without_provider_call(tmp_path: Path):
    task = copy.deepcopy(_manifest()["tasks"][0])
    task["source_relpath"] = "tests/fixtures/n30r/smoke/missing.py"
    called = []

    with pytest.raises(ExternalFixturePolicyError):
        runner._prepare_tasks({"tasks": [task]}, tmp_path)

    assert called == []


def test_run_evaluation_does_not_enter_an_arm_when_materialization_fails(
    monkeypatch, tmp_path: Path
):
    manifest = _manifest()
    manifest["tasks"][0]["source_fixture_sha256"] = "0" * 64
    calls = []
    monkeypatch.setattr(runner, "run_bare_row", lambda *args: calls.append("bare"))
    monkeypatch.setattr(runner, "run_core_row", lambda *args: calls.append("core"))
    monkeypatch.setattr(
        runner,
        "_check_environment",
        lambda: {"environment_valid": True},
    )

    with pytest.raises(ExternalFixturePolicyError):
        runner.run_evaluation(manifest, None, str(tmp_path / "summary.json"))

    assert calls == []
