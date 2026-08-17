"""
Tests for the Deterministic Epistemic Review Report (Milestone 3).
26 test cases covering all required scenarios.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

from nexus.research.epistemic_profile.report import (
    REPORT_SCHEMA,
    REPORT_TOP_LEVEL_KEYS,
    build_epistemic_review_report,
    render_epistemic_review_markdown,
    verify_epistemic_review_report,
    write_epistemic_review_report,
)
from tests.research.test_epistemic_profile_bridge_e2e import (
    _research_ledger_src,
)


def _run_rl_cli(args: list) -> subprocess.CompletedProcess:
    src = _research_ledger_src()
    inherited = os.environ.get("PYTHONPATH")
    pythonpath = str(src) if not inherited else os.pathsep.join((str(src), inherited))
    env = {**os.environ, "PYTHONPATH": pythonpath}
    cmd = [sys.executable, "-m", "research_ledger.cli"] + args
    return subprocess.run(cmd, env=env, capture_output=True, text=True)


def _run_nexus_cli(args: list) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-m", "nexus.research.epistemic_profile.cli"] + args
    return subprocess.run(cmd, capture_output=True, text=True)


def _build_valid_export(tmpdir: str) -> Dict[str, Any]:
    """Run full RL pipeline and return the export dict."""
    state_dir = os.path.join(tmpdir, "rl_state")
    export_file = os.path.join(tmpdir, "export.json")

    res_syn = _run_rl_cli(["run-gate-a-synthetic", "--state-dir", state_dir])
    assert res_syn.returncode == 0, f"run-gate-a-synthetic failed: {res_syn.stderr}"

    res_exp = _run_rl_cli(
        [
            "export-nexus-profile",
            "--state-dir",
            state_dir,
            "--run-id",
            "run_s1",
            "--task-id",
            "task_rpt_001",
            "--attempt-id",
            "att_rpt_001",
            "--profile-id",
            "prof_rpt_001",
            "--output",
            export_file,
        ]
    )
    assert res_exp.returncode == 0, f"export-nexus-profile failed: {res_exp.stderr}"

    with open(export_file, "r", encoding="utf-8") as f:
        return json.load(f), export_file


def _rehash_export(payload: dict) -> dict:
    p_sans = {k: v for k, v in payload.items() if k != "export_sha256"}
    canonical = json.dumps(p_sans, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    payload["export_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload


# ---------------------------------------------------------------------------
# Test 1: Positive report build
# ---------------------------------------------------------------------------


def test_01_positive_report_build():
    with tempfile.TemporaryDirectory() as tmpdir:
        export_data, export_file = _build_valid_export(tmpdir)
        report = build_epistemic_review_report(export_file)

        assert report["schema"] == REPORT_SCHEMA
        assert set(report.keys()) == REPORT_TOP_LEVEL_KEYS
        assert report["verification_status"] == "PASS"
        assert isinstance(report["records_checked"], int)
        assert report["records_checked"] >= 1
        assert isinstance(report["claim_count"], int)
        assert report["claim_count"] >= 1
        assert isinstance(report["report_sha256"], str)
        assert len(report["report_sha256"]) == 64


# ---------------------------------------------------------------------------
# Test 2: Deterministic repeated build
# ---------------------------------------------------------------------------


def test_02_deterministic_repeated_build():
    with tempfile.TemporaryDirectory() as tmpdir:
        _, export_file = _build_valid_export(tmpdir)
        r1 = build_epistemic_review_report(export_file)
        r2 = build_epistemic_review_report(export_file)
        assert r1 == r2


# ---------------------------------------------------------------------------
# Test 3: Claim IDs sorted
# ---------------------------------------------------------------------------


def test_03_claim_ids_sorted():
    with tempfile.TemporaryDirectory() as tmpdir:
        _, export_file = _build_valid_export(tmpdir)
        report = build_epistemic_review_report(export_file)
        claim_ids = [c["claim_id"] for c in report["claims"]]
        assert claim_ids == sorted(claim_ids)


# ---------------------------------------------------------------------------
# Test 4: Correct direction counts
# ---------------------------------------------------------------------------


def test_04_correct_direction_counts():
    with tempfile.TemporaryDirectory() as tmpdir:
        _, export_file = _build_valid_export(tmpdir)

        with open(export_file) as f:
            export_data = json.load(f)

        expected_counts = {}
        for rec in export_data.get("records", []):
            d = rec.get("direction", "unknown")
            expected_counts[d] = expected_counts.get(d, 0) + 1

        report = build_epistemic_review_report(export_file)
        got = report["global_summary"]["directions"]
        for d, cnt in expected_counts.items():
            assert got.get(d, 0) == cnt, f"Direction {d}: expected {cnt}, got {got.get(d, 0)}"


# ---------------------------------------------------------------------------
# Test 5: Correct scope counts
# ---------------------------------------------------------------------------


def test_05_correct_scope_counts():
    with tempfile.TemporaryDirectory() as tmpdir:
        _, export_file = _build_valid_export(tmpdir)

        with open(export_file) as f:
            export_data = json.load(f)

        expected_counts = {}
        for rec in export_data.get("records", []):
            s = rec.get("scope_alignment", "unknown")
            expected_counts[s] = expected_counts.get(s, 0) + 1

        report = build_epistemic_review_report(export_file)
        got = report["global_summary"]["scope_alignment"]
        for s, cnt in expected_counts.items():
            assert got.get(s, 0) == cnt, f"Scope {s}: expected {cnt}, got {got.get(s, 0)}"


# ---------------------------------------------------------------------------
# Test 6: Correct lineage counts
# ---------------------------------------------------------------------------


def test_06_correct_lineage_counts():
    with tempfile.TemporaryDirectory() as tmpdir:
        _, export_file = _build_valid_export(tmpdir)

        with open(export_file) as f:
            export_data = json.load(f)

        expected_counts = {}
        for rec in export_data.get("records", []):
            art = rec.get("artifact", {})
            li = art.get("lineage_independence", "unknown") if art else "unknown"
            expected_counts[li] = expected_counts.get(li, 0) + 1

        report = build_epistemic_review_report(export_file)
        got = report["global_summary"]["lineage_independence"]
        for li, cnt in expected_counts.items():
            assert got.get(li, 0) == cnt, f"Lineage {li}: expected {cnt}, got {got.get(li, 0)}"


# ---------------------------------------------------------------------------
# Test 7: Conflict detection (manipulate export to add contradicting record)
# ---------------------------------------------------------------------------


def test_07_conflict_detection():
    with tempfile.TemporaryDirectory() as tmpdir:
        _, export_file = _build_valid_export(tmpdir)
        with open(export_file) as f:
            data = json.load(f)

        # Duplicate first record with direction=contradicts on same claim
        if data.get("records"):
            orig = data["records"][0]
            dup = dict(orig)
            dup["direction"] = "contradicts"
            dup["cannot_establish_present"] = True
            data["records"].append(dup)

        # Also update verification.records_exported to match the added record
        data["verification"]["records_exported"] = len(data["records"])
        data = _rehash_export(data)

        conflict_file = os.path.join(tmpdir, "conflict_export.json")
        with open(conflict_file, "w") as f:
            json.dump(data, f)

        report = build_epistemic_review_report(conflict_file)
        assert report["global_summary"]["conflicting_claim_count"] >= 1
        conflicting = [c for c in report["claims"] if c["conflict_present"]]
        assert len(conflicting) >= 1


# ---------------------------------------------------------------------------
# Test 8: No conflict false positive
# ---------------------------------------------------------------------------


def test_08_no_conflict_false_positive():
    with tempfile.TemporaryDirectory() as tmpdir:
        _, export_file = _build_valid_export(tmpdir)
        report = build_epistemic_review_report(export_file)

        # Default synthetic run: single record with "supports" — no conflict
        assert report["global_summary"]["conflicting_claim_count"] == 0
        for claim in report["claims"]:
            assert not claim["conflict_present"]


# ---------------------------------------------------------------------------
# Test 9: Cannot-establish coverage
# ---------------------------------------------------------------------------


def test_09_cannot_establish_coverage():
    with tempfile.TemporaryDirectory() as tmpdir:
        _, export_file = _build_valid_export(tmpdir)

        with open(export_file) as f:
            data = json.load(f)

        sc_total = 0
        ce_true = 0
        for rec in data.get("records", []):
            if rec.get("direction") in ("supports", "contradicts"):
                sc_total += 1
                if rec.get("cannot_establish_present"):
                    ce_true += 1

        report = build_epistemic_review_report(export_file)
        cov = report["global_summary"]["cannot_establish_coverage"]
        assert isinstance(cov, str)
        assert len(cov) > 0
        # Verify it's a 4-decimal string
        assert "." in cov
        _, decimals = cov.split(".")
        assert len(decimals) == 4


# ---------------------------------------------------------------------------
# Test 10: Unique evidence ref count
# ---------------------------------------------------------------------------


def test_10_unique_evidence_ref_count():
    with tempfile.TemporaryDirectory() as tmpdir:
        _, export_file = _build_valid_export(tmpdir)
        with open(export_file) as f:
            data = json.load(f)

        unique_refs = set()
        for rec in data.get("records", []):
            ref = rec.get("extraction_ref", "")
            if ref:
                unique_refs.add(ref)

        report = build_epistemic_review_report(export_file)
        assert report["global_summary"]["unique_evidence_ref_count"] == len(unique_refs)


# ---------------------------------------------------------------------------
# Test 11: Unique receipt ref count
# ---------------------------------------------------------------------------


def test_11_unique_receipt_ref_count():
    with tempfile.TemporaryDirectory() as tmpdir:
        _, export_file = _build_valid_export(tmpdir)
        with open(export_file) as f:
            data = json.load(f)

        unique_refs = set()
        for rec in data.get("records", []):
            for rr in rec.get("receipt_refs", []):
                unique_refs.add(rr)

        report = build_epistemic_review_report(export_file)
        assert report["global_summary"]["unique_receipt_ref_count"] == len(unique_refs)


# ---------------------------------------------------------------------------
# Test 12: Report contains ClaimBoundary locks
# ---------------------------------------------------------------------------


def test_12_report_contains_claim_boundary_locks():
    with tempfile.TemporaryDirectory() as tmpdir:
        _, export_file = _build_valid_export(tmpdir)
        report = build_epistemic_review_report(export_file)

        auth = report["authority"]
        for key in (
            "runtime_update_allowed",
            "public_claim_allowed",
            "public_benchmark_allowed",
            "production_ready",
            "integration_approved",
        ):
            assert key in auth, f"Missing authority key: {key}"
            assert auth[key] is False, f"Authority key {key} must be False"


# ---------------------------------------------------------------------------
# Test 13: Report contains exact source export hash
# ---------------------------------------------------------------------------


def test_13_report_contains_exact_source_export_hash():
    with tempfile.TemporaryDirectory() as tmpdir:
        _, export_file = _build_valid_export(tmpdir)
        with open(export_file) as f:
            data = json.load(f)

        report = build_epistemic_review_report(export_file)
        assert report["source"]["export_sha256"] == data["export_sha256"]
        assert report["source"]["export_id"] == data["export_id"]


# ---------------------------------------------------------------------------
# Test 14: Report excludes forbidden keys
# ---------------------------------------------------------------------------


def test_14_report_excludes_forbidden_keys():
    with tempfile.TemporaryDirectory() as tmpdir:
        _, export_file = _build_valid_export(tmpdir)
        report = build_epistemic_review_report(export_file)
        report_str = json.dumps(report).lower()

        forbidden = [
            "original_text",
            "user_position",
            "salt",
            'can_establish":',
            'cannot_establish":',
            "reasoning_steps",
            "chain_of_thought",
        ]
        for f in forbidden:
            assert f not in report_str, f"Forbidden content found in report: {f!r}"


# ---------------------------------------------------------------------------
# Test 15: Markdown excludes forbidden content
# ---------------------------------------------------------------------------


def test_15_markdown_excludes_forbidden_content():
    with tempfile.TemporaryDirectory() as tmpdir:
        _, export_file = _build_valid_export(tmpdir)
        report = build_epistemic_review_report(export_file)
        md = render_epistemic_review_markdown(report)
        md_lower = md.lower()

        forbidden = [
            "original_text",
            "user_position",
            "salt",
            "can_establish",
            "reasoning_steps",
            "accepted",
            "proven",
            "production_ready: true",
        ]
        for f in forbidden:
            assert f not in md_lower, f"Forbidden content in Markdown: {f!r}"


# ---------------------------------------------------------------------------
# Test 16: Report hash tamper detected
# ---------------------------------------------------------------------------


def test_16_report_hash_tamper_detected():
    with tempfile.TemporaryDirectory() as tmpdir:
        _, export_file = _build_valid_export(tmpdir)
        report = build_epistemic_review_report(export_file)

        # Tamper the hash
        tampered = dict(report)
        tampered["report_sha256"] = "0" * 64

        result = verify_epistemic_review_report(tampered, export_file)
        assert result["status"] != "REVIEW_VERIFIED"
        assert any("REPORT_HASH_MISMATCH" in b for b in result.get("blockers", []))


# ---------------------------------------------------------------------------
# Test 17: Count tamper + recomputed hash still detected
# ---------------------------------------------------------------------------


def test_17_count_tamper_recomputed_hash_still_detected():
    with tempfile.TemporaryDirectory() as tmpdir:
        _, export_file = _build_valid_export(tmpdir)
        report = build_epistemic_review_report(export_file)

        # Tamper claim count and recompute hash (semantic forgery)
        forged = dict(report)
        forged["claim_count"] = 999
        forged["records_checked"] = 999
        # Recompute hash to pass naive hash check
        body = {k: v for k, v in forged.items() if k != "report_sha256"}
        canonical = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        forged["report_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()

        result = verify_epistemic_review_report(forged, export_file)
        # Must still detect forgery via semantic field comparison
        assert result["status"] != "REVIEW_VERIFIED"
        assert any("MISMATCH" in b for b in result.get("blockers", []))


# ---------------------------------------------------------------------------
# Test 18: Source export mismatch detected
# ---------------------------------------------------------------------------


def test_18_source_export_mismatch_detected():
    with tempfile.TemporaryDirectory() as tmpdir:
        _, export_file = _build_valid_export(tmpdir)
        report = build_epistemic_review_report(export_file)

        # Tamper source binding in report
        forged = json.loads(json.dumps(report))
        forged["source"]["export_sha256"] = "a" * 64
        forged["source"]["export_id"] = "wrong_id"
        # Recompute hash with forged content
        body = {k: v for k, v in forged.items() if k != "report_sha256"}
        canonical = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        forged["report_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()

        result = verify_epistemic_review_report(forged, export_file)
        assert result["status"] != "REVIEW_VERIFIED"


# ---------------------------------------------------------------------------
# Test 19: RETURN export cannot produce report
# ---------------------------------------------------------------------------


def test_19_return_export_cannot_produce_report():
    with tempfile.TemporaryDirectory() as tmpdir:
        _, export_file = _build_valid_export(tmpdir)
        with open(export_file) as f:
            data = json.load(f)

        # Corrupt the export hash to force RETURN
        data["export_sha256"] = "0" * 64
        bad_file = os.path.join(tmpdir, "bad_export.json")
        with open(bad_file, "w") as f:
            json.dump(data, f)

        with pytest.raises(ValueError, match="EP_REPORT_REQUIRES_VERIFIED_EXPORT"):
            build_epistemic_review_report(bad_file)


# ---------------------------------------------------------------------------
# Test 20: Report cannot contain accepted/proven status
# ---------------------------------------------------------------------------


def test_20_report_cannot_contain_accepted_or_proven():
    with tempfile.TemporaryDirectory() as tmpdir:
        _, export_file = _build_valid_export(tmpdir)
        report = build_epistemic_review_report(export_file)
        report_str = json.dumps(report).upper()

        # Status values that are forbidden anywhere in the report
        # (distinct from keys like "production_ready" which may appear as false flags)
        forbidden_status_values = ('"ACCEPTED"', '"PROVEN"', '"INTEGRATION_READY"')
        for forbidden in forbidden_status_values:
            assert forbidden not in report_str, f"Forbidden status value found: {forbidden}"

        # Authority flags must all be False (never True)
        auth = report["authority"]
        for key in (
            "runtime_update_allowed",
            "public_claim_allowed",
            "public_benchmark_allowed",
            "production_ready",
            "integration_approved",
        ):
            assert auth.get(key) is False, f"Authority key {key} must be False"


# ---------------------------------------------------------------------------
# Test 21: JSON/Markdown outputs atomic
# ---------------------------------------------------------------------------


def test_21_json_markdown_outputs_atomic():
    with tempfile.TemporaryDirectory() as tmpdir:
        _, export_file = _build_valid_export(tmpdir)
        json_out = os.path.join(tmpdir, "report.json")
        md_out = os.path.join(tmpdir, "report.md")

        write_epistemic_review_report(export_file, json_out, md_out)

        assert os.path.exists(json_out)
        assert os.path.exists(md_out)

        # Verify no temp files left behind
        for fname in os.listdir(tmpdir):
            assert not fname.startswith(".tmp_report_"), f"Temp file left: {fname}"


# ---------------------------------------------------------------------------
# Test 22: Existing outputs survive failure
# ---------------------------------------------------------------------------


def test_22_existing_outputs_survive_failure():
    with tempfile.TemporaryDirectory() as tmpdir:
        json_out = os.path.join(tmpdir, "report.json")
        md_out = os.path.join(tmpdir, "report.md")

        # Pre-write sentinel content
        with open(json_out, "w") as f:
            f.write("ORIGINAL_JSON")
        with open(md_out, "w") as f:
            f.write("ORIGINAL_MD")

        # Trigger failure with nonexistent export
        with pytest.raises(Exception):
            write_epistemic_review_report(
                os.path.join(tmpdir, "nonexistent.json"), json_out, md_out
            )

        with open(json_out) as f:
            assert f.read() == "ORIGINAL_JSON"
        with open(md_out) as f:
            assert f.read() == "ORIGINAL_MD"


# ---------------------------------------------------------------------------
# Test 23: Verify does not mutate source or report
# ---------------------------------------------------------------------------


def test_23_verify_does_not_mutate_source_or_report():
    with tempfile.TemporaryDirectory() as tmpdir:
        _, export_file = _build_valid_export(tmpdir)
        report = build_epistemic_review_report(export_file)

        import copy

        report_before = copy.deepcopy(report)

        # Read export file hash before
        sha_before = hashlib.sha256(Path(export_file).read_bytes()).hexdigest()

        verify_epistemic_review_report(report, export_file)

        # Export file unchanged
        sha_after = hashlib.sha256(Path(export_file).read_bytes()).hexdigest()
        assert sha_before == sha_after

        # Report dict unchanged
        assert report == report_before


# ---------------------------------------------------------------------------
# Test 24: CLI render-report positive
# ---------------------------------------------------------------------------


def test_24_cli_render_report_positive():
    with tempfile.TemporaryDirectory() as tmpdir:
        _, export_file = _build_valid_export(tmpdir)
        json_out = os.path.join(tmpdir, "report.json")
        md_out = os.path.join(tmpdir, "report.md")

        res = _run_nexus_cli(
            [
                "render-report",
                "--input",
                export_file,
                "--json-output",
                json_out,
                "--markdown-output",
                md_out,
            ]
        )
        assert res.returncode == 0, f"render-report failed: {res.stderr}"

        out = json.loads(res.stdout)
        assert out["status"] == "REVIEW_READY"
        assert out["public_claim_allowed"] is False
        assert out["production_ready"] is False
        assert len(out["report_sha256"]) == 64

        assert os.path.exists(json_out)
        assert os.path.exists(md_out)


# ---------------------------------------------------------------------------
# Test 25: CLI verify-report positive
# ---------------------------------------------------------------------------


def test_25_cli_verify_report_positive():
    with tempfile.TemporaryDirectory() as tmpdir:
        _, export_file = _build_valid_export(tmpdir)
        json_out = os.path.join(tmpdir, "report.json")
        md_out = os.path.join(tmpdir, "report.md")

        _run_nexus_cli(
            [
                "render-report",
                "--input",
                export_file,
                "--json-output",
                json_out,
                "--markdown-output",
                md_out,
            ]
        )

        res = _run_nexus_cli(
            [
                "verify-report",
                "--input",
                json_out,
                "--source-export",
                export_file,
            ]
        )
        assert res.returncode == 0, f"verify-report failed: {res.stderr}"

        out = json.loads(res.stdout)
        assert out["status"] == "REVIEW_VERIFIED"
        assert len(out["report_sha256"]) == 64


# ---------------------------------------------------------------------------
# Test 26: CLI invalid report → nonzero exit
# ---------------------------------------------------------------------------


def test_26_cli_invalid_report_nonzero_exit():
    with tempfile.TemporaryDirectory() as tmpdir:
        _, export_file = _build_valid_export(tmpdir)

        # Write bogus report JSON
        bad_report = os.path.join(tmpdir, "bad_report.json")
        with open(bad_report, "w") as f:
            json.dump({"schema": "wrong", "report_sha256": "0" * 64}, f)

        res = _run_nexus_cli(
            [
                "verify-report",
                "--input",
                bad_report,
                "--source-export",
                export_file,
            ]
        )
        assert res.returncode != 0
