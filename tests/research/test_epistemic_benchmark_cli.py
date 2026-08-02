"""
Tests for Epistemic Workflow Benchmark v0 — CLI.
Covers all 10 required test cases (Section 28 of spec).
"""
import json
import os
import subprocess
import sys
import tempfile

import pytest

from nexus.research.epistemic_benchmark.observations import (
    build_synthetic_observation,
)
from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run, load_run_manifest
from nexus.research.epistemic_benchmark.metrics import _build_alias_to_case_private
from nexus.research.epistemic_benchmark.contracts import compute_canonical_sha256
from nexus.research.epistemic_benchmark.cli import main


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def cli_run(tmp_path_factory):
    base = tmp_path_factory.mktemp("cli_run")
    run_dir = str(base / "run1")

    # Prepare a run using CLI
    rc = main(["prepare-run", "--output", run_dir, "--seed", "33333"])
    assert rc == 0

    manifest = load_run_manifest(run_dir)
    run_id = manifest["benchmark_run_id"]
    alias_to_case = _build_alias_to_case_private(manifest)

    from nexus.research.epistemic_benchmark.corpus import get_all_oracles
    oracles = {o["case_id"]: o for o in get_all_oracles()}

    def _arm_of(alias):
        for arm in ("standard_review", "strong_protocol", "epistemic_workflow"):
            if os.path.exists(os.path.join(run_dir, "packets", arm, f"{alias}.json")):
                return arm
        return None

    case_to_arm_alias = {}
    for alias, cid in alias_to_case.items():
        arm = _arm_of(alias)
        if arm:
            case_to_arm_alias.setdefault(cid, {})[arm] = alias

    # Write a few observation JSON files
    obs_files = []
    for i, (case_id, oracle) in enumerate(list(oracles.items())[:3]):
        for arm in ("standard_review",):
            alias = case_to_arm_alias.get(case_id, {}).get(arm)
            if alias is None:
                continue
            pkt_path = os.path.join(run_dir, "packets", arm, f"{alias}.json")
            with open(pkt_path) as f:
                pkt = json.load(f)
            refs = pkt.get("common_materials", {}).get("available_evidence_refs", [])
            obs = build_synthetic_observation(
                benchmark_run_id=run_id,
                arm=arm,
                case_alias=alias,
                observation_id=f"obs-cli-{case_id.lower()}-001",
                decision=oracle["oracle_decision"],
                cited_evidence_refs=[refs[0]] if refs else [],
                confidence=80,
            )
            obs_path = str(base / f"obs_{case_id}_{arm}.json")
            with open(obs_path, "w") as f:
                json.dump(obs, f)
            obs_files.append(obs_path)

    return {
        "run_dir": run_dir,
        "base": str(base),
        "manifest": manifest,
        "obs_files": obs_files,
    }


# ---------------------------------------------------------------------------
# Test 1: validate-corpus
# ---------------------------------------------------------------------------


def test_cli_validate_corpus():
    rc = main(["validate-corpus"])
    assert rc == 0


# ---------------------------------------------------------------------------
# Test 2: prepare-run
# ---------------------------------------------------------------------------


def test_cli_prepare_run(tmp_path):
    run_dir = str(tmp_path / "prepared")
    rc = main(["prepare-run", "--output", run_dir, "--seed", "44444"])
    assert rc == 0
    assert os.path.isdir(run_dir)
    assert os.path.isfile(os.path.join(run_dir, "manifest.json"))
    for arm in ("standard_review", "strong_protocol", "epistemic_workflow"):
        arm_dir = os.path.join(run_dir, "packets", arm)
        assert os.path.isdir(arm_dir)
        assert len(os.listdir(arm_dir)) == 18


# ---------------------------------------------------------------------------
# Test 3: import-observation
# ---------------------------------------------------------------------------


def test_cli_import_observation(cli_run):
    run_dir = cli_run["run_dir"]
    obs_path = cli_run["obs_files"][0]

    rc = main(["import-observation", "--run-dir", run_dir, "--input", obs_path])
    assert rc == 0


# ---------------------------------------------------------------------------
# Test 4: evaluate
# ---------------------------------------------------------------------------


