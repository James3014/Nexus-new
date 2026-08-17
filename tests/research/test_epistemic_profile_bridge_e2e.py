from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from nexus.research.epistemic_profile.contracts import EpistemicIntegrityStatus
from nexus.research.epistemic_profile.io import (
    verify_epistemic_profile_export,
    write_epistemic_receipt,
)

RESEARCH_LEDGER_ROOT_ENV = "NEXUS_RESEARCH_LEDGER_ROOT"
DEFAULT_RESEARCH_LEDGER_ROOT = Path("/Users/jameschen/Workspace/research-ledger")


def _research_ledger_src() -> Path:
    """Resolve the optional, read-only Research Ledger test checkout.

    The nested ``research-ledger`` directory used by the original demo is not
    part of the Nexus repository.  A durable sibling checkout is therefore
    the default for local integration tests, while CI and fresh clones skip
    when that optional checkout is absent.  An explicit override is strict:
    a missing or malformed checkout is a test failure, never a skip.
    """
    configured = os.environ.get(RESEARCH_LEDGER_ROOT_ENV)
    root = Path(configured).expanduser() if configured else DEFAULT_RESEARCH_LEDGER_ROOT
    if not root.exists():
        if configured:
            raise AssertionError(f"{RESEARCH_LEDGER_ROOT_ENV} points to a missing path: {root}")
        pytest.skip("Research Ledger checkout not present; optional bridge skipped")
    root = root.resolve()
    src = root / "src"
    cli = src / "research_ledger" / "cli.py"
    if not root.is_dir() or not src.is_dir() or not cli.is_file():
        raise AssertionError(f"Research Ledger checkout is invalid (expected {cli}): {root}")
    return src


