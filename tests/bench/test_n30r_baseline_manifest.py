from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "docs" / "bench" / "n30r_baseline_manifest.json"

_valid_sha_re = re.compile(r"^[0-9a-f]{40}$")


def _load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_n30r_manifest_has_valid_baseline_sha():
    manifest = _load_manifest()
    sha = manifest.get("baseline_commit_sha", "")
    assert sha, "baseline_commit_sha must not be empty"
    assert _valid_sha_re.match(sha), f"baseline_commit_sha malformed: {sha}"


def test_n30r_manifest_marks_n28_ineligible():
    manifest = _load_manifest()
    n28 = manifest["historical_runs"]["n28"]
    assert n28["capability_claim_eligible"] is False
    assert n28["capacity_claim_eligible"] is False
    assert n28["paired_baseline_eligible"] is False
    assert "task_bank_original_verifier_passes" in n28["reason_codes"]
    assert "bare_arm_not_bare" in n28["reason_codes"]
    assert "quadrant_execution_not_isolated" in n28["reason_codes"]


def test_n30r_manifest_marks_n30a_ineligible():
    manifest = _load_manifest()
    n30a = manifest["historical_runs"]["n30a"]
    assert n30a["capability_claim_eligible"] is False
    assert n30a["capacity_claim_eligible"] is False
    assert n30a["paired_baseline_eligible"] is False
    assert "task_bank_original_verifier_passes" in n30a["reason_codes"]
    assert "quadrant_execution_paths_identical" in n30a["reason_codes"]
    assert "model_call_evidence_incomplete" in n30a["reason_codes"]
    assert "empty_or_timeout_output_not_fail_closed" in n30a["reason_codes"]


def test_n30r_manifest_marks_m5_unpaired():
    manifest = _load_manifest()
    m5 = manifest["historical_runs"]["m5"]
    assert m5["paired_baseline_eligible"] is False
    assert "source_prompt_verifier_hashes_incomplete" in m5["reason_codes"]


def test_n30r_manifest_contains_forbidden_conclusions():
    manifest = _load_manifest()
    forbidden = manifest["forbidden_conclusions"]
    assert "n30a_zero_of_48_is_model_capacity_evidence" in forbidden
    assert "n28_is_strictly_comparable_to_m5" in forbidden
    assert "nexus_has_reached_local_model_ceiling" in forbidden
    assert len(forbidden) >= 3


def test_n30r_manifest_does_not_claim_n30r_ready():
    manifest = _load_manifest()
    assert manifest["status"] == "N30R_BASELINE_INVALIDATION_SEALED"
    for run_name in ("n28", "n30a"):
        for key in ("capability_claim_eligible", "capacity_claim_eligible", "paired_baseline_eligible"):
            assert manifest["historical_runs"][run_name][key] is False, (
                f"{run_name}.{key} must be false"
            )
    assert manifest["historical_runs"]["m5"]["paired_baseline_eligible"] is False