def test_cli_evaluate(cli_run, tmp_path):
    run_dir = cli_run["run_dir"]
    json_out = str(tmp_path / "report.json")
    md_out = str(tmp_path / "report.md")

    # Import remaining observations first
    for obs_path in cli_run["obs_files"][1:]:
        main(["import-observation", "--run-dir", run_dir, "--input", obs_path])

    rc = main(["evaluate", "--run-dir", run_dir, "--json-output", json_out, "--markdown-output", md_out])
    assert rc == 0
    assert os.path.isfile(json_out)
    assert os.path.isfile(md_out)

    with open(json_out) as f:
        report = json.load(f)
    assert "report_sha256" in report
    assert report.get("schema", "").startswith("nexus.epistemic_benchmark_report")


# ---------------------------------------------------------------------------
# Test 5: verify-report
# ---------------------------------------------------------------------------


def test_cli_verify_report(cli_run, tmp_path):
    run_dir = cli_run["run_dir"]
    json_out = str(tmp_path / "vreport.json")
    md_out = str(tmp_path / "vreport.md")

    rc_eval = main(["evaluate", "--run-dir", run_dir, "--json-output", json_out, "--markdown-output", md_out])
    assert rc_eval == 0

    rc = main(["verify-report", "--run-dir", run_dir, "--input", json_out])
    assert rc == 0


# ---------------------------------------------------------------------------
# Test 6: Invalid observation nonzero
# ---------------------------------------------------------------------------


def test_cli_invalid_observation_nonzero(cli_run, tmp_path):
    run_dir = cli_run["run_dir"]
    bad_obs = {"schema": "bad", "observation_id": "obs-invalid-999"}
    bad_path = str(tmp_path / "bad_obs.json")
    with open(bad_path, "w") as f:
        json.dump(bad_obs, f)

    rc = main(["import-observation", "--run-dir", run_dir, "--input", bad_path])
    assert rc != 0


# ---------------------------------------------------------------------------
# Test 7: Invalid report nonzero
# ---------------------------------------------------------------------------


def test_cli_invalid_report_nonzero(cli_run, tmp_path):
    run_dir = cli_run["run_dir"]
    bad_report = {"schema": "nexus.epistemic_benchmark_report.v0", "report_sha256": "badhash"}
    bad_path = str(tmp_path / "bad_report.json")
    with open(bad_path, "w") as f:
        json.dump(bad_report, f)

    rc = main(["verify-report", "--run-dir", run_dir, "--input", bad_path])
    assert rc != 0


# ---------------------------------------------------------------------------
# Test 8: No oracle written to run directory
# ---------------------------------------------------------------------------


def test_no_oracle_in_run_dir(cli_run):
    run_dir = cli_run["run_dir"]
    for root, dirs, files in os.walk(run_dir):
        for fname in files:
            fname_lower = fname.lower()
            assert "oracle" not in fname_lower, f"Oracle file found in run dir: {os.path.join(root, fname)}"
            assert "case_id_map" not in fname_lower
            assert "answer_key" not in fname_lower
            assert "expected_results" not in fname_lower


# ---------------------------------------------------------------------------
# Test 9: CLI output does not reveal oracle
# ---------------------------------------------------------------------------


def test_cli_output_no_oracle_reveal(cli_run, tmp_path, capsys):
    """validate-corpus stdout must not contain oracle decisions."""
    rc = main(["validate-corpus"])
    captured = capsys.readouterr()

    stdout_lower = captured.out.lower()
    oracle_keys = ["oracle_decision", "oracle_class", "known_defects", "required_detection"]
    for key in oracle_keys:
        assert key not in stdout_lower, f"Oracle key {key!r} found in CLI stdout"


# ---------------------------------------------------------------------------
# Test 10: Stable status codes
# ---------------------------------------------------------------------------


def test_cli_stable_status_codes(tmp_path):
    """Success exit codes are 0; failure exit codes are nonzero."""
    run_dir = str(tmp_path / "stable_run")

    # Success case
    rc = main(["validate-corpus"])
    assert rc == 0

    rc = main(["prepare-run", "--output", run_dir, "--seed", "66666"])
    assert rc == 0

    # Failure case: nonexistent input
    rc = main(["import-observation", "--run-dir", run_dir, "--input", "/nonexistent/obs.json"])
    assert rc != 0

    # Success statuses must not be forbidden ones
    # (We simply ensure the CLI returns 0 for successful ops)
    rc = main(["validate-corpus"])
    assert rc == 0  # CORPUS_VALID
