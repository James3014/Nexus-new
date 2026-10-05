import base64
import gzip
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from nexus.research.hybrid_replication_live import (
    CANONICAL_AGY_EXECUTION_GENERATION,
    EXACT_AGY_MODEL,
    FROZEN_RECEIPT_SHA256S,
    _c_prompt,
    _load_binding,
    _run_agy_b_fallback,
    _run_agy_candidate,
    _valid_probability_distribution,
    build_agy_identity_preflight_receipt,
    build_d2_candidate_packet,
    build_identity_preflight_receipt,
    classify_frozen_task_family,
    evaluate_agy_receipt,
    poll_agy_operation,
    resolve_canonical_agy_dispatch_path,
    resolve_ground_truth_payload,
    run_frozen_stack,
    seal_shadow_candidate,
)


def test_frozen_task_family_is_conservative() -> None:
    a = classify_frozen_task_family(
        title="Dependency discovery",
        body=(
            "At commit abc, perform dependency discovery for `nexus/core/example.py`. "
            "Return its direct imported modules, repository files that directly import "
            "this module, and its public top-level functions/classes."
        ),
    )
    assert a == "A"

    b = classify_frozen_task_family(
        title="Repository localization",
        body="Identify and rank the supplied candidate files most likely to require modification.",
    )
    assert b == "B"

    c = classify_frozen_task_family(
        title="Fix retry semantics",
        body="Implement the bounded retry fix and add regression tests.",
    )
    assert c == "C"


def test_d2_packet_preserves_literal_paths_before_frozen_ranked_candidates() -> None:
    packet = build_d2_candidate_packet(
        task_key="James3014/Nexus-new#1400",
        source_revision="a" * 40,
        task_contract="Touch `tests/test_example.py` and determine the primary source.",
        literal_paths=("tests/test_example.py",),
        ranked_paths=(
            "nexus/example.py",
            "tests/test_example.py",
            "nexus/other.py",
        ),
        evidence={
            "nexus/example.py": ("exact_identifier:Example",),
            "tests/test_example.py": ("literal_path_in_issue_body",),
            "nexus/other.py": ("cochange:example.py@12345678",),
        },
    )

    assert [item["path"] for item in packet["candidate_catalog"]] == [
        "tests/test_example.py",
        "nexus/example.py",
        "nexus/other.py",
    ]
    assert packet["candidate_catalog"][0]["source"] == "LITERAL_TASK_PATH"
    assert packet["candidate_catalog"][1]["source"] == "D0_V2_FROZEN"


def test_ground_truth_payload_is_unavailable_until_issue_is_terminal() -> None:
    assert (
        resolve_ground_truth_payload(
            issue={"state": "open", "number": 1400},
            merged_prs=(),
        )
        is None
    )

    payload = resolve_ground_truth_payload(
        issue={
            "state": "closed",
            "number": 1400,
            "closed_at": "2026-10-01T03:00:00Z",
        },
        merged_prs=(
            {
                "number": 1401,
                "merge_commit_sha": "b" * 40,
                "head_sha": "c" * 40,
                "merged_at": "2026-10-01T02:59:00Z",
                "changed_files": ("nexus/example.py", "tests/test_example.py"),
                "checks": (("test", "success"),),
            },
        ),
    )

    assert payload is not None
    assert payload["terminal_state"] == "CLOSED_WITH_MERGED_PR"
    assert "pr:1401@" + "b" * 40 in payload["evidence_refs"]
    assert payload["details"]["changed_files"] == [
        "nexus/example.py",
        "tests/test_example.py",
    ]


