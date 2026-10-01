from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.bench import n30r_v2_runner as runner
from scripts.bench.fixture_materialization import ExternalFixturePolicyError
from scripts.bench.n30r_v2_paired_eval import load_manifest

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/bench/n30r/v2_four_task_paired_manifest.json"


def _manifest() -> dict:
    return load_manifest(str(MANIFEST))


@pytest.fixture(autouse=True)
def provider_spies(monkeypatch):
    """Every test is offline; a missed pre-provider guard must fail the test."""
    bare = Mock(side_effect=AssertionError("unexpected Bare provider call"))
    core = Mock(side_effect=AssertionError("unexpected Core provider construction"))
    monkeypatch.setattr(runner, "_ollama_provider_with_metrics", bare)
    monkeypatch.setattr(runner, "OllamaLocalModelProvider", core)
    yield bare, core
    bare.assert_not_called()
    core.assert_not_called()


def test_prepare_tasks_uses_one_hash_complete_materialized_source(tmp_path: Path):
    manifest = _manifest()
    prepared = runner._prepare_tasks(manifest, tmp_path)

    assert len(prepared) == 4
    for original, task in zip(manifest["tasks"], prepared):
        assert task["_materialized_source"]
        assert (
            hashlib.sha256((ROOT / original["source_relpath"]).read_bytes()).hexdigest()
            == original["source_fixture_sha256"]
        )
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


def test_prepare_tasks_rejects_duplicate_ids_before_materialization(tmp_path: Path):
    manifest = _manifest()
    manifest["tasks"] = [manifest["tasks"][0], copy.deepcopy(manifest["tasks"][0])]
    with pytest.raises(ExternalFixturePolicyError, match="duplicate task_id"):
        runner._prepare_tasks(manifest, tmp_path)


@pytest.mark.parametrize(
    "field,value", [("repo", "https://attacker.invalid/repo"), ("repo_ref", "HEAD")]
)
def test_prepare_tasks_rejects_hostile_repo_binding(tmp_path: Path, field: str, value: str):
    task = copy.deepcopy(_manifest()["tasks"][0])
    task[field] = value
    with pytest.raises(ExternalFixturePolicyError, match="repository/ref"):
        runner._prepare_tasks({"tasks": [task]}, tmp_path)


def test_prepare_tasks_rejects_symlink_fixture(tmp_path: Path, monkeypatch):
    fake_root = tmp_path / "repo"
    fixture = fake_root / "tests/fixtures/n30r/smoke/syntax_task.py"
    fixture.parent.mkdir(parents=True)
    outside = tmp_path / "outside.py"
    outside.write_text("ORIGINAL = 'bad'\n", encoding="utf-8")
    fixture.symlink_to(outside)
    monkeypatch.setattr(runner, "__file__", str(fake_root / "scripts/bench/n30r_v2_runner.py"))
    task = copy.deepcopy(_manifest()["tasks"][0])
    with pytest.raises(ExternalFixturePolicyError, match="symlink"):
        runner._prepare_tasks({"tasks": [task]}, tmp_path / "workspace")


def test_direct_row_source_hash_is_revalidated(tmp_path: Path):
    task = copy.deepcopy(_manifest()["tasks"][0])
    task["_materialized_source"] = "tampered"
    with pytest.raises(ExternalFixturePolicyError, match="direct-row fixture hash"):
        runner._require_task_source(task)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda task: task.update(source_fixture_sha256="0" * 64),
        lambda task: task.update(source_relpath="../outside.py"),
        lambda task: task.update(task_id="../escape"),
        lambda task: task.update(source_fixture_sha256="not-a-sha"),
    ],
)
def test_malformed_materialization_fails_before_provider_setup(tmp_path: Path, mutator):
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


@pytest.mark.parametrize("manifest", [None, [], {}, {"tasks": []}, {"tasks": [None]}])
def test_missing_or_malformed_manifest_is_rejected(manifest, tmp_path):
    with pytest.raises(ExternalFixturePolicyError):
        runner._prepare_tasks(manifest, tmp_path)


@pytest.mark.parametrize("task_id", [".", "../escape", "x/../same", "a/b", "/outside"])
def test_task_ids_cannot_alias_another_case(task_id, tmp_path):
    manifest = _manifest()
    manifest["tasks"][0]["task_id"] = task_id
    with pytest.raises(ExternalFixturePolicyError):
        runner._prepare_tasks(manifest, tmp_path)
    assert not (tmp_path / ".nexus").exists()


@pytest.mark.parametrize("arm", [runner.run_bare_row, runner.run_core_row])
@pytest.mark.parametrize(
    "field,value",
    [
        ("task_statement", "substituted statement"),
        ("verifier_command", ["python3", "-c", "raise SystemExit(0)"]),
        ("repo_ref", "HEAD"),
    ],
)
def test_prepared_direct_rows_revalidate_contract_before_provider(arm, field, value, tmp_path):
    task = runner._prepare_tasks(_manifest(), tmp_path)[0]
    task[field] = value
    with pytest.raises(ExternalFixturePolicyError):
        arm(task, task["task_seed"], "negative-direct")


@pytest.mark.parametrize("level", ["manifest", "task"])
def test_network_enabled_policy_is_rejected(level, tmp_path):
    manifest = _manifest()
    target = manifest if level == "manifest" else manifest["tasks"][0]
    target["network_allowed"] = True
    with pytest.raises(ExternalFixturePolicyError):
        runner._prepare_tasks(manifest, tmp_path)


