from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

# Ensure scripts/ops can be imported if needed, or import function directly
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "ops"))
import p0t5_live_provider_canary  # noqa: I001
from p0t5_live_provider_canary import (
    _assert_canonical_admission,
    _assert_non_invoked_admission_terminal,
    _assert_replanable_provider_failure,
    _canonical_workforce_binding,
    get_provider_executable_identity,
    run_canary_campaign,
)
from nexus.services.unified_runtime import resolve_registered_online_cli_spec


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


def test_canary_open_code_failure_fallback_policy_is_bounded(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("NEXUS_P0T5_ALLOW_REAL_PROVIDER", "1")
    with pytest.raises(ValueError, match="provider_not_allowed"):
        run_canary_campaign(
            provider="gemini",
            project_root=str(tmp_path),
            receipt_dir=str(tmp_path / "receipts"),
            runner=_make_fixture_runner([]),
        )


def test_canary_admission_binding_hostiles_fail_closed():
    binding = _canonical_workforce_binding("opencode")
    decision = {
        "decision": "ALLOW",
        "resolved_worker_id": binding["worker_id"],
        "resolved_provider": binding["provider"],
        "resolved_model": binding["model"],
    }
    valid = {"workforce_admission": {"overall_decision": "ALLOW", "records": [{"decision": decision}]}}
    _assert_canonical_admission(valid, 1)

    hostile = [
        {},
        {"workforce_admission": None},
        {"workforce_admission": {"overall_decision": "ESCALATE", "records": [{"decision": decision}]}},
        {"workforce_admission": {"overall_decision": "ALLOW", "records": []}},
    ]
    for receipt in hostile:
        with pytest.raises(RuntimeError, match="workforce_admission_"):
            _assert_canonical_admission(receipt, 1)

    for field in ("resolved_worker_id", "resolved_provider", "resolved_model"):
        substituted = dict(decision)
        substituted[field] = "substituted"
        with pytest.raises(RuntimeError, match="workforce_admission_"):
            _assert_canonical_admission(
                {"workforce_admission": {"overall_decision": "ALLOW", "records": [{"decision": substituted}]}},
                1,
            )


def test_non_admitted_block_is_terminal_and_not_replanable():
    receipt = {
        "terminal_status": "BLOCKED",
        "workforce_admission": {"overall_decision": "BLOCK"},
        "capability_call_count": 0,
        "local_call_count": 0,
        "online_call_count": 0,
        "verifier_call_count": 0,
        "learning_call_count": 0,
        "provider_call_count": 0,
        "invocation_counts": {"capability": 0, "local": 0, "online": 0, "verifier": 0, "learning": 0},
        "stages": [
            {"name": "local", "status": "NOT_REQUESTED", "invoked": False},
            {"name": "online", "status": "NOT_REQUESTED", "invoked": False},
            {"name": "verifier", "status": "NOT_REQUESTED", "invoked": False},
            {"name": "learning", "status": "NOT_REQUESTED", "invoked": False},
        ],
    }

    _assert_non_invoked_admission_terminal(receipt, 1)


def test_non_admitted_escalate_is_incomplete_but_not_replanable():
    receipt = {
        "terminal_status": "INCOMPLETE",
        "workforce_admission": {"overall_decision": "ESCALATE"},
        "capability_call_count": 0,
        "local_call_count": 0,
        "online_call_count": 0,
        "verifier_call_count": 0,
        "learning_call_count": 0,
        "provider_call_count": 0,
        "invocation_counts": {"capability": 0, "local": 0, "online": 0, "verifier": 0, "learning": 0},
        "stages": [
            {"name": "local", "status": "NOT_REQUESTED", "invoked": False},
            {"name": "online", "status": "NOT_REQUESTED", "invoked": False},
            {"name": "verifier", "status": "NOT_REQUESTED", "invoked": False},
            {"name": "learning", "status": "NOT_REQUESTED", "invoked": False},
        ],
    }

    _assert_non_invoked_admission_terminal(receipt, 1)


def test_authority_failure_projection_allows_preparation_but_no_physical_calls():
    receipt = {
        "terminal_status": "BLOCKED",
        "workforce_admission": {"overall_decision": "BLOCK"},
        "capability_call_count": 1,
        "local_call_count": 0,
        "online_call_count": 0,
        "verifier_call_count": 0,
        "learning_call_count": 0,
        "provider_call_count": 0,
        "invocation_counts": {"capability": 1, "local": 0, "online": 0, "verifier": 0, "learning": 0},
        "stages": [
            {"name": "local", "status": "NOT_REQUESTED", "invoked": False},
            {
                "name": "online", "status": "FAILED", "invoked": False,
                "provider_call_count": 0, "model_call_count": 0,
                "response": {
                    "invoked": False,
                    "provider_call_count": 0,
                    "gateway_invocation_authority": {"status": "BLOCKED"},
                },
            },
            {"name": "verifier", "status": "NOT_REQUESTED", "invoked": False},
            {"name": "learning", "status": "NOT_REQUESTED", "invoked": False},
        ],
    }

    _assert_non_invoked_admission_terminal(receipt, 1)


def test_replan_requires_admitted_provider_delivery_and_trusted_failure():
    receipt = {
        "terminal_status": "INCOMPLETE",
        "workforce_admission": {"overall_decision": "ALLOW"},
        "online": {"invoked": True, "response": {"output_delivered": True}},
        "verifier": {
            "status": "FAILED",
            "invoked": True,
            "gate_passed": False,
            "evidence_present": True,
            "task_identity_shared": True,
            "evidence_refs": ["verifier:trusted-failure"],
        },
        "execution_replan_request": {
            "schema": "nexus.execution_replan_request.v1",
            "trigger": "verifier_failed",
            "replan_required": True,
            "verifier_outcome_trusted": True,
            "verifier_status": "FAILED",
            "verifier_evidence_refs": ["verifier:trusted-failure"],
        },
    }

    _assert_replanable_provider_failure(receipt, 1)


@pytest.mark.parametrize(
    ("change", "match"),
    [
        (lambda r: r.pop("provider_call_count"), "call_count"),
        (lambda r: r.__setitem__("provider_call_count", 1), "call_count"),
        (lambda r: r.__setitem__("execution_replan_request", {}), "replan_authority"),
        (lambda r: r["stages"].__setitem__(1, {"name": "online", "status": "FAILED", "invoked": False}), "stage_requested"),
    ],
)
def test_non_admitted_receipt_hostile_fields_fail_closed(change, match):
    receipt = {
        "terminal_status": "BLOCKED",
        "workforce_admission": {"overall_decision": "BLOCK"},
        "capability_call_count": 0,
        "local_call_count": 0,
        "online_call_count": 0,
        "verifier_call_count": 0,
        "learning_call_count": 0,
        "provider_call_count": 0,
        "invocation_counts": {"capability": 0, "local": 0, "online": 0, "verifier": 0, "learning": 0},
        "stages": [
            {"name": name, "status": "NOT_REQUESTED", "invoked": False}
            for name in ("local", "online", "verifier", "learning")
        ],
    }
    change(receipt)
    with pytest.raises(RuntimeError, match=match):
        _assert_non_invoked_admission_terminal(receipt, 1)


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r["verifier"].__setitem__("status", "SUCCEEDED"),
        lambda r: r["verifier"].__setitem__("evidence_present", False),
        lambda r: r["verifier"].pop("evidence_refs"),
        lambda r: r["online"]["response"].__setitem__("output_delivered", False),
        lambda r: r["workforce_admission"].__setitem__("overall_decision", "ESCALATE"),
        lambda r: r.pop("execution_replan_request"),
        lambda r: r["execution_replan_request"].__setitem__("verifier_outcome_trusted", False),
    ],
)
def test_replanable_receipt_hostile_fields_fail_closed(change):
    receipt = {
        "terminal_status": "INCOMPLETE",
        "workforce_admission": {"overall_decision": "ALLOW"},
        "online": {"invoked": True, "response": {"output_delivered": True}},
        "verifier": {
            "status": "FAILED", "invoked": True, "gate_passed": False,
            "evidence_present": True, "task_identity_shared": True,
            "evidence_refs": ["verifier:trusted-failure"],
        },
        "execution_replan_request": {
            "schema": "nexus.execution_replan_request.v1", "trigger": "verifier_failed",
            "replan_required": True, "verifier_outcome_trusted": True,
            "verifier_status": "FAILED", "verifier_evidence_refs": ["verifier:trusted-failure"],
        },
    }
    change(receipt)
    with pytest.raises(RuntimeError):
        _assert_replanable_provider_failure(receipt, 1)


