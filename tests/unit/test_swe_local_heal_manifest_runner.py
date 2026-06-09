from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.services.local_heal.task_manifest import LocalHealTaskSpec
from benchmarking.swebench_lite.swe_local_heal import (
    build_result_row,
    build_tasks_from_manifest,
    build_tasks_from_manifest_specs,
    filter_specs_for_resume,
    filter_tasks_for_resume,
    localized_files_for_task,
    nexus_local_generate,
    ollama_generate,
    read_resume_task_ids,
)


def test_build_tasks_from_local_heal_20_manifest():
    dataset = [
        {
            "instance_id": f"astropy__astropy-{index}",
            "repo": "astropy/astropy",
            "base_commit": f"commit-{index}",
            "problem_statement": f"problem {index}",
        }
        for index in range(10)
    ]

    tasks = build_tasks_from_manifest("local-heal-20", dataset, root_dir=Path("/repo"))

    assert len(tasks) == 20
    assert tasks[0]["instance_id"] == "astropy__astropy-0"
    assert tasks[0]["manifest_task_id"] == "astropy-swe-verified-0"
    assert tasks[0]["env_profile"] == "astropy-legacy"
    assert tasks[0]["local_mode"] is False
    assert tasks[9]["manifest_task_id"] == "astropy-swe-verified-9"

    assert tasks[10]["manifest_task_id"] == "deepswe-task4"
    assert tasks[10]["local_mode"] is True
    assert tasks[10]["env_profile"] == "python-default"
    assert tasks[10]["repo_dir"] == Path("/repo")
    assert tasks[-1]["manifest_task_id"] == "free-threading-weakref"
    assert tasks[-1]["local_path"].name == "free_threading_ref_race.py"


def test_localized_files_for_local_task_anchors_to_manifest_file(tmp_path):
    local_file = tmp_path / "scripts" / "benchmarks" / "race.py"
    local_file.parent.mkdir(parents=True)
    local_file.write_text("def test_challenge():\n    pass\n", encoding="utf-8")
    task = {
        "local_mode": True,
        "repo_dir": tmp_path,
        "local_path": local_file,
    }

    localized = localized_files_for_task(task)

    assert localized == [("scripts/benchmarks/race.py", "def test_challenge():\n    pass\n")]


def test_build_local_manifest_slice_does_not_require_dataset():
    specs = (
        LocalHealTaskSpec(
            task_id="asyncio-barrier",
            kind="local_concurrency",
            family="concurrency",
            env_profile="python-default",
            local_path="scripts/benchmarks/asyncio_barrier_race_real.py",
        ),
    )

    tasks = build_tasks_from_manifest_specs(specs, dataset=None, root_dir=Path("/repo"))

    assert len(tasks) == 1
    assert tasks[0]["manifest_task_id"] == "asyncio-barrier"
    assert tasks[0]["local_mode"] is True


def test_ollama_generate_propagates_timeout_for_pipeline_classification(monkeypatch):
    def raise_timeout(*args, **kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr("nexus.services.local_heal.client.urllib.request.urlopen", raise_timeout)

    with pytest.raises(TimeoutError):
        ollama_generate("", "patch please", timeout=1, model="qwen2.5-coder:14b")


def test_default_local_generate_uses_ollama_when_provider_is_ollama(monkeypatch):
    called_urls = []

    def raise_provider_error(req, *args, **kwargs):
        called_urls.append(req.full_url)
        raise ConnectionRefusedError("ollama unavailable")

    monkeypatch.delenv("NEXUS_LOCAL_MODEL", raising=False)
    monkeypatch.setattr("nexus.services.local_heal.client.urllib.request.urlopen", raise_provider_error)

    with pytest.raises(ConnectionRefusedError):
        nexus_local_generate("", "patch please", timeout=1)

    assert called_urls == ["http://localhost:11434/api/generate"]


def test_build_result_row_uses_receipt_failure_reason_when_context_is_empty(tmp_path):
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text('{"failure_reason":"MODEL_EMPTY_RESPONSE"}\n', encoding="utf-8")
    ctx = SimpleNamespace(
        final_patch="",
        solve_eligible=False,
        failure_reason="",
        receipt_path=str(receipt_path),
    )
    task = {
        "instance_id": "astropy__astropy-12907",
        "manifest_task_id": "astropy-swe-verified-0",
        "env_profile": "astropy-legacy",
    }

    row = build_result_row(task, ctx)

    assert row["failure_reason"] == "MODEL_EMPTY_RESPONSE"


def test_build_result_row_never_leaves_unsolved_reason_empty():
    ctx = SimpleNamespace(
        final_patch="",
        solve_eligible=False,
        failure_reason="",
        receipt_path="",
    )
    task = {
        "instance_id": "astropy__astropy-12907",
        "manifest_task_id": "astropy-swe-verified-0",
        "env_profile": "astropy-legacy",
    }

    row = build_result_row(task, ctx)

    assert row["failure_reason"] == "NO_PATCH"


def test_read_resume_task_ids_keeps_only_passed_repair_rows(tmp_path):
    resume_path = tmp_path / "results.jsonl"
    resume_path.write_text(
        "\n".join(
            [
                '{"manifest_task_id":"deepswe-task4","solve_eligible":true}',
                '{"manifest_task_id":"asyncio-barrier","solve_eligible":false,"failure_reason":"MODEL_TIMEOUT"}',
                '{"manifest_task_id":"astropy-swe-verified-0","preflight_ready":true}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert read_resume_task_ids(resume_path, mode="repair") == {"deepswe-task4"}


def test_read_resume_task_ids_keeps_only_ready_preflight_rows(tmp_path):
    resume_path = tmp_path / "preflight.jsonl"
    resume_path.write_text(
        "\n".join(
            [
                '{"manifest_task_id":"deepswe-task4","preflight_ready":true}',
                '{"manifest_task_id":"astropy-swe-verified-0","preflight_ready":false,"failure_reason":"ASTROPY_DEPENDENCY_MISSING"}',
                '{"manifest_task_id":"synthetic","solve_eligible":true}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert read_resume_task_ids(resume_path, mode="preflight") == {"deepswe-task4"}


def test_filter_tasks_for_resume_skips_only_completed_manifest_ids():
    tasks = [
        {"manifest_task_id": "deepswe-task4", "instance_id": "local_fix_deepswe_task4.py"},
        {"manifest_task_id": "asyncio-barrier", "instance_id": "local_fix_asyncio_barrier.py"},
    ]

    remaining = filter_tasks_for_resume(tasks, {"deepswe-task4"})

    assert remaining == [{"manifest_task_id": "asyncio-barrier", "instance_id": "local_fix_asyncio_barrier.py"}]


def test_filter_specs_for_resume_skips_only_ready_specs():
    specs = (
        LocalHealTaskSpec(
            task_id="deepswe-task4",
            kind="local_concurrency",
            family="concurrency",
            env_profile="python-default",
            local_path="scripts/benchmarks/deepswe_task4_singleton_race.py",
        ),
        LocalHealTaskSpec(
            task_id="asyncio-barrier",
            kind="local_concurrency",
            family="concurrency",
            env_profile="python-default",
            local_path="scripts/benchmarks/asyncio_barrier_race_real.py",
        ),
    )

    remaining = filter_specs_for_resume(specs, {"deepswe-task4"})

    assert [spec.task_id for spec in remaining] == ["asyncio-barrier"]