def test_existing_case_is_not_overwritten(tmp_path):
    manifest = _manifest()
    runner._prepare_tasks(manifest, tmp_path)
    case = tmp_path / ".nexus/bench_cases" / manifest["tasks"][0]["task_id"]
    sentinel = case / "sentinel.txt"
    sentinel.write_text("retain", encoding="utf-8")
    with pytest.raises(ExternalFixturePolicyError):
        runner._prepare_tasks(manifest, tmp_path)
    assert sentinel.read_text(encoding="utf-8") == "retain"


def test_output_symlink_escape_has_no_external_write(tmp_path):
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (workspace / ".nexus").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ExternalFixturePolicyError):
        runner._prepare_tasks(_manifest(), workspace)
    assert not list(outside.iterdir())


@pytest.mark.parametrize("failure", ["adapter_missing", "cache_missing", "network"])
def test_canonical_adapter_failures_prevent_provider_setup(monkeypatch, tmp_path, failure):
    from dataclasses import replace

    from scripts.bench.fixture_materialization import (
        ExternalFixtureAdapterRequired,
        OfflineCachedExternalFixtureAdapter,
    )

    def adapter_factory(**kwargs):
        if failure == "adapter_missing":
            return None
        if failure == "cache_missing":
            kwargs["cache_manifest"] = None
        else:
            kwargs["cache_manifest"] = replace(kwargs["cache_manifest"], network_allowed=True)
        return OfflineCachedExternalFixtureAdapter(**kwargs)

    monkeypatch.setattr(runner, "OfflineCachedExternalFixtureAdapter", adapter_factory)
    with pytest.raises((ExternalFixturePolicyError, ExternalFixtureAdapterRequired)):
        runner._prepare_tasks(_manifest(), tmp_path)
    assert not list((tmp_path / ".nexus/bench_cases").glob("n30r_smoke_*"))


def test_fixture_data_is_not_executed():
    fixture = "ORIGINAL = 'source text'\nraise AssertionError('fixture executed')\n"
    assert runner._extract_fixture_source(fixture) == "source text"


@pytest.mark.parametrize("tamper", ["memory", "disk"])
def test_prepared_source_tamper_blocks_both_arms(tmp_path, tamper):
    task = runner._prepare_tasks(_manifest(), tmp_path)[0]
    if tamper == "memory":
        task["_materialized_source"] = "tampered"
    else:
        path = tmp_path / ".nexus/bench_cases" / task["task_id"] / task["source_relpath"]
        path.write_text("tampered", encoding="utf-8")
    for arm in (runner.run_bare_row, runner.run_core_row):
        with pytest.raises(ExternalFixturePolicyError):
            arm(task, task["task_seed"], "tampered-source")


def test_evaluation_arms_share_canonical_fixture_and_cleanup(monkeypatch, tmp_path):
    from scripts.bench import n30r_v2_paired_eval

    seen = []

    def row(task, seed, run_id):
        source = runner._require_task_source(task)
        root = Path(task["_materialized_root"])
        assert root.is_relative_to(ROOT / ".nexus/bench_cases")
        assert root.is_dir()
        seen.append((task["task_id"], source, task["_task_spec"], root))
        return {"terminal_status": "DRY_RUN", "solved": False, "candidate_hash": ""}

    monkeypatch.setattr(runner, "_check_environment", lambda: {"environment_valid": True})
    monkeypatch.setattr(runner, "run_bare_row", row)
    monkeypatch.setattr(runner, "run_core_row", row)
    monkeypatch.setattr(n30r_v2_paired_eval, "validate_results", lambda *_: {"status": "TEST_ONLY"})
    runner.run_evaluation(_manifest(), str(tmp_path / "rows.jsonl"), None)
    assert len(seen) == 8
    assert all(seen[index] == seen[index + 1] for index in range(0, 8, 2))
    assert all(not item[3].exists() for item in seen)


def test_core_failure_cleans_workspace_and_restores_environment(monkeypatch):
    import os

    task = _manifest()["tasks"][0]
    seen = []
    before = {key: value for key, value in os.environ.items() if key.startswith("NEXUS_")}

    def fail(request, **kwargs):
        root = Path(request.repo_root)
        assert root.is_relative_to(ROOT / ".nexus/bench_cases")
        assert (root / "f.py").read_text() == runner._read_fixture_original(task["source_relpath"])
        seen.append(root)
        raise RuntimeError("injected executor failure")

    monkeypatch.setattr(runner, "OllamaLocalModelProvider", lambda: object())
    monkeypatch.setattr(runner.LocalModelExecutor, "run", fail)
    with pytest.raises(RuntimeError, match="injected executor failure"):
        runner.run_core_row(task, task["task_seed"], "cleanup")
    assert len(seen) == 1 and not seen[0].exists()
    assert {key: value for key, value in os.environ.items() if key.startswith("NEXUS_")} == before


def test_bare_offline_patch_reaches_real_isolated_verifier(monkeypatch):
    task = _manifest()["tasks"][0]
    fake_provider = Mock(
        return_value=("SEARCH:\ndef greet(name)\nREPLACE:\ndef greet(name):\n", {})
    )
    monkeypatch.setattr(runner, "_ollama_provider_with_metrics", fake_provider)
    before = set((ROOT / ".nexus/bench_cases").glob("n30r-v2-*"))
    result = runner.run_bare_row(task, task["task_seed"], "offline")
    assert result["verifier_reached"] is True
    assert result["verifier_status"] == "pass"
    assert result["candidate_isolated"] is True
    assert fake_provider.call_count == 1
    assert set((ROOT / ".nexus/bench_cases").glob("n30r-v2-*")) == before
