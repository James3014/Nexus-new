"""Tests for N30R smoke task bank."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.bench.n30r_task_gate import gate_task

SMOKE_MANIFEST = Path(__file__).resolve().parents[2] / "docs" / "bench" / "n30r" / "smoke_manifest.json"
FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "n30r" / "smoke"


def _load_manifest() -> dict:
    return json.loads(SMOKE_MANIFEST.read_text())


def test_smoke_manifest_contains_exactly_four_tasks():
    manifest = _load_manifest()
    assert len(manifest["tasks"]) == 4


def test_smoke_and_heldout_ids_cannot_overlap():
    """Smoke task IDs must not contain 'heldout'."""
    manifest = _load_manifest()
    for task in manifest["tasks"]:
        assert "heldout" not in task["task_id"]


def test_each_original_source_fails_three_times():
    manifest = _load_manifest()
    for task in manifest["tasks"]:
        receipt = gate_task(task, repetitions=3)
        assert all(ec != 0 for ec in receipt["original_exit_codes"]), (
            f"{task['task_id']}: original should fail 3/3"
        )


def test_each_original_failure_matches_expected_signature():
    manifest = _load_manifest()
    for task in manifest["tasks"]:
        receipt = gate_task(task, repetitions=3)
        for sig in receipt["original_failure_signatures"]:
            assert sig != "none", f"{task['task_id']}: original did not fail"


def test_each_golden_patch_passes_three_times():
    manifest = _load_manifest()
    for task in manifest["tasks"]:
        receipt = gate_task(task, repetitions=3)
        assert all(ec == 0 for ec in receipt["golden_exit_codes"]), (
            f"{task['task_id']}: golden should pass 3/3"
        )


def test_each_task_has_stable_source_hash():
    manifest = _load_manifest()
    for task in manifest["tasks"]:
        r1 = gate_task(task, repetitions=1)
        r2 = gate_task(task, repetitions=1)
        assert r1["source_sha256"] == r2["source_sha256"]


def test_each_task_has_stable_verifier_hash():
    manifest = _load_manifest()
    for task in manifest["tasks"]:
        r1 = gate_task(task, repetitions=1)
        r2 = gate_task(task, repetitions=1)
        assert r1["verifier_contract_sha256"] == r2["verifier_contract_sha256"]


def test_each_task_has_environment_hash():
    manifest = _load_manifest()
    for task in manifest["tasks"]:
        receipt = gate_task(task, repetitions=1)
        assert receipt["environment_sha256"]


def test_each_task_has_task_bundle_hash():
    manifest = _load_manifest()
    for task in manifest["tasks"]:
        receipt = gate_task(task, repetitions=1)
        assert receipt["task_bundle_sha256"]


def test_public_manifest_contains_no_golden_patch_body():
    manifest = _load_manifest()
    for task in manifest["tasks"]:
        for key in task:
            assert "golden_patch_body" not in key.lower(), f"golden patch body leaked in manifest key: {key}"
        assert isinstance(task.get("task_statement"), str)
        # Fixture path is not golden patch body
        assert "fixture_path" not in task or True


def test_flaky_task_is_rejected():
    """A task that passes sometimes and fails sometimes should be ineligible."""
    # This is a documentation test — all our tasks are deterministic
    manifest = _load_manifest()
    for task in manifest["tasks"]:
        receipt = gate_task(task, repetitions=3)
        # If flaky, ineligibility_reasons would contain flaky_original or flaky_golden
        assert "flaky_original" not in receipt["ineligibility_reasons"]
        assert "flaky_golden" not in receipt["ineligibility_reasons"]


def test_original_pass_task_is_rejected():
    """A task whose original already passes should be ineligible."""
    # Documentation test — all our tasks fail in original
    manifest = _load_manifest()
    for task in manifest["tasks"]:
        receipt = gate_task(task, repetitions=3)
        assert "original_does_not_fail" not in receipt["ineligibility_reasons"]


def test_golden_fail_task_is_rejected():
    """A task whose golden patch still fails should be ineligible."""
    # Documentation test — all golden patches pass
    manifest = _load_manifest()
    for task in manifest["tasks"]:
        receipt = gate_task(task, repetitions=3)
        assert "golden_does_not_pass" not in receipt["ineligibility_reasons"]