def test_identity_preflight_receipt_separates_generation_drift_from_provider_drift() -> None:
    receipt = build_identity_preflight_receipt(
        d0_sha256="cca215a2de82996c072f958159541a93d58b1482af3430d93f537c58ddafa2f9",
        d0_freeze_sha256="f04fdeea8ddb8cbaa2216aa783a7fe510da7c2f8625f50763a0d59d5e2234eee",
        frozen_receipt_sha256s=FROZEN_RECEIPT_SHA256S,
        declared_frozen_receipt_sha256s=FROZEN_RECEIPT_SHA256S,
        codex_cli="codex-cli 0.159.3",
        previous_codex_cli="codex-cli 0.158.0",
        codex_executable_sha256="61b0194f3bb6534439c8d26a3ed57d0805f84b884588b761795323eeb92fcf70",
        expected_codex_executable_sha256="61b0194f3bb6534439c8d26a3ed57d0805f84b884588b761795323eeb92fcf70",
        jev_requested_model="jev-latest",
        jev_resolved_model="jev-1.13.0",
        expected_jev_resolved_model="jev-1.13.0",
        jev_status="VALID",
        jev_usage={"input_tokens": 10, "output_tokens": 2},
        jev_latency_ms=12.5,
        created_at_utc="2026-10-01T03:00:00Z",
    )

    assert receipt["status"] == "PASS_NEW_EXECUTION_GENERATION"
    assert receipt["execution_generation_change"] is True
    assert receipt["provider_identity_drift"] is False
    assert receipt["activation_allowed"] is True


def test_jev_probability_distribution_matches_frozen_dm1_validation() -> None:
    assert _valid_probability_distribution({"C1": 0.8, "C2": 0.1, "ESCALATE": 0.1})
    assert not _valid_probability_distribution({"C1": 0.9, "C2": 0.2})
    assert not _valid_probability_distribution({"C1": 1.1, "C2": -0.1})
    assert not _valid_probability_distribution({"C1": "not-a-number"})


def test_ground_truth_excludes_pr_merged_after_issue_terminal_time() -> None:
    payload = resolve_ground_truth_payload(
        issue={
            "state": "closed",
            "number": 1400,
            "closed_at": "2026-10-01T03:00:00Z",
        },
        merged_prs=(
            {
                "number": 1401,
                "merge_commit_sha": "b" * 40,
                "head_sha": "c" * 40,
                "merged_at": "2026-10-01T03:00:01Z",
                "changed_files": ("nexus/late.py",),
                "checks": (("late", "success"),),
            },
        ),
    )
    assert payload is not None
    assert payload["terminal_state"] == "CLOSED_WITHOUT_MERGED_PR"
    assert payload["details"]["merged_prs"] == []
    assert payload["details"]["changed_files"] == []


def test_identity_preflight_blocks_frozen_receipt_or_executable_drift() -> None:
    drifted = dict(FROZEN_RECEIPT_SHA256S)
    drifted["d2"] = "0" * 64
    receipt = build_identity_preflight_receipt(
        d0_sha256="cca215a2de82996c072f958159541a93d58b1482af3430d93f537c58ddafa2f9",
        d0_freeze_sha256="f04fdeea8ddb8cbaa2216aa783a7fe510da7c2f8625f50763a0d59d5e2234eee",
        frozen_receipt_sha256s=drifted,
        declared_frozen_receipt_sha256s=FROZEN_RECEIPT_SHA256S,
        codex_cli="codex-cli 0.159.3",
        previous_codex_cli="codex-cli 0.158.0",
        codex_executable_sha256="0" * 64,
        expected_codex_executable_sha256="61b0194f3bb6534439c8d26a3ed57d0805f84b884588b761795323eeb92fcf70",
        jev_requested_model="jev-latest",
        jev_resolved_model="jev-1.13.0",
        expected_jev_resolved_model="jev-1.13.0",
        jev_status="VALID",
        jev_usage={},
        jev_latency_ms=1.0,
        created_at_utc="2026-10-01T03:00:00Z",
    )
    assert receipt["activation_allowed"] is False
    assert receipt["status"] == "BLOCKED_IDENTITY_OR_PROVIDER_DRIFT"


def test_c_prompt_requires_shadow_candidate_execution() -> None:
    from nexus.research.hybrid_replication_pipeline import TaskSnapshot

    snapshot = TaskSnapshot.create(
        repository="James3014/Nexus-new",
        issue_number=0,
        created_at="2026-10-01T00:00:00Z",
        captured_at="2026-10-01T00:00:00Z",
        issue_updated_at="2026-10-01T00:00:00Z",
        title="Synthetic C canary",
        body="Implement a bounded candidate change in an isolated canary checkout.",
        pre_implementation_revision="a" * 40,
        default_branch="main",
        source_event_id="activation-canary:c",
    )
    prompt, schema = _c_prompt(snapshot)
    assert "Implement" in prompt
    assert "isolated" in prompt
    assert schema["properties"]["status"]["enum"] == ["CANDIDATE", "NO_CHANGE", "BLOCKED"]