def test_canary_does_not_automatically_use_codex(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_P0T5_ALLOW_REAL_PROVIDER", "1")
    with pytest.raises(ValueError, match="provider_not_allowed"):
        run_canary_campaign(
            provider="codex",
            project_root=str(tmp_path),
            receipt_dir=str(tmp_path / "receipts"),
        )


def test_canary_supports_mainchain_entrypoint(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_P0T5_ALLOW_REAL_PROVIDER", "1")
    nonces = []
    summary = run_canary_campaign(
        provider="opencode",
        entrypoint="mainchain",
        project_root=str(tmp_path),
        receipt_dir=str(tmp_path / "receipts"),
        runner=_make_fixture_runner(nonces),
    )
    assert summary["entrypoint"] == "mainchain"
    assert summary["attempt_1_mainchain_entry"] is True
    assert summary["attempt_2_mainchain_entry"] is True
    assert summary["attempt_1_route_freeze"] is True
    assert summary["attempt_2_route_freeze"] is True


# Milestone B Tests — Exact Executable Binding & Route Identity Truth

def test_provider_identity_uses_exact_resolved_executable(tmp_path: Path):
    ident = get_provider_executable_identity("opencode", shutil.which("opencode") or "opencode")
    assert ident["version_source"] == "exact_invoked_executable"
    assert ident["version_command_exit_code"] in (0, -1)
    assert "executable_path_hash" in ident


def test_provider_version_uses_same_executable_as_inference(tmp_path: Path):
    spec = resolve_registered_online_cli_spec("opencode", working_directory=str(tmp_path))
    ident = get_provider_executable_identity("opencode", spec.command[0])
    assert ident["version_normalized"] != ""
    assert "executable_path_hash" in ident


def test_provider_identity_hash_matches_process_evidence(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_P0T5_ALLOW_REAL_PROVIDER", "1")
    nonces = []
    summary = run_canary_campaign(
        provider="opencode",
        entrypoint="mainchain",
        project_root=str(tmp_path),
        receipt_dir=str(tmp_path / "receipts"),
        runner=_make_fixture_runner(nonces),
    )
    ident_hash = summary["provider_executable_identity"]["executable_path_hash"]
    assert ident_hash.startswith("sha256:")


def test_provider_version_summary_matches_identity(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_P0T5_ALLOW_REAL_PROVIDER", "1")
    nonces = []
    summary = run_canary_campaign(
        provider="opencode",
        entrypoint="mainchain",
        project_root=str(tmp_path),
        receipt_dir=str(tmp_path / "receipts"),
        runner=_make_fixture_runner(nonces),
    )
    assert summary["provider_version"] == summary["provider_executable_identity"]["version_normalized"]


def test_provider_identity_error_does_not_expose_exception(tmp_path: Path):
    ident = get_provider_executable_identity("invalid_binary_foo_bar_xyz", "/nonexistent/path/binary")
    assert ident["version_normalized"] == "unknown"
    assert ident["version_error_code"] == "provider_version_query_failed"
    assert "/nonexistent/path" not in str(ident)


def test_mainchain_canary_summary_requires_complete_route_identity(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_P0T5_ALLOW_REAL_PROVIDER", "1")
    nonces = []
    summary = run_canary_campaign(
        provider="opencode",
        entrypoint="mainchain",
        project_root=str(tmp_path),
        receipt_dir=str(tmp_path / "receipts"),
        runner=_make_fixture_runner(nonces),
    )
    assert summary["attempt_1_mainchain_identity_complete"] is True
    assert summary["attempt_2_mainchain_identity_complete"] is True


# Milestone B — Executable Pinning & Resolution Closure Tests

def test_canary_resolves_provider_exactly_once(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_P0T5_ALLOW_REAL_PROVIDER", "1")
    resolve_count = {"count": 0}
    orig_resolver = p0t5_live_provider_canary.resolve_registered_online_cli_spec

    def counting_resolver(provider, working_directory=""):
        resolve_count["count"] += 1
        return orig_resolver(provider, working_directory=working_directory)

    monkeypatch.setattr(
        p0t5_live_provider_canary,
        "resolve_registered_online_cli_spec",
        counting_resolver,
    )

    nonces = []
    summary = run_canary_campaign(
        provider="opencode",
        entrypoint="mainchain",
        project_root=str(tmp_path),
        receipt_dir=str(tmp_path / "receipts"),
        runner=_make_fixture_runner(nonces),
    )
    assert resolve_count["count"] == 1
    assert summary["real_provider_call_count"] == 2


def test_canary_reuses_resolved_spec_for_both_attempts(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_P0T5_ALLOW_REAL_PROVIDER", "1")
    resolved_specs = []
    orig_invoker_builder = p0t5_live_provider_canary.build_subprocess_online_invoker

    def tracking_builder(spec, runner=None):
        resolved_specs.append(spec)
        return orig_invoker_builder(spec, runner=runner)

    monkeypatch.setattr(
        p0t5_live_provider_canary,
        "build_subprocess_online_invoker",
        tracking_builder,
    )

    nonces = []
    run_canary_campaign(
        provider="opencode",
        entrypoint="mainchain",
        project_root=str(tmp_path),
        receipt_dir=str(tmp_path / "receipts"),
        runner=_make_fixture_runner(nonces),
    )
    assert len(resolved_specs) == 2
    assert resolved_specs[0] is resolved_specs[1]


def test_canary_does_not_reresolve_after_path_change(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_P0T5_ALLOW_REAL_PROVIDER", "1")
    dir_a = tmp_path / "bin_a"
    dir_a.mkdir()
    bin_a = dir_a / "opencode"
    bin_a.write_text("#!/bin/sh\necho '1.17.20-A'", encoding="utf-8")
    bin_a.chmod(0o755)

    dir_b = tmp_path / "bin_b"
    dir_b.mkdir()
    bin_b = dir_b / "opencode"
    bin_b.write_text("#!/bin/sh\necho '9.9.9-B'", encoding="utf-8")
    bin_b.chmod(0o755)

    monkeypatch.setenv("PATH", f"{dir_a}:{os.environ.get('PATH', '')}")

    nonces = []
    summary = run_canary_campaign(
        provider="opencode",
        entrypoint="mainchain",
        project_root=str(tmp_path),
        receipt_dir=str(tmp_path / "receipts"),
        runner=_make_fixture_runner(nonces),
    )
    assert summary["provider_executable_identity"]["version_normalized"].startswith("1.17.20")


def test_canary_version_uses_resolved_spec_executable(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_P0T5_ALLOW_REAL_PROVIDER", "1")
    nonces = []
    summary = run_canary_campaign(
        provider="opencode",
        entrypoint="mainchain",
        project_root=str(tmp_path),
        receipt_dir=str(tmp_path / "receipts"),
        runner=_make_fixture_runner(nonces),
    )
    ident = summary["provider_executable_identity"]
    assert ident["version_source"] == "exact_invoked_executable"
    assert ident["executable_path_hash"].startswith("sha256:")


def test_canary_process_hash_matches_resolved_executable(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_P0T5_ALLOW_REAL_PROVIDER", "1")
    nonces = []
    summary = run_canary_campaign(
        provider="opencode",
        entrypoint="mainchain",
        project_root=str(tmp_path),
        receipt_dir=str(tmp_path / "receipts"),
        runner=_make_fixture_runner(nonces),
    )
    assert summary["provider_executable_identity"]["executable_path_hash"] != ""


def test_canary_fails_when_process_identity_differs(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_P0T5_ALLOW_REAL_PROVIDER", "1")
    orig_ident = p0t5_live_provider_canary.get_provider_executable_identity

    def bad_ident(provider, executable=None):
        res = orig_ident(provider, executable)
        res["executable_path_hash"] = "sha256:mismatch_fake_hash_123"
        return res

    monkeypatch.setattr(
        p0t5_live_provider_canary,
        "get_provider_executable_identity",
        bad_ident,
    )
    nonces = []
    with pytest.raises(RuntimeError, match="PROVIDER_EXECUTABLE_IDENTITY_MISMATCH"):
        run_canary_campaign(
            provider="opencode",
            entrypoint="mainchain",
            project_root=str(tmp_path),
            receipt_dir=str(tmp_path / "receipts"),
            runner=_make_fixture_runner(nonces),
        )


def test_canary_does_not_call_registered_lazy_resolver(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_P0T5_ALLOW_REAL_PROVIDER", "1")
    lazy_calls = {"count": 0}

    def lazy_invoker(*args, **kwargs):
        lazy_calls["count"] += 1
        raise RuntimeError("build_registered_online_invoker_should_not_be_called")

    monkeypatch.setattr(
        p0t5_live_provider_canary,
        "build_registered_online_invoker",
        lazy_invoker,
    )

    nonces = []
    summary = run_canary_campaign(
        provider="opencode",
        entrypoint="mainchain",
        project_root=str(tmp_path),
        receipt_dir=str(tmp_path / "receipts"),
        runner=_make_fixture_runner(nonces),
    )
    assert lazy_calls["count"] == 0
    assert summary["real_provider_call_count"] == 2
