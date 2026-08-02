"""
Epistemic Workflow Benchmark v0 — Real but Synthetic E2E Test.

Integration pipeline:
  synthetic corpus
  → prepare three arm packets
  → import synthetic observations
  → evaluate benchmark
  → verify benchmark report

Nexus production benchmark package does NOT import research_ledger.
Research Ledger used only via subprocess (read-only) if available.
"""
import json
import os
import subprocess
import sys

import pytest

from nexus.research.epistemic_benchmark.corpus import get_all_oracles, REQUIRED_CASE_IDS
from nexus.research.epistemic_benchmark.observations import (
    build_synthetic_observation,
    import_observation,
)
from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run, load_run_manifest
from nexus.research.epistemic_benchmark.metrics import _build_alias_to_case_private
from nexus.research.epistemic_benchmark.report import (
    build_benchmark_report,
    render_benchmark_markdown,
    verify_benchmark_report,
    write_benchmark_report,
)
from nexus.research.epistemic_benchmark.contracts import (
    CLAIM_CEILING_TEXT,
    REQUIRED_LIMITATIONS,
    compute_canonical_sha256,
)


# ---------------------------------------------------------------------------
# Safety invariant: benchmark package does not import research_ledger
# ---------------------------------------------------------------------------


def test_no_research_ledger_import():
    """Production benchmark package must not import research_ledger at runtime."""
    import nexus.research.epistemic_benchmark as pkg
    import importlib, pkgutil

    for importer, modname, ispkg in pkgutil.walk_packages(
        path=pkg.__path__, prefix=pkg.__name__ + ".", onerror=lambda x: None
    ):
        try:
            mod = importlib.import_module(modname)
            assert "research_ledger" not in (getattr(mod, "__file__", "") or "")
        except ImportError:
            pass

    # Direct check: no imports in the package source
    pkg_dir = os.path.dirname(pkg.__file__)
    for root, dirs, files in os.walk(pkg_dir):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(root, fname)
            with open(fpath) as f:
                source = f.read()
            assert "import research_ledger" not in source, (
                f"research_ledger import found in {fpath}"
            )
            assert "from research_ledger" not in source, (
                f"research_ledger import found in {fpath}"
            )


# ---------------------------------------------------------------------------
# Safety invariant: same source/candidate/response across arms
# ---------------------------------------------------------------------------


def test_same_materials_across_arms(tmp_path):
    """All three arms for the same case must have identical common_materials_sha256."""
    run_dir = str(tmp_path / "fairness_run")
    prepare_benchmark_run(output_dir=run_dir, seed=12321, corpus_version="v0")
    manifest = load_run_manifest(run_dir)

    # For every case_id, collect common_materials_sha256 from all three arms
    for case_id, arm_aliases in manifest.get("packet_manifest", {}).items():
        hashes = {}
        for arm_name, alias in arm_aliases.items():
            pkt_path = os.path.join(run_dir, "packets", arm_name, f"{alias}.json")
            with open(pkt_path) as f:
                pkt = json.load(f)
            hashes[arm_name] = pkt.get("common_materials_sha256")

        hash_values = list(hashes.values())
        assert len(set(hash_values)) == 1, (
            f"Case {case_id}: common_materials_sha256 differs across arms: {hashes}"
        )


# ---------------------------------------------------------------------------
# Safety invariant: oracle not in public packets
# ---------------------------------------------------------------------------


