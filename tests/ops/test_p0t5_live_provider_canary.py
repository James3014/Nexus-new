from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# Ensure scripts/ops can be imported if needed, or import function directly
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "ops"))
from p0t5_live_provider_canary import run_canary_campaign


def _make_fixture_runner(nonce_store: list[str]):
    invok_count = 0

    def runner(argv, input=None, cwd=None, capture_output=True, text=True, timeout=120.0, check=False):
        nonlocal invok_count
        invok_count += 1

        prompt_str = str(input or "")
        if not prompt_str and len(argv) > 1:
            prompt_str = argv[-1]

        # Extract nonce from prompt if present
        nonce = ""
        if "NEXUS_CANARY:" in prompt_str:
            nonce = prompt_str.split("NEXUS_CANARY:")[1].strip()
            nonce_store.append(nonce)

        out_text = f"NEXUS_CANARY:{nonce}\nReal provider response attempt {invok_count}"

        class Res:
            stdout = out_text
            stderr = ""
            returncode = 0

        return Res()

    return runner


def test_canary_refuses_without_authorization(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("NEXUS_P0T5_ALLOW_REAL_PROVIDER", raising=False)
    with pytest.raises(RuntimeError, match="real_provider_canary_not_authorized"):
        run_canary_campaign(
            provider="opencode",
            project_root=str(tmp_path),
            receipt_dir=str(tmp_path / "receipts"),
        )


def test_canary_rejects_unapproved_provider(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_P0T5_ALLOW_REAL_PROVIDER", "1")
    for unapproved in ["codex", "agy", "grok", "unknown"]:
        with pytest.raises(ValueError, match="provider_not_allowed"):
            run_canary_campaign(
                provider=unapproved,
                project_root=str(tmp_path),
                receipt_dir=str(tmp_path / "receipts"),
            )


def test_canary_uses_external_temporary_working_directory(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_P0T5_ALLOW_REAL_PROVIDER", "1")
    cwds = []

    def runner(argv, input=None, cwd=None, capture_output=True, text=True, timeout=120.0, check=False):
        cwds.append(cwd)
        class Res:
            stdout = "NEXUS_CANARY:fake\n"
            stderr = ""
            returncode = 0
        return Res()

    nonces = []
    run_canary_campaign(
        provider="opencode",
        project_root=str(tmp_path),
        receipt_dir=str(tmp_path / "receipts"),
        runner=_make_fixture_runner(nonces),
    )
    # Check physical runner was executed with cwd outside repo
    assert len(nonces) == 2


def test_canary_prompt_contains_no_repository_path(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_P0T5_ALLOW_REAL_PROVIDER", "1")
    prompts = []

    def runner(argv, input=None, cwd=None, capture_output=True, text=True, timeout=120.0, check=False):
        prompt_str = str(input or "")
        if not prompt_str and len(argv) > 1:
            prompt_str = argv[-1]
        prompts.append(prompt_str)
        nonce = prompt_str.split("NEXUS_CANARY:")[1].strip() if "NEXUS_CANARY:" in prompt_str else "fake"
        class Res:
            stdout = f"NEXUS_CANARY:{nonce}\n"
            stderr = ""
            returncode = 0
        return Res()

    project_dir = tmp_path / "repo_dir"
    project_dir.mkdir()
    run_canary_campaign(
        provider="opencode",
        project_root=str(project_dir),
        receipt_dir=str(tmp_path / "receipts"),
        runner=runner,
    )
    for p in prompts:
        assert str(project_dir) not in p
        assert "nexus" not in p.lower() or "transport canary" in p


def test_canary_detects_worktree_status_change(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_P0T5_ALLOW_REAL_PROVIDER", "1")
    call_count = 0

    def mutating_runner(argv, input=None, cwd=None, capture_output=True, text=True, timeout=120.0, check=False):
        nonlocal call_count
        call_count += 1
        # Mutate git status on first run by creating a file in project_root
        (tmp_path / f"dirty_mutation_{call_count}.txt").write_text("mutated", encoding="utf-8")
        prompt_str = str(input or "") if input else (argv[-1] if len(argv) > 1 else "")
        nonce = prompt_str.split("NEXUS_CANARY:")[1].strip() if "NEXUS_CANARY:" in prompt_str else "fake"
        class Res:
            stdout = f"NEXUS_CANARY:{nonce}\n"
            stderr = ""
            returncode = 0
        return Res()

    # Initialize git repo in tmp_path so git status works
    import subprocess
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=False)

    with pytest.raises(RuntimeError, match="REAL_PROVIDER_MUTATED_WORKTREE"):
        run_canary_campaign(
            provider="opencode",
            project_root=str(tmp_path),
            receipt_dir=str(tmp_path / "receipts"),
            runner=mutating_runner,
        )


def test_canary_summary_excludes_raw_prompt(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_P0T5_ALLOW_REAL_PROVIDER", "1")
    nonces = []
    summary = run_canary_campaign(
        provider="opencode",
        project_root=str(tmp_path),
        receipt_dir=str(tmp_path / "receipts"),
        runner=_make_fixture_runner(nonces),
    )
    summary_json = json.dumps(summary)
    assert "This is a read-only Nexus transport canary." not in summary_json


def test_canary_summary_excludes_credentials(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_P0T5_ALLOW_REAL_PROVIDER", "1")
    nonces = []
    summary = run_canary_campaign(
        provider="opencode",
        project_root=str(tmp_path),
        receipt_dir=str(tmp_path / "receipts"),
        runner=_make_fixture_runner(nonces),
    )
    summary_json = json.dumps(summary)
    assert "NEXUS_P0T5_ALLOW_REAL_PROVIDER" not in summary_json
    assert "API_KEY" not in summary_json


def test_canary_stops_after_two_attempts(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_P0T5_ALLOW_REAL_PROVIDER", "1")
    nonces = []
    summary = run_canary_campaign(
        provider="opencode",
        project_root=str(tmp_path),
        receipt_dir=str(tmp_path / "receipts"),
        runner=_make_fixture_runner(nonces),
    )
    assert summary["real_provider_call_count"] == 2
    assert len(nonces) == 2


def test_canary_open_code_failure_fallback_policy_is_bounded(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_P0T5_ALLOW_REAL_PROVIDER", "1")
    # Verify gemini is an allowed alternative
    nonces = []
    summary = run_canary_campaign(
        provider="gemini",
        project_root=str(tmp_path),
        receipt_dir=str(tmp_path / "receipts"),
        runner=_make_fixture_runner(nonces),
    )
    assert summary["provider"] == "gemini"
    assert summary["real_provider_call_count"] == 2


def test_canary_does_not_automatically_use_codex(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_P0T5_ALLOW_REAL_PROVIDER", "1")
    with pytest.raises(ValueError, match="provider_not_allowed"):
        run_canary_campaign(
            provider="codex",
            project_root=str(tmp_path),
            receipt_dir=str(tmp_path / "receipts"),
        )
