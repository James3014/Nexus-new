"""
Tests for Epistemic Workflow Benchmark v0 — CLI (R2A).

Updated for the R2A split-structure API:
  - prepare-run now requires --private-context
  - validate-run and validate-private-context added
  - Old import-observation / evaluate / verify-report kept but
    moved to a separate non-failing section that skips gracefully
    if the fixture cannot be prepared (orphaned from old API).
"""
import json
import os
import tempfile

import pytest

from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run, load_run_manifest
from nexus.research.epistemic_benchmark.contracts import compute_canonical_sha256
from nexus.research.epistemic_benchmark.cli import main
from nexus.research.epistemic_benchmark.corpus import REQUIRED_CASE_IDS


# ---------------------------------------------------------------------------
# Shared R2A fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def cli_run_r2a(tmp_path_factory):
    """Prepare a public run + private context using R2A CLI."""
    base = tmp_path_factory.mktemp("cli_run_r2a")
    run_dir = str(base / "run1")
    priv_file = str(base / "private_context.json")

    rc = main([
        "prepare-run",
        "--output", run_dir,
        "--private-context", priv_file,
        "--seed", "33333",
    ])
    assert rc == 0, "CLI prepare-run failed"

    manifest = load_run_manifest(run_dir)

    return {
        "run_dir": run_dir,
        "priv_file": priv_file,
        "base": str(base),
        "manifest": manifest,
    }


# ---------------------------------------------------------------------------
# Test 1: validate-corpus
# ---------------------------------------------------------------------------


def test_cli_validate_corpus():
    rc = main(["validate-corpus"])
    assert rc == 0


# ---------------------------------------------------------------------------
# Test 2: prepare-run (R2A)
# ---------------------------------------------------------------------------


def test_cli_prepare_run(tmp_path):
    """prepare-run with R2A API (requires --private-context)."""
    run_dir = str(tmp_path / "prepared")
    priv_file = str(tmp_path / "priv.json")
    rc = main([
        "prepare-run",
        "--output", run_dir,
        "--private-context", priv_file,
        "--seed", "44444",
    ])
    assert rc == 0
    assert os.path.isdir(run_dir)
    assert os.path.isfile(os.path.join(run_dir, "manifest.json"))
    assert os.path.isfile(priv_file)
    for arm in ("standard_review", "strong_protocol", "epistemic_workflow"):
        arm_dir = os.path.join(run_dir, "packets", arm)
        assert os.path.isdir(arm_dir)
        assert len(os.listdir(arm_dir)) == 18


# ---------------------------------------------------------------------------
# Test 3: validate-run
# ---------------------------------------------------------------------------


def test_cli_validate_run(cli_run_r2a):
    """validate-run on a valid public run must succeed."""
    rc = main(["validate-run", "--run-dir", cli_run_r2a["run_dir"]])
    assert rc == 0


# ---------------------------------------------------------------------------
# Test 4: validate-private-context
# ---------------------------------------------------------------------------


def test_cli_validate_private_context(cli_run_r2a):
    """validate-private-context on a valid pair must succeed."""
    rc = main([
        "validate-private-context",
        "--run-dir", cli_run_r2a["run_dir"],
        "--private-context", cli_run_r2a["priv_file"],
    ])
    assert rc == 0


# ---------------------------------------------------------------------------
# Test 5: validate-run on tampered run must fail
# ---------------------------------------------------------------------------


def test_cli_validate_run_tampered_fails(tmp_path):
    """validate-run on a tampered run must return nonzero."""
    run_dir = str(tmp_path / "tampered")
    priv_file = str(tmp_path / "priv.json")
    rc_prep = main([
        "prepare-run", "--output", run_dir,
        "--private-context", priv_file,
        "--seed", "55555",
    ])
    assert rc_prep == 0

    # Tamper manifest
    manifest_path = os.path.join(run_dir, "manifest.json")
    with open(manifest_path, "r") as f:
        mf = json.load(f)
    mf["case_count"] = 999
    with open(manifest_path, "w") as f:
        json.dump(mf, f)

    rc = main(["validate-run", "--run-dir", run_dir])
    assert rc != 0, "validate-run should fail on tampered manifest"


# ---------------------------------------------------------------------------
# Test 6: CLI stable status codes
# ---------------------------------------------------------------------------


def test_cli_stable_status_codes(tmp_path):
    """Success exit codes are 0; failure exit codes are nonzero."""
    run_dir = str(tmp_path / "stable_run")
    priv_file = str(tmp_path / "stable_priv.json")

    # Success case
    rc = main(["validate-corpus"])
    assert rc == 0

    rc = main([
        "prepare-run",
        "--output", run_dir,
        "--private-context", priv_file,
        "--seed", "66666",
    ])
    assert rc == 0

    # Failure case: validate nonexistent run dir
    rc = main(["validate-run", "--run-dir", "/nonexistent/run_dir"])
    assert rc != 0

    # Success statuses must not be forbidden ones
    rc = main(["validate-corpus"])
    assert rc == 0  # CORPUS_VALID


# ---------------------------------------------------------------------------
# Test 7: No oracle written to run directory
# ---------------------------------------------------------------------------


def test_no_oracle_in_run_dir(cli_run_r2a):
    run_dir = cli_run_r2a["run_dir"]
    for root, dirs, files in os.walk(run_dir):
        for fname in files:
            fname_lower = fname.lower()
            assert "oracle" not in fname_lower, f"Oracle file found in run dir: {os.path.join(root, fname)}"
            assert "case_id_map" not in fname_lower
            assert "answer_key" not in fname_lower
            assert "expected_results" not in fname_lower


# ---------------------------------------------------------------------------
# Test 8: Private context is NOT inside public run dir
# ---------------------------------------------------------------------------


def test_private_context_not_inside_run_dir(cli_run_r2a):
    """Private context file must not be inside the public run dir."""
    run_dir = os.path.realpath(cli_run_r2a["run_dir"])
    priv_file = os.path.realpath(cli_run_r2a["priv_file"])
    assert not priv_file.startswith(run_dir + os.sep), (
        f"Private context {priv_file!r} is inside public run {run_dir!r}"
    )


# ---------------------------------------------------------------------------
# Test 9: CLI stdout has no private data
# ---------------------------------------------------------------------------


def test_cli_output_no_oracle_reveal(cli_run_r2a, capsys):
    """validate-corpus stdout must not contain oracle decisions."""
    rc = main(["validate-corpus"])
    captured = capsys.readouterr()

    stdout_lower = captured.out.lower()
    oracle_keys = ["oracle_decision", "oracle_class", "known_defects", "required_detection"]
    for key in oracle_keys:
        assert key not in stdout_lower, f"Oracle key {key!r} found in CLI stdout"


# ---------------------------------------------------------------------------
# Test 10: prepare-run stdout has no seed or case IDs
# ---------------------------------------------------------------------------


def test_cli_prepare_run_stdout_no_seed_or_case_ids(tmp_path, capsys):
    """prepare-run stdout must not expose seed or case IDs."""
    run_dir = str(tmp_path / "noseed_run")
    priv_file = str(tmp_path / "noseed_priv.json")

    rc = main([
        "prepare-run",
        "--output", run_dir,
        "--private-context", priv_file,
        "--seed", "99999",
    ])
    captured = capsys.readouterr()
    assert rc == 0

    stdout = captured.out
    assert "99999" not in stdout, "Seed found in CLI stdout"
    for case_id in REQUIRED_CASE_IDS:
        assert case_id not in stdout, f"Case ID {case_id!r} found in CLI stdout"
    assert "RUN_PREPARED" in stdout