def test_c_prompt_forbids_prohibited_actions_and_future_outcomes() -> None:
    from nexus.research.hybrid_replication_pipeline import TaskSnapshot

    snapshot = TaskSnapshot.create(
        repository="James3014/Nexus-new",
        issue_number=1,
        created_at="2026-10-01T00:00:00Z",
        captured_at="2026-10-01T00:00:00Z",
        issue_updated_at="2026-10-01T00:00:00Z",
        title="Prohibition check",
        body="Verify prohibited commands and future outcome leak guards.",
        pre_implementation_revision="b" * 40,
        default_branch="main",
        source_event_id="canary:prohibitions",
    )
    prompt, _ = _c_prompt(snapshot)
    for forbidden_word in (
        "commit",
        "push",
        "fetch",
        "pull",
        "clone",
        "network",
        "install",
        "future",
    ):
        assert forbidden_word in prompt.lower()


def _canonical_dispatch_stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    dispatch_file = tmp_path / "nexus-agy-dispatch"
    dispatch_file.write_text("#!/bin/sh\n", encoding="utf-8")
    digest = hashlib.sha256(dispatch_file.read_bytes()).hexdigest()
    monkeypatch.setattr(
        "nexus.research.hybrid_replication_live.CANONICAL_AGY_DISPATCH_SHA256",
        digest,
    )
    return dispatch_file


def _init_test_git_repo(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=path, check=True)
    (path / "file1.txt").write_text("initial content\n", encoding="utf-8")
    subprocess.run(["git", "add", "file1.txt"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=path, check=True)
    rev = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=path, check=True, capture_output=True, text=True
    ).stdout.strip()
    return rev


def test_exact_attestation_produces_valid_agy_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stdout_file = tmp_path / "stdout.log"
    stdout_file.write_text("operation output\n", encoding="utf-8")
    stderr_file = tmp_path / "stderr.log"
    stderr_file.write_text("", encoding="utf-8")
    dispatch_file = _canonical_dispatch_stub(tmp_path, monkeypatch)

    record = {
        "schema": "nexus.agy_operation.v1",
        "operation_id": "agyop_11112222333344445555666677778888",
        "status": "COMPLETED",
        "provider": "agy",
        "observed_provider": "agy",
        "observed_model": EXACT_AGY_MODEL,
        "account_alias_hash": "alias_hash_abc",
        "rotations": 0,
        "failure_kind": None,
        "provider_session_id": "conv_exact_123",
        "runtime_revision": "rev_exact_999",
        "exit_code": 0,
    }

    receipt = evaluate_agy_receipt(
        record,
        dispatch_path=dispatch_file,
        stdout_path=stdout_file,
        stderr_path=stderr_file,
    )

    assert receipt["status"] == "VALID"
    assert receipt["valid"] is True
    assert receipt["operation_id"] == "agyop_11112222333344445555666677778888"
    assert receipt["account_alias_hash"] == "alias_hash_abc"
    assert receipt["rotations"] == 0
    assert receipt["failure_kind"] is None
    assert receipt["provider_session_id"] == "conv_exact_123"
    assert receipt["runtime_revision"] == "rev_exact_999"
    assert receipt["stdout_sha256"] == hashlib.sha256(b"operation output\n").hexdigest()
    assert receipt["stderr_sha256"] == hashlib.sha256(b"").hexdigest()
    assert receipt["transport_identity"] == "nexus-agy-dispatch"
    assert receipt["observed_provider"] == "agy"
    assert receipt["observed_model"] == EXACT_AGY_MODEL
    assert receipt["requested_model"] == EXACT_AGY_MODEL