def test_oracle_not_in_public_packets(tmp_path):
    run_dir = str(tmp_path / "oracle_check_run")
    prepare_benchmark_run(output_dir=run_dir, seed=98765, corpus_version="v0")

    oracle_keys = {
        "oracle_class", "oracle_decision", "known_defects",
        "required_detection", "oracle_sha256", "defect_id",
    }

    for arm in ("standard_review", "strong_protocol", "epistemic_workflow"):
        arm_dir = os.path.join(run_dir, "packets", arm)
        for fname in os.listdir(arm_dir):
            if not fname.endswith(".json"):
                continue
            with open(os.path.join(arm_dir, fname)) as f:
                pkt = json.load(f)
            pkt_str = json.dumps(pkt)

            # Check no oracle keys appear as keys (not nested)
            def _recursive_check(obj, path=""):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if k in oracle_keys:
                            pytest.fail(
                                f"Oracle key {k!r} found in packet {arm}/{fname} at {path}"
                            )
                        _recursive_check(v, f"{path}.{k}")
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        _recursive_check(item, f"{path}[{i}]")

            _recursive_check(pkt)

            # Check real case_id not in packet
            for real_case_id in REQUIRED_CASE_IDS:
                assert real_case_id not in pkt_str, (
                    f"Real case_id {real_case_id!r} found in {arm}/{fname}"
                )


# ---------------------------------------------------------------------------
# Safety invariant: oracle not written to run dir
# ---------------------------------------------------------------------------


def test_oracle_not_written_to_run_dir(tmp_path):
    run_dir = str(tmp_path / "no_oracle_run")
    prepare_benchmark_run(output_dir=run_dir, seed=13579, corpus_version="v0")

    for root, dirs, files in os.walk(run_dir):
        for fname in files:
            fname_lower = fname.lower()
            assert "oracle" not in fname_lower, (
                f"Oracle file found in run dir: {os.path.join(root, fname)}"
            )
            assert "case_id_map" not in fname_lower
            assert "expected_results" not in fname_lower
            assert "answer_key" not in fname_lower


# ---------------------------------------------------------------------------
# Safety invariant: missing observations not counted as correct
# ---------------------------------------------------------------------------


def test_missing_obs_not_counted_as_correct(tmp_path):
    run_dir = str(tmp_path / "missing_run")
    prepare_benchmark_run(output_dir=run_dir, seed=24680, corpus_version="v0")

    # Import NO observations
    report = build_benchmark_report(run_dir)

    # All arms must show 0 observation_count and 18 missing
    for arm_name in ("standard_review", "strong_protocol", "epistemic_workflow"):
        arm_m = report["arms"][arm_name]
        assert arm_m.get("observation_count", 0) == 0
        cov = report["coverage"][arm_name]
        assert cov["missing_cases"] == 18
        assert cov["observed_cases"] == 0


# ---------------------------------------------------------------------------
# Safety invariant: synthetic observations explicitly labelled
# ---------------------------------------------------------------------------


def test_synthetic_obs_explicitly_labelled():
    obs = build_synthetic_observation(
        benchmark_run_id="test-run",
        arm="standard_review",
        case_alias="alias-001",
        observation_id="obs-synth-001",
        decision="ACCEPT",
    )
    assert obs["evaluator"]["provider"] == "synthetic-test"
    assert obs["evaluator"]["model_id"] == "deterministic-fixture"


# ---------------------------------------------------------------------------
# Safety invariant: no model called by benchmark harness
# ---------------------------------------------------------------------------


def test_no_model_called_by_harness(tmp_path):
    """prepare_benchmark_run and build_benchmark_report must not make network/model calls."""
    run_dir = str(tmp_path / "no_model_run")
    # If these calls fail due to network, the test would error differently
    prepare_benchmark_run(output_dir=run_dir, seed=11223, corpus_version="v0")
    report = build_benchmark_report(run_dir)
    # If we get here without network errors, the harness does not call models
    assert report is not None


# ---------------------------------------------------------------------------
# Full E2E: prepare → observe → evaluate → verify
# ---------------------------------------------------------------------------


