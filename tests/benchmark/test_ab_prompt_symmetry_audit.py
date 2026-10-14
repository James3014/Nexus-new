"""S21/S22: captured-prompt symmetry audit and ABBA interleaving for the counted A/B."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.bench.agy_prompt_capture import capture_record, prompt_from_argv, write_record
from scripts.bench.prompt_symmetry_audit import (
    NO_TOOLS_PREFIX,
    TaskMaterial,
    audit_run,
    extra_lines,
    hidden_only_literals,
)

VISIBLE = "def test_v():\n    assert classify(False, {'verified': True}) == 'open'\n"
HIDDEN = (
    "def test_h():\n"
    "    assert classify(True, {'verified': True}) == 'resolved'\n"
    "    assert classify(True, {'verified': False}) == 'needs_evidence'\n"
)
BARE = (
    NO_TOOLS_PREFIX + "\n\nTask: Fix an incident classifier.\n\n[CURRENT SOURCE]\n"
    "def classify(smoke_passed, semantic_evidence):\n    return 'open'\n\n[CURRENT TESTS]\n"
    + VISIBLE
)


@pytest.fixture(autouse=True)
def _restore_environ():
    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)


def _material() -> dict[str, TaskMaterial]:
    return {
        "nexus-value-trust-002__1": TaskMaterial(
            task_id="nexus-value-trust-002", visible_test=VISIBLE, hidden_test=HIDDEN
        )
    }


def _capture(tmp_path: Path, arm: str, prompt: str) -> None:
    write_record(
        capture_record(
            ["--model", "m", "--print", prompt],
            "",
            {"NEXUS_BENCH_ARM": arm, "NEXUS_BENCH_CAPTURE_KEY": "nexus-value-trust-002__1"},
        ),
        str(tmp_path),
    )


def test_prompt_from_argv_reads_print_value() -> None:
    assert prompt_from_argv(["--model", "m", "-p", "hello"]) == "hello"
    assert prompt_from_argv(["--print=hi"]) == "hi"
    assert prompt_from_argv(["--model", "m"]) is None


def test_identical_prompts_except_no_tools_prefix_pass(tmp_path: Path) -> None:
    _capture(tmp_path, "without_nexus", BARE)
    _capture(tmp_path, "with_nexus", BARE.replace(NO_TOOLS_PREFIX, ""))
    report = audit_run(tmp_path, _material())
    assert report["status"] == "PASS", report


def test_hidden_literal_and_with_nexus_only_text_fail(tmp_path: Path) -> None:
    _capture(tmp_path, "without_nexus", BARE)
    _capture(
        tmp_path,
        "with_nexus",
        BARE + "\nNexus trust classifier decision table: return exactly 'needs_evidence'.\n",
    )
    report = audit_run(tmp_path, _material())
    task = report["tasks"][0]
    assert report["status"] == "FAIL"
    assert "needs_evidence" in task["hidden_hits"]
    assert "with_nexus_only_text" in task["violations"]
    assert "hidden_literal_in_with_nexus_prompt" in task["violations"]


def test_missing_visible_test_prior_art_and_second_call_fail(tmp_path: Path) -> None:
    _capture(tmp_path, "without_nexus", BARE)
    no_tests = BARE.split("[CURRENT TESTS]")[0] + "[Prior Art]\n"
    _capture(tmp_path, "with_nexus", no_tests)
    _capture(tmp_path, "with_nexus", no_tests)
    task = audit_run(tmp_path, _material())["tasks"][0]
    assert "visible_test_missing_from_with_nexus_prompt" in task["violations"]
    assert "prior_art_in_with_nexus_prompt" in task["violations"]
    assert "with_nexus_calls=2" in task["violations"]


def test_missing_bare_capture_and_unattributed_calls_fail(tmp_path: Path) -> None:
    _capture(tmp_path, "with_nexus", BARE)
    write_record(capture_record(["--print", "x"], "", {}), str(tmp_path))
    report = audit_run(tmp_path, _material())
    assert report["status"] == "FAIL"
    assert "bare_calls=0" in report["tasks"][0]["violations"]
    assert report["unattributed_captures"] == ["unknown__unknown"]


def test_row_level_violations_fail(tmp_path: Path) -> None:
    _capture(tmp_path, "without_nexus", BARE)
    _capture(tmp_path, "with_nexus", BARE)
    rows = [{"mode": "with_nexus", "task_id": "t", "trial_index": 1, "attempt_count": 2}]
    report = audit_run(tmp_path, _material(), rows=rows)
    assert report["status"] == "FAIL"
    assert report["row_violations"] == ["with_nexus:t#1:attempt_count>1"]


def test_hidden_only_literals_include_inventory_and_auto_literals() -> None:
    literals = hidden_only_literals(_material()["nexus-value-trust-002__1"])
    assert "needs_evidence" in literals
    assert "{'verified': False}" in literals
    assert "resolved" in literals  # auto: hidden-only string constant


def test_extra_lines_ignores_whitespace_and_no_tools_prefix() -> None:
    assert extra_lines("  Task:   x \n" + NO_TOOLS_PREFIX, "Task: x") == []
    assert extra_lines("Task: x\nHint: baseline", "Task: x") == ["Hint: baseline"]


def _fake_agy(tmp_path: Path) -> Path:
    fake = tmp_path / "fake-agy"
    fake.write_text('#!/bin/sh\necho \'{"status":"no_change","patch":""}\'\n', encoding="utf-8")
    fake.chmod(0o755)
    return fake


def _run_main_with_fake_arms(
    tmp_path: Path, monkeypatch, *, with_prompt_extra: str
) -> tuple[int, list[str], Path]:
    import scripts.bench.capability_ab_runner as runner

    order: list[str] = []
    out_dir = tmp_path / "out"

    def _call_agy(prompt: str) -> None:
        subprocess.run(
            [os.environ["NEXUS_AGY_BIN"], "--model", "m", "--print", prompt],
            check=True,
            capture_output=True,
        )

    def _row(mode: str, task) -> dict:
        return {
            "mode": mode,
            "task_id": task.id,
            "trial_index": task.trial_index,
            "status": "FAILED",
            "model_calls": 1,
        }

    def _bare_prompt(target_file: str, test_file: str, task) -> str:
        return (
            NO_TOOLS_PREFIX
            + f"\n\nTask: {task.task_desc}\n\n[CURRENT SOURCE]\n{Path(target_file).read_text()}\n\n"
            + f"[CURRENT TESTS]\n{Path(test_file).read_text()}"
        )

    def fake_with(*, task, target_file, test_file, **_kwargs):
        order.append(f"with:{task.id}")
        _call_agy(
            _bare_prompt(target_file, test_file, task).replace(NO_TOOLS_PREFIX, "")
            + with_prompt_extra
        )
        return _row("with_nexus", task)

    def fake_without(*, task, target_file, test_file, **_kwargs):
        order.append(f"bare:{task.id}")
        _call_agy(_bare_prompt(target_file, test_file, task))
        return _row("without_nexus", task)

    monkeypatch.setattr(runner, "run_with_nexus", fake_with)
    monkeypatch.setattr(runner, "run_without_nexus", fake_without)
    monkeypatch.setenv("NEXUS_AGY_BIN", str(_fake_agy(tmp_path)))
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capability_ab_runner.py",
            "--tasks-file",
            "scripts/bench/public_benchmark_nexus_value_v1.json",
            "--output-dir",
            str(out_dir),
            "--max-tasks",
            "2",
            "--repeat-trials",
            "1",
            "--difficulty",
            "all",
            "--repo-kind-filter",
            "all",
            "--materialize-missing",
            "--isolation-mode",
            "preserve_target",
            "--strict-llm-baseline",
        ],
    )
    code = runner.main()
    return code, order, out_dir


def test_counted_run_interleaves_abba_and_passes_symmetric_prompts(
    tmp_path: Path, monkeypatch
) -> None:
    code, order, out_dir = _run_main_with_fake_arms(tmp_path, monkeypatch, with_prompt_extra="")
    assert [item.split(":")[0] for item in order] == ["with", "bare", "bare", "with"]
    report = json.loads((out_dir / "prompt_symmetry_audit.json").read_text())
    assert report["status"] == "PASS", report
    assert code == 0


def test_counted_run_fails_on_with_nexus_only_prompt_text(tmp_path: Path, monkeypatch) -> None:
    code, _, out_dir = _run_main_with_fake_arms(
        tmp_path, monkeypatch, with_prompt_extra="\n[NEXUS ROUTE SUMMARY]\n{}\n"
    )
    report = json.loads((out_dir / "prompt_symmetry_audit.json").read_text())
    assert report["status"] == "FAIL"
    assert code == 3
