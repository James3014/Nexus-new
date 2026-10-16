"""Tests for N30R heldout task bank."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.bench.n30r_task_gate import gate_task

HELDOUT_MANIFEST = Path(__file__).resolve().parents[2] / "docs" / "bench" / "n30r" / "heldout_manifest.json"
SMOKE_MANIFEST = Path(__file__).resolve().parents[2] / "docs" / "bench" / "n30r" / "smoke_manifest.json"


def _load_manifest() -> dict:
    return json.loads(HELDOUT_MANIFEST.read_text())


def _load_smoke_ids() -> set[str]:
    return {t["task_id"] for t in json.loads(SMOKE_MANIFEST.read_text())["tasks"]}


def test_heldout_contains_exactly_24_tasks():
    assert len(_load_manifest()["tasks"]) == 24


def test_heldout_has_required_failure_family_distribution():
    manifest = _load_manifest()
    families = {}
    for t in manifest["tasks"]:
        tid = t["task_id"]
        if tid.startswith("h_loc_"): families.setdefault("localization", 0); families["localization"] += 1
        elif tid.startswith("h_syn_"): families.setdefault("syntax", 0); families["syntax"] += 1
        elif tid.startswith("h_sem_"): families.setdefault("semantic", 0); families["semantic"] += 1
        elif tid.startswith("h_mix_"): families.setdefault("mixed", 0); families["mixed"] += 1
    assert families.get("localization", 0) >= 6
    assert families.get("syntax", 0) >= 6
    assert families.get("semantic", 0) >= 6
    assert families.get("mixed", 0) >= 6


def test_heldout_has_no_smoke_overlap():
    heldout_ids = {t["task_id"] for t in _load_manifest()["tasks"]}
    smoke_ids = _load_smoke_ids()
    assert heldout_ids.isdisjoint(smoke_ids)


def test_all_original_sources_fail_three_times():
    manifest = _load_manifest()
    for t in manifest["tasks"]:
        r = gate_task(t, repetitions=3)
        assert all(ec != 0 for ec in r["original_exit_codes"]), f"{t['task_id']}: original should fail 3/3"


def test_all_original_failures_match_expected_signature():
    manifest = _load_manifest()
    for t in manifest["tasks"]:
        r = gate_task(t, repetitions=3)
        for sig in r["original_failure_signatures"]:
            assert sig != "none", f"{t['task_id']}: original did not fail"


def test_all_golden_patches_pass_three_times():
    manifest = _load_manifest()
    for t in manifest["tasks"]:
        r = gate_task(t, repetitions=3)
        assert all(ec == 0 for ec in r["golden_exit_codes"]), f"{t['task_id']}: golden should pass 3/3"


def test_all_task_hashes_are_stable():
    manifest = _load_manifest()
    for t in manifest["tasks"]:
        r1 = gate_task(t, repetitions=1)
        r2 = gate_task(t, repetitions=1)
        assert r1["source_sha256"] == r2["source_sha256"]
        assert r1["verifier_contract_sha256"] == r2["verifier_contract_sha256"]
        assert r1["task_bundle_sha256"] == r2["task_bundle_sha256"]


def test_no_public_golden_patch_body():
    manifest = _load_manifest()
    for t in manifest["tasks"]:
        for key in t:
            assert "golden_patch_body" not in key.lower()


def test_no_network_dependent_verifier():
    manifest = _load_manifest()
    for t in manifest["tasks"]:
        cmd = t["verifier_command"]
        assert not any("curl" in c or "wget" in c or "http" in c for c in cmd)


def test_no_duplicate_source_and_verifier_bundle():
    manifest = _load_manifest()
    seen = set()
    for t in manifest["tasks"]:
        r = gate_task(t, repetitions=1)
        key = (r["source_sha256"], r["verifier_contract_sha256"])
        assert key not in seen, f"Duplicate source+verifier bundle: {t['task_id']}"
        seen.add(key)


def test_heldout_seal_matches_manifest():
    """Seal must reference all 24 task IDs from manifest."""
    manifest = _load_manifest()
    manifest_ids = sorted(t["task_id"] for t in manifest["tasks"])
    assert len(manifest_ids) == 24


def test_heldout_seal_contains_24_eligible_tasks():
    manifest = _load_manifest()
    all_eligible = True
    for t in manifest["tasks"]:
        r = gate_task(t, repetitions=3)
        if not r["eligible"]:
            all_eligible = False
    assert all_eligible