def _rehash_export(payload: dict) -> dict:
    p_sans = {k: v for k, v in payload.items() if k != "export_sha256"}
    canonical = json.dumps(p_sans, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    payload["export_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload


def _run_rl_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    src = _research_ledger_src()
    inherited = os.environ.get("PYTHONPATH")
    pythonpath = str(src) if not inherited else os.pathsep.join((str(src), inherited))
    env = {**os.environ, "PYTHONPATH": pythonpath}
    cmd = [sys.executable, "-m", "research_ledger.cli"] + args
    return subprocess.run(cmd, env=env, capture_output=True, text=True)


def test_positive_end_to_end_bridge_pipeline_via_subprocess():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = os.path.join(tmpdir, "rl_state")
        export_file = os.path.join(tmpdir, "export.json")
        receipt_file = os.path.join(tmpdir, "receipt.json")

        # 1. Run Gate A synthetic via Research Ledger CLI
        res_syn = _run_rl_cli(["run-gate-a-synthetic", "--state-dir", state_dir])
        assert res_syn.returncode == 0, f"run-gate-a-synthetic failed: {res_syn.stderr}"

        # 2. Export Nexus Profile via Research Ledger CLI
        res_exp = _run_rl_cli(
            [
                "export-nexus-profile",
                "--state-dir",
                state_dir,
                "--run-id",
                "run_s1",
                "--task-id",
                "task_e2e_001",
                "--attempt-id",
                "att_e2e_001",
                "--profile-id",
                "prof_e2e_001",
                "--output",
                export_file,
            ]
        )
        assert res_exp.returncode == 0, f"export-nexus-profile failed: {res_exp.stderr}"
        assert os.path.exists(export_file)

        with open(export_file, "r", encoding="utf-8") as f:
            export_payload = json.load(f)

        # 3. Nexus Verification via strict loader
        ver_res = verify_epistemic_profile_export(export_file)
        assert ver_res.status == EpistemicIntegrityStatus.PASS
        assert ver_res.records_checked > 0
        assert ver_res.source_export_id == export_payload["export_id"]
        assert ver_res.source_export_sha256 == export_payload["export_sha256"]

        # 4. Write Receipt via Nexus
        rcpt = write_epistemic_receipt(ver_res, receipt_file, source_export_path=export_file)
        assert os.path.exists(receipt_file)
        assert rcpt["source_export_sha256"] == export_payload["export_sha256"]
        assert rcpt["runtime_update_allowed"] is False
        assert rcpt["public_claim_allowed"] is False
        assert rcpt["public_benchmark_allowed"] is False
        assert rcpt["production_ready"] is False
        assert rcpt["integration_approved"] is False


def test_negative_missing_run_rejected_by_exporter():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = os.path.join(tmpdir, "rl_state")
        export_file = os.path.join(tmpdir, "export.json")
        _run_rl_cli(["run-gate-a-synthetic", "--state-dir", state_dir])

        res_exp = _run_rl_cli(
            [
                "export-nexus-profile",
                "--state-dir",
                state_dir,
                "--run-id",
                "nonexistent_run",
                "--task-id",
                "t1",
                "--attempt-id",
                "a1",
                "--profile-id",
                "p1",
                "--output",
                export_file,
            ]
        )
        assert res_exp.returncode != 0
        assert any(
            code in res_exp.stderr
            for code in (
                "EXPORT_RUN_NOT_FOUND",
                "EXPORT_BLIND_TASK_RUN_MISMATCH",
                "EXPORT_VERIFICATION_FAILED",
            )
        )
        assert not os.path.exists(export_file)


def test_negative_modified_export_hash_fails_closed():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = os.path.join(tmpdir, "rl_state")
        export_file = os.path.join(tmpdir, "export.json")
        _run_rl_cli(["run-gate-a-synthetic", "--state-dir", state_dir])
        _run_rl_cli(
            [
                "export-nexus-profile",
                "--state-dir",
                state_dir,
                "--run-id",
                "run_s1",
                "--task-id",
                "t1",
                "--attempt-id",
                "a1",
                "--profile-id",
                "p1",
                "--output",
                export_file,
            ]
        )

        with open(export_file, "r", encoding="utf-8") as f:
            payload = json.load(f)

        payload["export_sha256"] = "0" * 64
        with open(export_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        res = verify_epistemic_profile_export(export_file)
        assert res.status == EpistemicIntegrityStatus.RETURN
        assert "EP_EXPORT_HASH_MISMATCH" in res.blockers


def test_negative_source_text_forgery_rehashed_fails_closed():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = os.path.join(tmpdir, "rl_state")
        export_file = os.path.join(tmpdir, "export.json")
        _run_rl_cli(["run-gate-a-synthetic", "--state-dir", state_dir])
        _run_rl_cli(
            [
                "export-nexus-profile",
                "--state-dir",
                state_dir,
                "--run-id",
                "run_s1",
                "--task-id",
                "t1",
                "--attempt-id",
                "a1",
                "--profile-id",
                "p1",
                "--output",
                export_file,
            ]
        )

        with open(export_file, "r", encoding="utf-8") as f:
            payload = json.load(f)

        payload["records"][0]["source_text"] = "forged raw text"
        payload = _rehash_export(payload)
        with open(export_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        res = verify_epistemic_profile_export(export_file)
        assert res.status == EpistemicIntegrityStatus.RETURN
        assert "EP_FORBIDDEN_KEY_DETECTED" in res.blockers


def test_negative_invalid_direction_fails_closed():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = os.path.join(tmpdir, "rl_state")
        export_file = os.path.join(tmpdir, "export.json")
        _run_rl_cli(["run-gate-a-synthetic", "--state-dir", state_dir])
        _run_rl_cli(
            [
                "export-nexus-profile",
                "--state-dir",
                state_dir,
                "--run-id",
                "run_s1",
                "--task-id",
                "t1",
                "--attempt-id",
                "a1",
                "--profile-id",
                "p1",
                "--output",
                export_file,
            ]
        )

        with open(export_file, "r", encoding="utf-8") as f:
            payload = json.load(f)

        payload["records"][0]["direction"] = "super_supports"
        payload = _rehash_export(payload)
        with open(export_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        res = verify_epistemic_profile_export(export_file)
        assert res.status == EpistemicIntegrityStatus.RETURN
        assert "EP_INVALID_DIRECTION" in res.blockers


def test_negative_string_boolean_fails_closed():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = os.path.join(tmpdir, "rl_state")
        export_file = os.path.join(tmpdir, "export.json")
        _run_rl_cli(["run-gate-a-synthetic", "--state-dir", state_dir])
        _run_rl_cli(
            [
                "export-nexus-profile",
                "--state-dir",
                state_dir,
                "--run-id",
                "run_s1",
                "--task-id",
                "t1",
                "--attempt-id",
                "a1",
                "--profile-id",
                "p1",
                "--output",
                export_file,
            ]
        )

        with open(export_file, "r", encoding="utf-8") as f:
            payload = json.load(f)

        payload["records"][0]["cannot_establish_present"] = "false"
        payload = _rehash_export(payload)
        with open(export_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        res = verify_epistemic_profile_export(export_file)
        assert res.status == EpistemicIntegrityStatus.RETURN
        assert "EP_RECORD_KEYS_MISMATCH" in res.blockers


def test_negative_corrupted_gate_status_fails_closed():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = os.path.join(tmpdir, "rl_state")
        export_file = os.path.join(tmpdir, "export.json")
        _run_rl_cli(["run-gate-a-synthetic", "--state-dir", state_dir])
        _run_rl_cli(
            [
                "export-nexus-profile",
                "--state-dir",
                state_dir,
                "--run-id",
                "run_s1",
                "--task-id",
                "t1",
                "--attempt-id",
                "a1",
                "--profile-id",
                "p1",
                "--output",
                export_file,
            ]
        )

        with open(export_file, "r", encoding="utf-8") as f:
            payload = json.load(f)

        payload["verification"]["gate_a_status"] = "GATE_A_CORRUPTED"
        payload = _rehash_export(payload)
        with open(export_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        res = verify_epistemic_profile_export(export_file)
        assert res.status == EpistemicIntegrityStatus.RETURN
        assert "EP_GATE_A_NOT_VERIFIED" in res.blockers


def test_negative_unexpected_nested_key_fails_closed():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = os.path.join(tmpdir, "rl_state")
        export_file = os.path.join(tmpdir, "export.json")
        _run_rl_cli(["run-gate-a-synthetic", "--state-dir", state_dir])
        _run_rl_cli(
            [
                "export-nexus-profile",
                "--state-dir",
                state_dir,
                "--run-id",
                "run_s1",
                "--task-id",
                "t1",
                "--attempt-id",
                "a1",
                "--profile-id",
                "p1",
                "--output",
                export_file,
            ]
        )

        with open(export_file, "r", encoding="utf-8") as f:
            payload = json.load(f)

        payload["verification"]["unexpected_field"] = "malicious"
        payload = _rehash_export(payload)
        with open(export_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        res = verify_epistemic_profile_export(export_file)
        assert res.status == EpistemicIntegrityStatus.RETURN
        assert "EP_VERIFICATION_KEYS_MISMATCH" in res.blockers


def test_negative_nexus_production_code_does_not_import_research_ledger():
    pkg_dir = Path("nexus/research/epistemic_profile")
    for py_file in pkg_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("research_ledger"), (
                        f"File {py_file} imports {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    assert not node.module.startswith("research_ledger"), (
                        f"File {py_file} imports from {node.module}"
                    )