def test_quota_rotation_success_remains_valid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stdout_file = tmp_path / "stdout.log"
    stdout_file.write_text("completed after quota rotation\n", encoding="utf-8")
    stderr_file = tmp_path / "stderr.log"
    stderr_file.write_text("", encoding="utf-8")
    dispatch_file = _canonical_dispatch_stub(tmp_path, monkeypatch)

    record = {
        "schema": "nexus.agy_operation.v1",
        "operation_id": "agyop_quota_rot_1234",
        "status": "COMPLETED",
        "provider": "agy",
        "observed_provider": "agy",
        "observed_model": EXACT_AGY_MODEL,
        "account_alias_hash": "final_alias_hash",
        "rotations": 2,
        "failure_kind": "QUOTA_EXHAUSTED",
        "provider_session_id": "conv_rotated",
        "runtime_revision": "rev_rot",
        "exit_code": 0,
    }

    receipt = evaluate_agy_receipt(
        record,
        dispatch_path=dispatch_file,
        stdout_path=stdout_file,
        stderr_path=stderr_file,
    )

    assert receipt["status"] == "VALID"
    assert receipt["valid"] is True
    assert receipt["failure_kind"] == "QUOTA_EXHAUSTED"
    assert receipt["rotations"] == 2
    assert receipt["account_alias_hash"] == "final_alias_hash"
    assert receipt["observed_model"] == EXACT_AGY_MODEL


def test_silent_model_substitution_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dispatch_file = _canonical_dispatch_stub(tmp_path, monkeypatch)

    record = {
        "operation_id": "agyop_sub_model",
        "status": "COMPLETED",
        "provider": "agy",
        "observed_provider": "agy",
        "observed_model": "gemini-1.5-pro",
        "exit_code": 0,
    }

    receipt = evaluate_agy_receipt(record, dispatch_path=dispatch_file)
    assert receipt["status"] == "MODEL_SUBSTITUTION_REJECTED"
    assert receipt["valid"] is False


def test_silent_provider_substitution_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dispatch_file = _canonical_dispatch_stub(tmp_path, monkeypatch)

    record = {
        "operation_id": "agyop_sub_provider",
        "status": "COMPLETED",
        "provider": "agy",
        "observed_provider": "openai",
        "observed_model": EXACT_AGY_MODEL,
        "exit_code": 0,
    }

    receipt = evaluate_agy_receipt(record, dispatch_path=dispatch_file)
    assert receipt["status"] == "PROVIDER_SUBSTITUTION_REJECTED"
    assert receipt["valid"] is False


def test_unexpected_transport_identity_rejected(tmp_path: Path) -> None:
    dispatch_file = tmp_path / "nexus-agy-dispatch"
    dispatch_file.write_text("#!/bin/sh\n", encoding="utf-8")

    record = {
        "operation_id": "agyop_bad_transport",
        "status": "COMPLETED",
        "provider": "not-agy",
        "observed_provider": "agy",
        "observed_model": EXACT_AGY_MODEL,
        "exit_code": 0,
    }

    receipt = evaluate_agy_receipt(record, dispatch_path=dispatch_file)
    assert receipt["status"] == "UNEXPECTED_TRANSPORT_IDENTITY"
    assert receipt["valid"] is False


def test_raw_agy_invocation_is_strictly_forbidden(tmp_path: Path) -> None:
    raw_agy = tmp_path / "agy"
    raw_agy.write_text("#!/bin/sh\n", encoding="utf-8")

    receipt = evaluate_agy_receipt({"status": "COMPLETED"}, dispatch_path=raw_agy)
    assert receipt["status"] == "UNEXPECTED_TRANSPORT_IDENTITY"
    assert receipt["valid"] is False

    with pytest.raises(RuntimeError, match="raw_agy_forbidden"):
        resolve_canonical_agy_dispatch_path({"agy_dispatch_path": str(raw_agy)})


