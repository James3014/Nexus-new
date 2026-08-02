from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
import pytest

from research_ledger.gate_a_harness import run_gate_a_synthetic
from research_ledger.nexus_profile_export import export_nexus_epistemic_profile

from nexus.research.epistemic_profile.contracts import EpistemicIntegrityStatus
from nexus.research.epistemic_profile.io import (
    load_epistemic_profile_export,
    verify_epistemic_profile_export,
    write_epistemic_receipt,
    FORBIDDEN_KEYS,
)


def _rehash_export(payload: dict) -> dict:
    p_sans = {k: v for k, v in payload.items() if k != "export_sha256"}
    canonical = json.dumps(p_sans, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    payload["export_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload


def test_positive_end_to_end_bridge_pipeline():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = os.path.join(tmpdir, "rl_state")
        export_file = os.path.join(tmpdir, "export.json")
        receipt_file = os.path.join(tmpdir, "receipt.json")

        run_gate_a_synthetic(state_dir)

        payload = export_nexus_epistemic_profile(
            state_dir=state_dir,
            run_id="run_s1",
            task_id="task_e2e_001",
            attempt_id="att_e2e_001",
            profile_id="prof_e2e_001",
            output_path=export_file,
        )
        assert os.path.exists(export_file)

        # Nexus Verification
        res = verify_epistemic_profile_export(export_file)
        assert res.status == EpistemicIntegrityStatus.PASS
        assert res.records_checked > 0

        # Receipt writing
        rcpt = write_epistemic_receipt(res, receipt_file)
        assert rcpt["runtime_update_allowed"] is False
        assert rcpt["public_claim_allowed"] is False
        assert rcpt["public_benchmark_allowed"] is False
        assert rcpt["production_ready"] is False
        assert rcpt["integration_approved"] is False


def test_negative_1_corrupted_evidence_pipeline_fails_export():
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = os.path.join(tmpdir, "rl_state")
            export_file = os.path.join(tmpdir, "export.json")
            run_gate_a_synthetic(state_dir)

            # Corrupt evidence database
            db_path = os.path.join(state_dir, "public", "evidence.sqlite3")
            if os.path.exists(db_path):
                os.remove(db_path)

            with pytest.raises(RuntimeError, match="EXPORT_VERIFICATION_FAILED"):
                export_nexus_epistemic_profile(
                    state_dir=state_dir,
                    run_id="run_s1",
                    task_id="t1",
                    attempt_id="a1",
                    profile_id="p1",
                    output_path=export_file,
                )
            assert not os.path.exists(export_file)


def test_negative_2_modified_export_hash_fails_closed():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = os.path.join(tmpdir, "rl_state")
        export_file = os.path.join(tmpdir, "export.json")
        run_gate_a_synthetic(state_dir)
        payload = export_nexus_epistemic_profile(
            state_dir=state_dir,
            run_id="run_s1",
            task_id="t1",
            attempt_id="a1",
            profile_id="p1",
            output_path=export_file,
        )

        payload["export_sha256"] = "0" * 64
        with open(export_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        res = verify_epistemic_profile_export(export_file)
        assert res.status == EpistemicIntegrityStatus.RETURN
        assert "EP_EXPORT_HASH_MISMATCH" in res.blockers


def test_negative_3_source_text_forgery_rehashed_fails_closed():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = os.path.join(tmpdir, "rl_state")
        export_file = os.path.join(tmpdir, "export.json")
        run_gate_a_synthetic(state_dir)
        payload = export_nexus_epistemic_profile(
            state_dir=state_dir,
            run_id="run_s1",
            task_id="t1",
            attempt_id="a1",
            profile_id="p1",
            output_path=export_file,
        )

        payload["records"][0]["source_text"] = "forged raw text"
        payload = _rehash_export(payload)
        with open(export_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        res = verify_epistemic_profile_export(export_file)
        assert res.status == EpistemicIntegrityStatus.RETURN
        assert "EP_FORBIDDEN_KEY_DETECTED" in res.blockers


def test_negative_4_user_position_forgery_rehashed_fails_closed():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = os.path.join(tmpdir, "rl_state")
        export_file = os.path.join(tmpdir, "export.json")
        run_gate_a_synthetic(state_dir)
        payload = export_nexus_epistemic_profile(
            state_dir=state_dir,
            run_id="run_s1",
            task_id="t1",
            attempt_id="a1",
            profile_id="p1",
            output_path=export_file,
        )

        payload["user_position"] = "secret_user_opinion"
        payload = _rehash_export(payload)
        with open(export_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        res = verify_epistemic_profile_export(export_file)
        assert res.status == EpistemicIntegrityStatus.RETURN
        assert "EP_FORBIDDEN_KEY_DETECTED" in res.blockers


def test_negative_5_absolute_path_artifact_ref_fails_closed():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = os.path.join(tmpdir, "rl_state")
        export_file = os.path.join(tmpdir, "export.json")
        run_gate_a_synthetic(state_dir)
        payload = export_nexus_epistemic_profile(
            state_dir=state_dir,
            run_id="run_s1",
            task_id="t1",
            attempt_id="a1",
            profile_id="p1",
            output_path=export_file,
        )

        payload["records"][0]["artifact"]["relative_ref"] = "/etc/passwd"
        payload = _rehash_export(payload)
        with open(export_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        res = verify_epistemic_profile_export(export_file)
        assert res.status == EpistemicIntegrityStatus.RETURN


def test_negative_6_path_traversal_artifact_ref_fails_closed():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = os.path.join(tmpdir, "rl_state")
        export_file = os.path.join(tmpdir, "export.json")
        run_gate_a_synthetic(state_dir)
        payload = export_nexus_epistemic_profile(
            state_dir=state_dir,
            run_id="run_s1",
            task_id="t1",
            attempt_id="a1",
            profile_id="p1",
            output_path=export_file,
        )

        payload["records"][0]["artifact"]["relative_ref"] = "../secret.txt"
        payload = _rehash_export(payload)
        with open(export_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        res = verify_epistemic_profile_export(export_file)
        assert res.status == EpistemicIntegrityStatus.RETURN


def test_negative_7_cross_run_record_fails_closed():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = os.path.join(tmpdir, "rl_state")
        export_file = os.path.join(tmpdir, "export.json")
        run_gate_a_synthetic(state_dir)
        payload = export_nexus_epistemic_profile(
            state_dir=state_dir,
            run_id="run_s1",
            task_id="t1",
            attempt_id="a1",
            profile_id="p1",
            output_path=export_file,
        )

        payload["records"][0]["run_id"] = "run_OTHER"
        payload = _rehash_export(payload)
        with open(export_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        res = verify_epistemic_profile_export(export_file)
        assert res.status == EpistemicIntegrityStatus.RETURN
        assert "EP_CROSS_RUN_RECORD" in res.blockers


def test_negative_14_records_count_mismatch_fails_closed():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = os.path.join(tmpdir, "rl_state")
        export_file = os.path.join(tmpdir, "export.json")
        run_gate_a_synthetic(state_dir)
        payload = export_nexus_epistemic_profile(
            state_dir=state_dir,
            run_id="run_s1",
            task_id="t1",
            attempt_id="a1",
            profile_id="p1",
            output_path=export_file,
        )

        payload["verification"]["records_exported"] = 999
        payload = _rehash_export(payload)
        with open(export_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        res = verify_epistemic_profile_export(export_file)
        assert res.status == EpistemicIntegrityStatus.RETURN
        assert "EP_RECORDS_COUNT_MISMATCH" in res.blockers


def test_negative_15_unknown_top_level_key_fails_closed():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = os.path.join(tmpdir, "rl_state")
        export_file = os.path.join(tmpdir, "export.json")
        run_gate_a_synthetic(state_dir)
        payload = export_nexus_epistemic_profile(
            state_dir=state_dir,
            run_id="run_s1",
            task_id="t1",
            attempt_id="a1",
            profile_id="p1",
            output_path=export_file,
        )

        payload["bogus_key"] = "bogus"
        payload = _rehash_export(payload)
        with open(export_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        res = verify_epistemic_profile_export(export_file)
        assert res.status == EpistemicIntegrityStatus.RETURN
        assert "EP_EXPORT_KEYS_MISMATCH" in res.blockers


def test_negative_17_invalid_completion_status_fails_closed():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = os.path.join(tmpdir, "rl_state")
        export_file = os.path.join(tmpdir, "export.json")
        run_gate_a_synthetic(state_dir)
        payload = export_nexus_epistemic_profile(
            state_dir=state_dir,
            run_id="run_s1",
            task_id="t1",
            attempt_id="a1",
            profile_id="p1",
            output_path=export_file,
        )

        payload["completion_status"] = "BANANA"
        payload = _rehash_export(payload)
        with open(export_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        res = verify_epistemic_profile_export(export_file)
        assert res.status == EpistemicIntegrityStatus.RETURN
        assert "EP_INVALID_COMPLETION_STATUS" in res.blockers


def test_negative_22_export_output_inside_state_dir_rejected():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = os.path.join(tmpdir, "rl_state")
        run_gate_a_synthetic(state_dir)
        inside_file = os.path.join(state_dir, "bad.json")

        with pytest.raises(ValueError, match="EXPORT_OUTPUT_INSIDE_STATE"):
            export_nexus_epistemic_profile(
                state_dir=state_dir,
                run_id="run_s1",
                task_id="t1",
                attempt_id="a1",
                profile_id="p1",
                output_path=inside_file,
            )


def test_negative_23_state_dir_manifest_unmodified_by_export():
    from research_ledger.gate_a_harness import _dir_hash_manifest
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = os.path.join(tmpdir, "rl_state")
        export_file = os.path.join(tmpdir, "export.json")
        run_gate_a_synthetic(state_dir)

        m_before = _dir_hash_manifest(state_dir)

        export_nexus_epistemic_profile(
            state_dir=state_dir,
            run_id="run_s1",
            task_id="t1",
            attempt_id="a1",
            profile_id="p1",
            output_path=export_file,
        )

        m_after = _dir_hash_manifest(state_dir)
        assert m_before == m_after


def test_negative_25_receipt_contains_no_forbidden_fields():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = os.path.join(tmpdir, "rl_state")
        export_file = os.path.join(tmpdir, "export.json")
        receipt_file = os.path.join(tmpdir, "receipt.json")
        run_gate_a_synthetic(state_dir)

        export_nexus_epistemic_profile(
            state_dir=state_dir,
            run_id="run_s1",
            task_id="t1",
            attempt_id="a1",
            profile_id="p1",
            output_path=export_file,
        )

        res = verify_epistemic_profile_export(export_file)
        rcpt = write_epistemic_receipt(res, receipt_file)

        blob = json.dumps(rcpt)
        for key in FORBIDDEN_KEYS:
            assert f'"{key}"' not in blob


def test_negative_28_nexus_production_code_does_not_import_research_ledger():
    import ast
    from pathlib import Path
    pkg_dir = Path("nexus/research/epistemic_profile")
    for py_file in pkg_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("research_ledger"), f"File {py_file} imports {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    assert not node.module.startswith("research_ledger"), f"File {py_file} imports from {node.module}"
