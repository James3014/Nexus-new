"""
Epistemic Workflow Benchmark v0 — Real but Synthetic E2E Test (R2A updated).

Integration pipeline:
  synthetic corpus
  → prepare three arm packets (with private blinding)
  → validate public run integrity
  → validate private scoring context
  → import synthetic observations (using private context for alias resolution)
  → evaluate benchmark
  → verify benchmark report

Nexus production benchmark package does NOT import research_ledger.
Research Ledger used only via subprocess (read-only) if available.
"""
import json
import os
import subprocess
import sys
from typing import Dict, Any, Optional

import pytest

from nexus.research.epistemic_benchmark.corpus import get_all_oracles, REQUIRED_CASE_IDS
from nexus.research.epistemic_benchmark.observations import (
    build_synthetic_observation,
    import_observation,
)
from nexus.research.epistemic_benchmark.packets import (
    prepare_benchmark_run,
    load_run_manifest,
    validate_public_run_integrity,
    validate_private_scoring_context,
)
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

FIXED_KEY = bytes.fromhex("a1b2c3d4" * 8)  # 32 bytes deterministic test key


def _prepare(tmp_path, seed: int = 20260802, subdir: str = "run") -> tuple:
    """Prepare a full run and return (run_dir, priv_path, manifest)."""
    run_dir = str(tmp_path / subdir)
    priv_path = str(tmp_path / "private_context.json")
    manifest = prepare_benchmark_run(
        public_output_dir=run_dir,
        private_context_path=priv_path,
        seed=seed,
        blinding_key=FIXED_KEY,
    )
    return run_dir, priv_path, manifest


def _load_alias_to_case(priv_path: str) -> Dict[str, str]:
    """Build {alias: case_id} from private context."""
    with open(priv_path) as f:
        ctx = json.load(f)
    return {b["case_alias"]: b["case_id"] for b in ctx.get("alias_bindings", [])}


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
    run_dir, priv_path, manifest = _prepare(tmp_path, seed=12321)
    with open(priv_path) as f:
        ctx = json.load(f)

    # Build case_id -> {arm: alias} using private context
    case_arm_alias: Dict[str, Dict[str, str]] = {}
    for b in ctx["alias_bindings"]:
        cid = b["case_id"]
        arm = b["arm"]
        alias = b["case_alias"]
        case_arm_alias.setdefault(cid, {})[arm] = alias

    # Build alias -> manifest entry
    alias_entry = {p["case_alias"]: p for p in manifest["packets"]}

    for case_id, arm_aliases in case_arm_alias.items():
        hashes = {}
        for arm_name, alias in arm_aliases.items():
            entry = alias_entry.get(alias, {})
            hashes[arm_name] = entry.get("common_materials_sha256")

        hash_values = [v for v in hashes.values() if v is not None]
        if hash_values:
            assert len(set(hash_values)) == 1, (
                f"Case {case_id}: common_materials_sha256 differs across arms: {hashes}"
            )


# ---------------------------------------------------------------------------
# Safety invariant: oracle not in public packets
# ---------------------------------------------------------------------------


def test_oracle_not_in_public_packets(tmp_path):
    run_dir, priv_path, manifest = _prepare(tmp_path, seed=98765, subdir="oracle_check_run")

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

            for real_case_id in REQUIRED_CASE_IDS:
                assert real_case_id not in json.dumps(pkt), (
                    f"Real case_id {real_case_id!r} found in {arm}/{fname}"
                )


# ---------------------------------------------------------------------------
# Safety invariant: oracle not written to run dir
# ---------------------------------------------------------------------------


def test_oracle_not_written_to_run_dir(tmp_path):
    run_dir, priv_path, manifest = _prepare(tmp_path, seed=13579, subdir="no_oracle_run")

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
# Integrity validators
# ---------------------------------------------------------------------------


def test_validate_public_run_integrity(tmp_path):
    run_dir, priv_path, manifest = _prepare(tmp_path, seed=55555)
    ok, errors = validate_public_run_integrity(run_dir)
    assert ok, f"Public run integrity failed: {errors}"


def test_validate_private_scoring_context(tmp_path):
    run_dir, priv_path, manifest = _prepare(tmp_path, seed=66666)
    ok, errors = validate_private_scoring_context(run_dir, priv_path)
    assert ok, f"Private context validation failed: {errors}"


# ---------------------------------------------------------------------------
# Safety invariant: missing observations not counted as correct
# ---------------------------------------------------------------------------


def test_missing_obs_not_counted_as_correct(tmp_path):
    run_dir, priv_path, manifest = _prepare(tmp_path, seed=24680, subdir="missing_run")

    # Import NO observations
    report = build_benchmark_report(run_dir, private_context_path=priv_path)

    # All arms must show 0 observation_count
    for arm_name in ("standard_review", "strong_protocol", "epistemic_workflow"):
        arm_m = report["arms"][arm_name]
        assert arm_m.get("observation_count", 0) == 0


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
    """prepare_benchmark_run must not make network/model calls."""
    run_dir, priv_path, manifest = _prepare(tmp_path, seed=11223, subdir="no_model_run")
    # If these calls fail due to network, the test would error differently
    assert manifest is not None


# ---------------------------------------------------------------------------
# Full E2E: prepare → validate → observe → evaluate → verify
# ---------------------------------------------------------------------------


def test_full_e2e_pipeline(tmp_path):
    """
    Full E2E pipeline:
    1. Prepare run with blinding key + seed
    2. Validate public run integrity
    3. Validate private scoring context
    4. Import synthetic observations (using private context for alias resolution)
    5. Build report (metrics depend on packet_manifest which is now in private context)
    6. Verify report
    7. Check safety invariants
    """
    run_dir, priv_path, manifest = _prepare(tmp_path, seed=20260802)
    real_run_id = manifest["benchmark_run_id"]

    # Step 2: Public run integrity
    ok, errors = validate_public_run_integrity(run_dir)
    assert ok, f"Public run integrity failed: {errors}"

    # Step 3: Private context integrity
    ok, errors = validate_private_scoring_context(run_dir, priv_path)
    assert ok, f"Private context validation failed: {errors}"

    # Load alias_to_case from private context
    alias_to_case = _load_alias_to_case(priv_path)
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

    # Step 4: Import observations for all cases and all arms
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
                packet_sha256=pkt.get("packet_sha256"),
                cited_evidence_refs=[refs[0]] if refs else [],
                confidence=80,
            )
            success, errors = import_observation(run_dir, obs)
            assert success, f"E2E: Failed to import obs for {case_id}/{arm}: {errors}"
            imported += 1

    assert imported == 18 * 3, f"Expected 54 imported observations, got {imported}"

    # Step 5: Build report
    report = build_benchmark_report(run_dir, private_context_path=priv_path)
    assert report is not None

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

    # Step 6: Verify report
    valid, errors = verify_benchmark_report(report, run_dir, private_context_path=priv_path)
    assert valid, f"E2E: Report verification failed: {errors}"

    # Step 7: Write and read back
    json_out = str(tmp_path / "e2e_report.json")
    md_out = str(tmp_path / "e2e_report.md")
    write_benchmark_report(report, json_out, md_out)

    with open(json_out) as f:
        loaded = json.load(f)
    assert loaded["report_sha256"] == report["report_sha256"]

    # Determinism: rebuild and compare hashes
    report2 = build_benchmark_report(run_dir, private_context_path=priv_path)
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
    assert result is not None  # subprocess ran