def test_outcome_unknown_and_timeout_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dispatch_file = _canonical_dispatch_stub(tmp_path, monkeypatch)

    # OUTCOME_UNKNOWN
    record = {
        "operation_id": "agyop_unknown",
        "status": "OUTCOME_UNKNOWN",
        "provider": "agy",
        "observed_provider": "agy",
        "observed_model": EXACT_AGY_MODEL,
    }
    receipt = evaluate_agy_receipt(record, dispatch_path=dispatch_file)
    assert receipt["status"] == "OUTCOME_UNKNOWN"
    assert receipt["valid"] is False

    # Timeout
    receipt = evaluate_agy_receipt(None, dispatch_path=dispatch_file, timed_out=True)
    assert receipt["status"] == "TIMEOUT"
    assert receipt["valid"] is False

    # Missing / corrupt journal
    receipt = evaluate_agy_receipt(
        None, dispatch_path=dispatch_file, error_reason="MISSING_OR_CORRUPT_JOURNAL"
    )
    assert receipt["status"] == "MISSING_OR_CORRUPT_JOURNAL"
    assert receipt["valid"] is False

    # Pre-journal launch failures must stay distinguishable from journal corruption.
    receipt = evaluate_agy_receipt(
        None,
        dispatch_path=dispatch_file,
        error_reason="SPAWN_FAILED:WORKTREE_NO_FALLBACK_REQUESTED",
    )
    assert receipt["status"] == "SPAWN_FAILED"
    assert receipt["valid"] is False


def test_poll_agy_operation_handles_terminal_timeout_and_corrupt(tmp_path: Path) -> None:
    op_json = tmp_path / "operation.json"

    # Terminal state found
    op_json.write_text(json.dumps({"status": "COMPLETED"}), encoding="utf-8")
    record, timed_out, err = poll_agy_operation(op_json, timeout=0.1)
    assert record == {"status": "COMPLETED"}
    assert timed_out is False
    assert err is None

    # Still non-terminal -> timeout
    op_json.write_text(json.dumps({"status": "RUNNING"}), encoding="utf-8")
    record, timed_out, err = poll_agy_operation(op_json, timeout=0.05, poll_interval=0.01)
    assert timed_out is True
    assert err == "TIMEOUT"

    # Corrupt JSON -> missing/corrupt
    op_json.write_text("{corrupt json", encoding="utf-8")
    record, _, err = poll_agy_operation(op_json, timeout=0.05, poll_interval=0.01)
    assert record is None
    assert err == "MISSING_OR_CORRUPT_JOURNAL"