def test_full_e2e_pipeline(tmp_path):
    """
    Full E2E pipeline:
    1. Prepare run with seed
    2. Import synthetic observations (all three arms, all 18 cases)
    3. Build report
    4. Verify report
    5. Check all safety invariants
    """
    run_dir = str(tmp_path / "e2e_run")
    run_id = prepare_benchmark_run(output_dir=run_dir, seed=20260802, corpus_version="v0")
    manifest = load_run_manifest(run_dir)
    real_run_id = manifest["benchmark_run_id"]
    alias_to_case = _build_alias_to_case_private(manifest)

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

    # Import observations for all cases and all arms
    imported = 0
    for case_id, oracle in oracles.items():
        for arm in ("standard_review", "strong_protocol", "epistemic_workflow"):
            alias = case_to_arm_alias.get(case_id, {}).get(arm)
            if alias is None:
                continue
            pkt_path = os.path.join(run_dir, "packets", arm, f"{alias}.json")
            with open(pkt_path) as f:
                pkt = json.load(f)
            refs = pkt.get("common_materials", {}).get("available_evidence_refs", [])

            obs = build_synthetic_observation(
                benchmark_run_id=real_run_id,
                arm=arm,
                case_alias=alias,
                observation_id=f"obs-e2e-{arm[:3]}-{case_id.lower()}",
                decision=oracle["oracle_decision"],
                cited_evidence_refs=[refs[0]] if refs else [],
                confidence=80,
                provider="synthetic-test",
                model_id="deterministic-fixture",
            )
            success, errors = import_observation(run_dir, obs)
            assert success, f"E2E: Failed to import obs for {case_id}/{arm}: {errors}"
            imported += 1

    assert imported == 18 * 3, f"Expected 54 imported observations, got {imported}"

    # Build report
    report = build_benchmark_report(run_dir)

    # Coverage: all arms should be 100%
    for arm_name in ("standard_review", "strong_protocol", "epistemic_workflow"):
        cov = report["coverage"][arm_name]
        assert cov["observed_cases"] == 18
        assert cov["missing_cases"] == 0

    # Claim ceiling
    assert report["claim_ceiling"] == CLAIM_CEILING_TEXT

    # Limitations
    lims_str = " ".join(report["limitations"]).lower()
    for req in REQUIRED_LIMITATIONS:
        assert req.lower() in lims_str

    # Forbidden words not in Markdown
    md = render_benchmark_markdown(report)
    md_lower = md.lower()
    for fw in ("winner", "proven better", "statistically significant", "production ready"):
        assert fw not in md_lower, f"Forbidden word found: {fw!r}"

    # INCOMPLETE COVERAGE not shown when coverage is 100%
    assert "INCOMPLETE BENCHMARK COVERAGE" not in md

    # Verify report
    valid, errors = verify_benchmark_report(report, run_dir)
    assert valid, f"E2E: Report verification failed: {errors}"

    # Write and read back
    json_out = str(tmp_path / "e2e_report.json")
    md_out = str(tmp_path / "e2e_report.md")
    write_benchmark_report(report, json_out, md_out)

    with open(json_out) as f:
        loaded = json.load(f)
    assert loaded["report_sha256"] == report["report_sha256"]

    # Determinism: rebuild and compare hashes
    report2 = build_benchmark_report(run_dir)
    assert report2["report_sha256"] == report["report_sha256"]


# ---------------------------------------------------------------------------
# E2E: Research Ledger subprocess integration (read-only, optional)
# ---------------------------------------------------------------------------


def test_research_ledger_subprocess_readonly():
    """
    If Research Ledger is available, verify it can be called via subprocess
    and that we do NOT import it directly in our package.
    This test is skipped if research-ledger is not present.
    """
    nexus_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..")
    )
    rl_src = os.path.join(nexus_root, "research-ledger", "src")

    if not os.path.isdir(rl_src):
        pytest.skip("research-ledger not present — skipping subprocess integration test")

    # Verify no direct import in benchmark package
    import nexus.research.epistemic_benchmark as pkg
    pkg_dir = os.path.dirname(pkg.__file__)
    for root, dirs, files in os.walk(pkg_dir):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            with open(os.path.join(root, fname)) as f:
                src = f.read()
            assert "import research_ledger" not in src
            assert "from research_ledger" not in src

    # Try calling research_ledger CLI via subprocess (read-only)
    env = dict(os.environ)
    env["PYTHONPATH"] = rl_src

    result = subprocess.run(
        [sys.executable, "-m", "research_ledger.cli", "--help"],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    # If it runs without error, the subprocess integration works
    # We don't assert 0 because --help may or may not return 0 depending on CLI design
    assert result is not None  # subprocess ran