def test_c_diff_sealing_captures_physical_binary_diff(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    _init_test_git_repo(repo_dir)

    # Modify tracked file
    (repo_dir / "file1.txt").write_text("modified content\n", encoding="utf-8")
    # Add untracked file
    (repo_dir / "untracked.py").write_text("print('hello')\n", encoding="utf-8")

    sealing = seal_shadow_candidate(repo_dir)

    assert sealing["scope_valid"] is True
    assert sealing["changed_files"] == ["file1.txt", "untracked.py"]
    assert sealing["out_of_scope_paths"] == []
    assert sealing["oversized_untracked_files"] == []

    # Check physical diff
    diff_expected = subprocess.run(
        ["git", "diff", "--binary", "HEAD"],
        cwd=repo_dir,
        capture_output=True,
        check=True,
    ).stdout
    assert sealing["diff_sha256"] == hashlib.sha256(diff_expected).hexdigest()
    decompressed = gzip.decompress(base64.b64decode(sealing["diff_gzip_base64"].encode("ascii")))
    assert decompressed == diff_expected

    # Untracked files list
    assert len(sealing["untracked_files"]) == 1
    assert sealing["untracked_files"][0]["path"] == "untracked.py"
    assert (
        sealing["untracked_files"][0]["sha256"] == hashlib.sha256(b"print('hello')\n").hexdigest()
    )


def test_c_scope_rejection_for_out_of_scope_and_oversized_artifacts(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    _init_test_git_repo(repo_dir)

    # Out of scope path
    (repo_dir / "unauthorized.txt").write_text("evil\n", encoding="utf-8")
    sealing = seal_shadow_candidate(repo_dir, allowed_paths=["file1.txt"])
    assert sealing["scope_valid"] is False
    assert "unauthorized.txt" in sealing["out_of_scope_paths"]

    # Oversized artifact
    (repo_dir / "unauthorized.txt").unlink()
    (repo_dir / "large.bin").write_bytes(b"x" * 200)
    sealing_oversized = seal_shadow_candidate(repo_dir, max_file_size=100)
    assert sealing_oversized["scope_valid"] is False
    assert "large.bin" in sealing_oversized["oversized_untracked_files"]


def test_c_shadow_worktree_cleanup_always_performed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_dir = tmp_path / "repo"
    rev = _init_test_git_repo(repo_dir)

    def failing_dispatch(**kwargs: object) -> tuple:
        source = Path(str(kwargs["cwd"]))
        assert (source / ".git").is_dir()
        assert subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=source,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip() == rev
        raise RuntimeError("dispatcher crashed unexpectedly")

    monkeypatch.setattr(
        "nexus.research.hybrid_replication_live._run_agy_dispatch",
        failing_dispatch,
    )

    with pytest.raises(RuntimeError, match="dispatcher crashed"):
        _run_agy_candidate(
            repo=repo_dir,
            revision=rev,
            prompt="test prompt",
            binding={},
        )

    # Verify worktree was completely removed and pruned
    wt_out = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "nexus-hybrid-replication-c-" not in wt_out


def test_b_fallback_plan_mode_rejects_repository_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_dir = tmp_path / "repo"
    rev = _init_test_git_repo(repo_dir)
    dispatch_file = _canonical_dispatch_stub(tmp_path, monkeypatch)

    def mutating_dispatch(**kwargs: object) -> tuple:
        cwd = Path(str(kwargs["cwd"]))
        # Mutate repository in plan mode
        (cwd / "illegal_edit.txt").write_text("mutation in plan mode\n", encoding="utf-8")
        record = {
            "operation_id": "agyop_plan_mutation",
            "status": "COMPLETED",
            "provider": "agy",
            "observed_provider": "agy",
            "observed_model": EXACT_AGY_MODEL,
            "exit_code": 0,
        }
        return (
            record,
            1.0,
            cwd / "stdout.log",
            cwd / "stderr.log",
            False,
            None,
            dispatch_file,
        )

    monkeypatch.setattr(
        "nexus.research.hybrid_replication_live._run_agy_dispatch",
        mutating_dispatch,
    )

    receipt, _ = _run_agy_b_fallback(
        repo=repo_dir,
        revision=rev,
        prompt="plan prompt",
        binding={},
    )

    assert receipt["status"] == "REPOSITORY_MUTATION_REJECTED"
    assert receipt["valid"] is False
    assert receipt["repository_mutated"] is True

    # Check worktree was cleaned up
    wt_out = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "nexus-hybrid-replication-b-" not in wt_out


def test_run_frozen_stack_c_uses_agy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_dir = tmp_path / "repo"
    rev = _init_test_git_repo(repo_dir)

    from nexus.research.hybrid_replication_pipeline import TaskSnapshot

    snapshot = TaskSnapshot.create(
        repository="James3014/Nexus-new",
        issue_number=101,
        created_at="2026-10-01T00:00:00Z",
        captured_at="2026-10-01T00:00:00Z",
        issue_updated_at="2026-10-01T00:00:00Z",
        title="Implement bugfix",
        body="Implement bugfix in isolated checkout and add tests.",
        pre_implementation_revision=rev,
        default_branch="main",
        source_event_id="test:run_frozen_stack_c",
    )

    mock_receipt = {
        "schema": "nexus.hybrid_replication.agy_shadow_candidate.v1",
        "status": "VALID",
        "valid": True,
        "operation_id": "agyop_candidate_123",
        "observed_provider": "agy",
        "observed_model": EXACT_AGY_MODEL,
        "requested_model": EXACT_AGY_MODEL,
        "resolved_model": EXACT_AGY_MODEL,
        "transport_identity": "nexus-agy-dispatch",
        "usage": {"input_tokens": 150, "output_tokens": 50},
    }

    monkeypatch.setattr(
        "nexus.research.hybrid_replication_live._run_agy_candidate",
        lambda **kwargs: (mock_receipt, 2.5),
    )

    binding = {
        "repo_roots": {"James3014/Nexus-new": str(repo_dir)},
    }

    outcome = run_frozen_stack(snapshot, binding=binding)
    assert outcome.stratum == "C"
    assert outcome.raw_result.provider == "agy"
    assert outcome.raw_result.requested_model == EXACT_AGY_MODEL
    assert outcome.raw_result.resolved_model == EXACT_AGY_MODEL
    assert outcome.strong_online_raw_response == mock_receipt
    assert outcome.raw_result.failures == ()


def test_run_frozen_stack_b_fallback_uses_agy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_dir = tmp_path / "repo"
    rev = _init_test_git_repo(repo_dir)

    from nexus.research.hybrid_replication_pipeline import TaskSnapshot

    snapshot = TaskSnapshot.create(
        repository="James3014/Nexus-new",
        issue_number=102,
        created_at="2026-10-01T00:00:00Z",
        captured_at="2026-10-01T00:00:00Z",
        issue_updated_at="2026-10-01T00:00:00Z",
        title="Localize file",
        body="Identify and rank the supplied candidate files most likely to require modification.",
        pre_implementation_revision=rev,
        default_branch="main",
        source_event_id="test:run_frozen_stack_b",
    )

    # Mock D0 candidate ranking to return 2 candidates
    monkeypatch.setattr(
        "nexus.research.hybrid_replication_live._rank_candidates",
        lambda **kwargs: (("file1.txt", "file2.txt"), {}),
    )
    # Mock JEV to return low margin (rejected by DM1 policy)
    mock_jev = {
        "status": "VALID",
        "choice": "C1",
        "top_probability": 0.50,  # below DM1_TOP_PROBABILITY_MIN (0.70)
        "margin": 0.10,  # below DM1_MARGIN_MIN (0.30)
        "usage": {"input_tokens": 50, "output_tokens": 10},
    }
    monkeypatch.setattr(
        "nexus.research.hybrid_replication_live._jev_request",
        lambda **kwargs: (mock_jev, 0, 0.5),
    )

    mock_b_receipt = {
        "schema": "nexus.hybrid_replication.agy_live_raw.v1",
        "status": "VALID",
        "valid": True,
        "operation_id": "agyop_b_fallback_456",
        "observed_provider": "agy",
        "observed_model": EXACT_AGY_MODEL,
        "requested_model": EXACT_AGY_MODEL,
        "resolved_model": EXACT_AGY_MODEL,
        "transport_identity": "nexus-agy-dispatch",
        "usage": {"input_tokens": 80, "output_tokens": 20},
    }
    monkeypatch.setattr(
        "nexus.research.hybrid_replication_live._run_agy_b_fallback",
        lambda **kwargs: (mock_b_receipt, 1.8),
    )

    binding = {
        "repo_roots": {"James3014/Nexus-new": str(repo_dir)},
        "jev": {
            "requested_model": "jev-latest",
            "resolved_model": "jev-1.13.0",
        },
    }

    outcome = run_frozen_stack(snapshot, binding=binding)
    assert outcome.stratum == "B"
    assert outcome.raw_result.provider == "typesafe+agy"
    assert outcome.raw_result.requested_model == f"jev-latest+{EXACT_AGY_MODEL}"
    assert outcome.raw_result.resolved_model == f"jev-1.13.0+{EXACT_AGY_MODEL}"
    assert outcome.raw_result.fallbacks == ("DM1_TO_STRONG_ONLINE",)
    assert outcome.strong_online_raw_response == mock_b_receipt
    assert outcome.raw_result.failures == ()


def test_load_binding_accepts_current_canonical_agy_generation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    binding_path = tmp_path / "LIVE_BINDING.json"
    binding_path.write_text(
        json.dumps({
            "schema": "nexus.hybrid_replication.live_binding.v1",
            "activation_state": "AUTOMATIC_CAPTURE_READY",
            "frozen_receipts": {},
            "d0": {
                "implementation_path": "/tmp/d0_impl.py",
                "implementation_sha256": "cca215a2de82996c072f958159541a93d58b1482af3430d93f537c58ddafa2f9",
                "freeze_path": "/tmp/D0_V2_FROZEN.json",
                "freeze_sha256": "f04fdeea8ddb8cbaa2216aa783a7fe510da7c2f8625f50763a0d59d5e2234eee",
            },
            "strong_online": {
                "provider": "agy",
                "requested_model": EXACT_AGY_MODEL,
                "execution_generation": CANONICAL_AGY_EXECUTION_GENERATION,
            },
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "nexus.research.hybrid_replication_live._frozen_receipt_hashes",
        lambda payload: (FROZEN_RECEIPT_SHA256S, FROZEN_RECEIPT_SHA256S),
    )
    monkeypatch.setattr(
        "nexus.research.hybrid_replication_live._sha256_file",
        lambda path: (
            "cca215a2de82996c072f958159541a93d58b1482af3430d93f537c58ddafa2f9"
            if str(path).endswith("d0_impl.py")
            else "f04fdeea8ddb8cbaa2216aa783a7fe510da7c2f8625f50763a0d59d5e2234eee"
        ),
    )
    monkeypatch.setattr(
        "nexus.research.hybrid_replication_live.resolve_canonical_agy_dispatch_path",
        lambda payload: Path("/tmp/nexus-agy-dispatch"),
    )

    loaded = _load_binding(binding_path)

    assert loaded["strong_online"]["execution_generation"] == CANONICAL_AGY_EXECUTION_GENERATION


def test_agy_identity_preflight_passes_new_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = "a" * 64
    monkeypatch.setattr(
        "nexus.research.hybrid_replication_live.CANONICAL_AGY_DISPATCH_SHA256",
        canonical,
    )
    receipt = build_agy_identity_preflight_receipt(
        d0_sha256="cca215a2de82996c072f958159541a93d58b1482af3430d93f537c58ddafa2f9",
        d0_freeze_sha256="f04fdeea8ddb8cbaa2216aa783a7fe510da7c2f8625f50763a0d59d5e2234eee",
        frozen_receipt_sha256s=FROZEN_RECEIPT_SHA256S,
        declared_frozen_receipt_sha256s=FROZEN_RECEIPT_SHA256S,
        agy_dispatch_sha256=canonical,
        expected_agy_dispatch_sha256=canonical,
        requested_provider="agy",
        requested_model=EXACT_AGY_MODEL,
        execution_generation=CANONICAL_AGY_EXECUTION_GENERATION,
        previous_execution_generation="AGY_GEMINI_3_8_FLASH_MEDIUM_V3",
        jev_requested_model="jev-latest",
        jev_resolved_model="jev-1.13.0",
        expected_jev_resolved_model="jev-1.13.0",
        jev_status="VALID",
        jev_usage={},
        jev_latency_ms=1.0,
        created_at_utc="2026-10-01T13:00:00Z",
    )
    assert receipt["activation_allowed"] is True
    assert receipt["status"] == "PASS_NEW_EXECUTION_GENERATION"
    assert receipt["strong_online_identity_match"] is True
    assert receipt["transport_identity_match"] is True


def test_agy_identity_preflight_rejects_model_or_transport_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = "b" * 64
    monkeypatch.setattr(
        "nexus.research.hybrid_replication_live.CANONICAL_AGY_DISPATCH_SHA256",
        canonical,
    )
    receipt = build_agy_identity_preflight_receipt(
        d0_sha256="cca215a2de82996c072f958159541a93d58b1482af3430d93f537c58ddafa2f9",
        d0_freeze_sha256="f04fdeea8ddb8cbaa2216aa783a7fe510da7c2f8625f50763a0d59d5e2234eee",
        frozen_receipt_sha256s=FROZEN_RECEIPT_SHA256S,
        declared_frozen_receipt_sha256s=FROZEN_RECEIPT_SHA256S,
        agy_dispatch_sha256="c" * 64,
        expected_agy_dispatch_sha256=canonical,
        requested_provider="agy",
        requested_model="gemini-3.8-flash-high",
        execution_generation=CANONICAL_AGY_EXECUTION_GENERATION,
        previous_execution_generation="AGY_GEMINI_3_8_FLASH_MEDIUM_V3",
        jev_requested_model="jev-latest",
        jev_resolved_model="jev-1.13.0",
        expected_jev_resolved_model="jev-1.13.0",
        jev_status="VALID",
        jev_usage={},
        jev_latency_ms=1.0,
        created_at_utc="2026-10-01T13:00:00Z",
    )
    assert receipt["activation_allowed"] is False
    assert receipt["status"] == "BLOCKED_IDENTITY_OR_PROVIDER_DRIFT"
    assert receipt["strong_online_identity_match"] is False
    assert receipt["transport_identity_match"] is False
