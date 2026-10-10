import base64
import gzip
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from nexus.research.hybrid_replication_live import (
    CANONICAL_AGY_DISPATCH_SHA256,
    CANONICAL_AGY_EXECUTION_GENERATION,
    EXACT_AGY_MODEL,
    FROZEN_RECEIPT_SHA256S,
    _c_prompt,
    _load_binding,
    _run_agy_b_fallback,
    _run_agy_candidate,
    _valid_probability_distribution,
    audit_post_terminal_revisions,
    build_agy_identity_preflight_receipt,
    build_d2_candidate_packet,
    build_identity_preflight_receipt,
    build_post_terminal_revision_events,
    evaluate_agy_receipt,
    poll_agy_operation,
    resolve_canonical_agy_dispatch_path,
    resolve_ground_truth_payload,
    run_frozen_stack,
    seal_shadow_candidate,
)


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


def _post_terminal_scored_state() -> dict[str, object]:
    return {
        "task_key": "James3014/Nexus-new#1541",
        "admission_disposition": "ADMITTED_PRIMARY_FRESH_TASK",
        "phase": "SCORED",
        "snapshot": {
            "repository": "James3014/Nexus-new",
            "issue_number": 1541,
        },
        "ground_truth": {
            "sha256": "a" * 64,
            "terminal_at": "2026-10-07T08:46:22Z",
            "terminal_state": "CLOSED_WITH_MERGED_PR",
        },
        "score": {
            "sha256": "b" * 64,
            "path": "score.json",
        },
    }


def test_post_terminal_revision_detects_reopen_without_rewriting_score() -> None:
    state = _post_terminal_scored_state()
    events = build_post_terminal_revision_events(
        state=state,
        timeline=(
            {
                "id": 10,
                "event": "closed",
                "created_at": "2026-10-07T08:46:22Z",
                "actor": {"login": "James3014"},
            },
            {
                "id": 11,
                "event": "reopened",
                "created_at": "2026-10-07T09:21:35Z",
                "actor": {"login": "James3014"},
            },
            {
                "id": 12,
                "event": "closed",
                "created_at": "2026-10-07T09:42:17Z",
                "actor": {"login": "James3014"},
            },
        ),
    )

    assert [item["event"] for item in events] == ["reopened", "closed"]
    assert events[0]["score_effect"] == "SUPERSEDED_BY_POST_TERMINAL_REOPEN"
    assert events[1]["score_effect"] == "POST_REOPEN_RECLOSURE_OBSERVED"
    assert all(item["score_rewrite"] is False for item in events)
    assert all(item["raw_rewrite"] is False for item in events)
    assert all(item["route_rewrite"] is False for item in events)


def test_post_terminal_revision_ignores_non_reopen_lifecycle_noise() -> None:
    events = build_post_terminal_revision_events(
        state=_post_terminal_scored_state(),
        timeline=(
            {
                "id": 20,
                "event": "labeled",
                "created_at": "2026-10-07T09:00:00Z",
            },
            {
                "id": 21,
                "event": "closed",
                "created_at": "2026-10-07T09:10:00Z",
            },
        ),
    )
    assert events == ()


def test_post_terminal_audit_is_append_only_and_reduces_effective_scored_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nexus.research.hybrid_replication_live as live

    store_root = tmp_path / "store"
    task_root = store_root / "tasks" / "task"
    task_root.mkdir(parents=True)
    ground_truth_bytes = b'{"terminal":"original"}\n'
    score_bytes = b'{"score":"original"}\n'
    (task_root / "ground_truth.json").write_bytes(ground_truth_bytes)
    (task_root / "score.json").write_bytes(score_bytes)

    state = _post_terminal_scored_state()
    state["ground_truth"] = {
        **dict(state["ground_truth"]),
        "sha256": hashlib.sha256(ground_truth_bytes).hexdigest(),
    }
    state["score"] = {
        **dict(state["score"]),
        "sha256": hashlib.sha256(score_bytes).hexdigest(),
    }
    (task_root / "state.json").write_text(json.dumps(state), encoding="utf-8")

    timeline = [
        {
            "id": 6034936137,
            "event": "reopened",
            "created_at": "2026-10-07T09:21:35Z",
            "actor": {"login": "James3014"},
        },
        {
            "id": 6035292584,
            "event": "closed",
            "created_at": "2026-10-07T09:42:17Z",
            "actor": {"login": "James3014"},
        },
    ]
    monkeypatch.setattr(live, "_gh_list", lambda *_args, **_kwargs: timeline)

    output_root = tmp_path / "post-terminal-revisions"
    first = audit_post_terminal_revisions(store_root=store_root, output_root=output_root)
    second = audit_post_terminal_revisions(store_root=store_root, output_root=output_root)

    assert first["scored_primary_count"] == 1
    assert first["effective_scored_primary_count"] == 0
    assert first["superseded_task_keys"] == ["James3014/Nexus-new#1541"]
    assert [row["write_disposition"] for row in first["revision_receipts"]] == [
        "CREATED",
        "CREATED",
    ]
    assert [row["write_disposition"] for row in second["revision_receipts"]] == [
        "REUSED_SAME_BYTES",
        "REUSED_SAME_BYTES",
    ]
    assert first["score_rewrite"] is False
    assert (task_root / "score.json").read_bytes() == score_bytes
    assert (task_root / "ground_truth.json").read_bytes() == ground_truth_bytes


def test_post_terminal_audit_fail_closes_on_conflicting_revision_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nexus.research.hybrid_replication_live as live

    store_root = tmp_path / "store"
    task_root = store_root / "tasks" / "task"
    task_root.mkdir(parents=True)
    ground_truth_bytes = b'{"terminal":"original"}\n'
    score_bytes = b'{"score":"original"}\n'
    (task_root / "ground_truth.json").write_bytes(ground_truth_bytes)
    (task_root / "score.json").write_bytes(score_bytes)
    state = _post_terminal_scored_state()
    state["ground_truth"] = {
        **dict(state["ground_truth"]),
        "sha256": hashlib.sha256(ground_truth_bytes).hexdigest(),
    }
    state["score"] = {
        **dict(state["score"]),
        "sha256": hashlib.sha256(score_bytes).hexdigest(),
    }
    (task_root / "state.json").write_text(json.dumps(state), encoding="utf-8")

    timeline = [
        {
            "id": 99,
            "event": "reopened",
            "created_at": "2026-10-07T09:21:35Z",
            "actor": {"login": "James3014"},
        }
    ]
    monkeypatch.setattr(live, "_gh_list", lambda *_args, **_kwargs: timeline)
    output_root = tmp_path / "post-terminal-revisions"
    first = audit_post_terminal_revisions(store_root=store_root, output_root=output_root)
    receipt_path = Path(first["revision_receipts"][0]["path"])
    receipt_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="immutable_post_terminal_revision_conflict"):
        audit_post_terminal_revisions(store_root=store_root, output_root=output_root)


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
    assert "SANDBOX BOUNDARY:" in prompt
    assert prompt.index("SANDBOX BOUNDARY:") < prompt.index("TASK KEY:")
    hinted, _ = _c_prompt(snapshot, localization_hint_path="nexus/x.py")
    assert hinted.index("SANDBOX BOUNDARY:") < hinted.index("LOCALIZATION (")
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
        assert (
            subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=source,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            == rev
        )
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


_NATURAL_PATHS = tuple(f"nexus/mod{i}.py" for i in range(1, 9))


def _commit_files(repo_dir: Path, names: tuple[str, ...], content: str = "x = 1\n") -> str:
    for name in names:
        target = repo_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "add files"], cwd=repo_dir, check=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_dir, check=True, capture_output=True, text=True
    ).stdout.strip()


def _natural_snapshot(rev: str, *, title: str, body: str, issue: int = 101):
    from nexus.research.hybrid_replication_pipeline import TaskSnapshot

    return TaskSnapshot.create(
        repository="James3014/Nexus-new",
        issue_number=issue,
        created_at="2026-10-01T00:00:00Z",
        captured_at="2026-10-01T00:00:00Z",
        issue_updated_at="2026-10-01T00:00:00Z",
        title=title,
        body=body,
        pre_implementation_revision=rev,
        default_branch="trunk",
        source_event_id=f"test:run_frozen_stack:{issue}",
    )


_STRONG_RECEIPT = {
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

_JEV_BINDING_PART = {"requested_model": "jev-latest", "resolved_model": "jev-1.13.0"}


def _wire_stack(
    monkeypatch: pytest.MonkeyPatch,
    *,
    ranked: tuple[str, ...],
    jev: dict[str, object] | None,
) -> dict[str, list]:
    calls: dict[str, list] = {"rank": [], "jev": [], "strong": []}

    def fake_rank(**kwargs):
        calls["rank"].append(kwargs)
        return ranked, {}

    def fake_jev(**kwargs):
        calls["jev"].append(kwargs)
        assert jev is not None
        return jev, 0, 0.5

    def fake_strong(**kwargs):
        calls["strong"].append(kwargs)
        return _STRONG_RECEIPT, 2.5

    monkeypatch.setattr("nexus.research.hybrid_replication_live._rank_candidates", fake_rank)
    monkeypatch.setattr("nexus.research.hybrid_replication_live._jev_request", fake_jev)
    monkeypatch.setattr("nexus.research.hybrid_replication_live._run_agy_candidate", fake_strong)
    return calls


def _natural_stack(
    tmp_path: Path,
    monkeypatch,
    *,
    ranked,
    jev,
    body: str = "Implement the bounded retry fix and add regression tests.",
    extra_paths: tuple[str, ...] = (),
):
    repo_dir = tmp_path / "repo"
    rev = _init_test_git_repo(repo_dir)
    rev = _commit_files(repo_dir, _NATURAL_PATHS + extra_paths)
    snapshot = _natural_snapshot(rev, title="Fix retry semantics", body=body)
    calls = _wire_stack(monkeypatch, ranked=ranked, jev=jev)
    binding = {
        "repo_roots": {"James3014/Nexus-new": str(repo_dir)},
        "jev": _JEV_BINDING_PART,
    }
    return run_frozen_stack(snapshot, binding=binding), calls


def test_natural_task_dm1_accept_routes_b_with_localization_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jev = {
        "status": "VALID",
        "choice": "C3",
        "top_probability": 0.9,
        "margin": 0.5,
        "usage": {"input_tokens": 50, "output_tokens": 10},
    }
    outcome, calls = _natural_stack(tmp_path, monkeypatch, ranked=_NATURAL_PATHS, jev=jev)
    assert outcome.stratum == "B"
    assert len(calls["jev"]) == 1 and len(calls["strong"]) == 1
    hint = _NATURAL_PATHS[2]
    prompt = calls["strong"][0]["prompt"]
    assert f"LOCALIZATION (DM1-accepted under the frozen policy): start at `{hint}`." in prompt
    assert calls["strong"][0]["default_branch"] == "trunk"
    raw = outcome.raw_result
    assert raw.provider == "typesafe+agy"
    assert raw.requested_model == f"jev-latest+{EXACT_AGY_MODEL}"
    assert raw.resolved_model == f"jev-1.13.0+{EXACT_AGY_MODEL}"
    assert raw.model_call_count == 2
    assert raw.fallbacks == ()
    assert raw.failures == ()
    assert raw.input_tokens == 200 and raw.output_tokens == 60
    assert raw.raw_response["localization_hint_path"] == hint
    assert raw.raw_response["accepted_by_frozen_policy"] is True
    assert raw.raw_response["dm1_applicable"] is True
    assert raw.raw_response["strong_online_raw_response"] == _STRONG_RECEIPT
    assert "d0_wall_seconds" in raw.raw_response
    assert outcome.dm1_decision["applicable"] is True
    outcome.validate()


def test_natural_task_seals_frozen_d0_top8_separately_from_truncated_packet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ranked = _NATURAL_PATHS + ("nexus/mod9.py",)
    outcome, _calls = _natural_stack(
        tmp_path,
        monkeypatch,
        ranked=ranked,
        jev={
            "status": "VALID",
            "choice": "ESCALATE",
            "top_probability": 0.4,
            "margin": 0.1,
            "usage": {"input_tokens": 50, "output_tokens": 10},
        },
        body="Fix `nexus/literal.py` and add regression tests.",
        extra_paths=("nexus/literal.py", "nexus/mod9.py"),
    )
    raw = outcome.raw_result.raw_response
    catalog = raw["candidate_packet"]["candidate_catalog"]
    assert [item["path"] for item in catalog] == ["nexus/literal.py", *_NATURAL_PATHS[:7]]
    assert catalog[0]["source"] == "LITERAL_TASK_PATH"
    # The sealed D0 top-8 is the frozen ranking itself: no literal paths, no
    # truncation by the packet, and nothing past rank 8.
    assert raw["d0_top8_paths"] == list(_NATURAL_PATHS)


def test_frozen_task_family_is_conservative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nexus.research.hybrid_replication_live as live

    assert not hasattr(live, "classify_frozen_task_family")
    jev = {
        "status": "VALID",
        "choice": "ESCALATE",
        "top_probability": 0.4,
        "margin": 0.1,
        "usage": {"input_tokens": 50, "output_tokens": 10},
    }
    outcome, calls = _natural_stack(tmp_path, monkeypatch, ranked=_NATURAL_PATHS, jev=jev)
    assert len(calls["rank"]) == 1
    assert outcome.stratum in {"B", "C"}


def test_run_frozen_stack_b_fallback_uses_agy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jev = {
        "status": "VALID",
        "choice": "ESCALATE",
        "top_probability": 0.4,
        "margin": 0.1,
        "usage": {"input_tokens": 50, "output_tokens": 10},
    }
    outcome, calls = _natural_stack(tmp_path, monkeypatch, ranked=_NATURAL_PATHS, jev=jev)
    assert outcome.stratum == "C"
    assert "LOCALIZATION" not in calls["strong"][0]["prompt"]
    raw = outcome.raw_result
    assert raw.fallbacks == ("DM1_TO_STRONG_ONLINE",)
    assert raw.model_call_count == 2
    assert raw.raw_response["localization_hint_path"] is None
    assert raw.raw_response["accepted_by_frozen_policy"] is False
    outcome.validate()


def test_natural_task_low_margin_jev_choice_routes_c(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jev = {
        "status": "VALID",
        "choice": "C1",
        "top_probability": 0.5,
        "margin": 0.1,
        "usage": {"input_tokens": 50, "output_tokens": 10},
    }
    outcome, calls = _natural_stack(tmp_path, monkeypatch, ranked=_NATURAL_PATHS, jev=jev)
    assert outcome.stratum == "C"
    assert "LOCALIZATION" not in calls["strong"][0]["prompt"]
    assert outcome.raw_result.fallbacks == ("DM1_TO_STRONG_ONLINE",)


def test_natural_task_unmapped_jev_choice_is_not_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jev = {
        "status": "VALID",
        "choice": "C99",
        "top_probability": 0.9,
        "margin": 0.5,
        "usage": {"input_tokens": 50, "output_tokens": 10},
    }
    outcome, calls = _natural_stack(tmp_path, monkeypatch, ranked=_NATURAL_PATHS, jev=jev)
    assert outcome.stratum == "C"
    assert outcome.dm1_decision["unmapped_choice"] is True
    assert "LOCALIZATION" not in calls["strong"][0]["prompt"]


def test_run_frozen_stack_c_uses_agy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outcome, calls = _natural_stack(tmp_path, monkeypatch, ranked=("nexus/mod1.py",), jev=None)
    assert outcome.stratum == "C"
    assert calls["jev"] == []
    assert len(calls["strong"]) == 1
    raw = outcome.raw_result
    assert raw.provider == "agy"
    assert raw.requested_model == EXACT_AGY_MODEL
    assert raw.model_call_count == 1
    assert raw.fallbacks == ()
    assert raw.raw_response["dm1_applicable"] is False
    assert outcome.jev_raw_response is None
    assert outcome.dm1_decision["reason"] == "candidate_set_below_two"
    assert outcome.deterministic_receipt["dm1_applicable"] is False
    assert "family_probe" not in outcome.deterministic_receipt
    outcome.validate()


def _timeout_stack(tmp_path: Path, monkeypatch, strong_online):
    repo_dir = tmp_path / "repo"
    _init_test_git_repo(repo_dir)
    rev = _commit_files(repo_dir, _NATURAL_PATHS)
    snapshot = _natural_snapshot(
        rev, title="Fix retry semantics", body="Implement the bounded retry fix.", issue=104
    )
    jev = {"status": "VALID", "choice": "ESCALATE", "usage": {}}
    calls = _wire_stack(monkeypatch, ranked=_NATURAL_PATHS, jev=jev)
    binding: dict[str, object] = {
        "repo_roots": {"James3014/Nexus-new": str(repo_dir)},
        "jev": _JEV_BINDING_PART,
    }
    if strong_online is not None:
        binding["strong_online"] = strong_online
    return snapshot, binding, calls


def test_strong_online_timeout_defaults_to_300_seconds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot, binding, calls = _timeout_stack(tmp_path, monkeypatch, None)
    outcome = run_frozen_stack(snapshot, binding=binding)
    assert calls["strong"][0]["timeout"] == 300
    assert calls["strong"][0]["poll_timeout"] == 360.0
    assert outcome.raw_result.raw_response["strong_online_timeout_seconds"] == 300


def test_strong_online_timeout_is_bound_from_generation_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot, binding, calls = _timeout_stack(
        tmp_path,
        monkeypatch,
        {"provider": "agy", "effort": "medium", "candidate_timeout_seconds": 1800},
    )
    outcome = run_frozen_stack(snapshot, binding=binding)
    assert calls["strong"][0]["timeout"] == 1800
    assert calls["strong"][0]["poll_timeout"] == 1860.0
    assert outcome.raw_result.raw_response["strong_online_timeout_seconds"] == 1800


@pytest.mark.parametrize("bad", [10, "abc", 7201, True, None])
def test_invalid_strong_online_timeout_fails_before_any_model_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad: object
) -> None:
    snapshot, binding, calls = _timeout_stack(
        tmp_path, monkeypatch, {"candidate_timeout_seconds": bad}
    )
    with pytest.raises(ValueError, match="strong_online_candidate_timeout_invalid"):
        run_frozen_stack(snapshot, binding=binding)
    assert calls["jev"] == []
    assert calls["strong"] == []


def test_a_template_task_routes_a_without_model_calls_or_ranking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_dir = tmp_path / "repo"
    _init_test_git_repo(repo_dir)
    rev = _commit_files(repo_dir, ("nexus/core/example.py",), content="import os\n")
    snapshot = _natural_snapshot(
        rev,
        title="Dependency discovery",
        body=(
            "At commit abc, perform dependency discovery for `nexus/core/example.py`. "
            "Return its direct imported modules, repository files that directly import "
            "this module, and its public top-level functions/classes."
        ),
        issue=103,
    )
    calls = _wire_stack(monkeypatch, ranked=_NATURAL_PATHS, jev=None)
    outcome = run_frozen_stack(
        snapshot, binding={"repo_roots": {"James3014/Nexus-new": str(repo_dir)}}
    )
    assert outcome.stratum == "A"
    assert outcome.raw_result.model_call_count == 0
    assert calls == {"rank": [], "jev": [], "strong": []}
    outcome.validate()


def _write_loadable_agy_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    activation_state: str,
) -> Path:
    binding_path = tmp_path / "LIVE_BINDING.json"
    binding_path.write_text(
        json.dumps({
            "schema": "nexus.hybrid_replication.live_binding.v1",
            "activation_state": activation_state,
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
    return binding_path


def test_load_binding_pending_readiness_control_requires_explicit_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding_path = _write_loadable_agy_binding(
        tmp_path,
        monkeypatch,
        activation_state="READINESS_CONTROL_PENDING",
    )

    with pytest.raises(ValueError, match="live_binding_not_activated"):
        _load_binding(binding_path)

    loaded = _load_binding(binding_path, readiness_control=True)
    assert loaded["activation_state"] == "READINESS_CONTROL_PENDING"


def test_load_binding_ready_state_is_not_readiness_control_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding_path = _write_loadable_agy_binding(
        tmp_path,
        monkeypatch,
        activation_state="AUTOMATIC_CAPTURE_READY",
    )

    with pytest.raises(ValueError, match="live_binding_not_activated"):
        _load_binding(binding_path, readiness_control=True)


def test_load_binding_accepts_current_canonical_agy_generation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    binding_path = _write_loadable_agy_binding(
        tmp_path,
        monkeypatch,
        activation_state="AUTOMATIC_CAPTURE_READY",
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
        previous_execution_generation="AGY_GEMINI_3_8_FLASH_MEDIUM_V5",
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


def test_canonical_agy_dispatch_identity_matches_source() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    dispatch_path = repo_root / "scripts" / "ops" / "nexus-agy-dispatch"

    assert hashlib.sha256(dispatch_path.read_bytes()).hexdigest() == CANONICAL_AGY_DISPATCH_SHA256
    assert CANONICAL_AGY_EXECUTION_GENERATION == "AGY_GEMINI_3_8_FLASH_MEDIUM_V11"


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
        previous_execution_generation="AGY_GEMINI_3_8_FLASH_MEDIUM_V5",
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


def test_prospective_agy_dispatch_recovers_matching_operation_without_relaunch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.research import hybrid_replication_live as live
    from nexus.research.hybrid_replication_pipeline import (
        AdmissionReceipt,
        AutomaticReplicationStore,
        TaskSnapshot,
        build_admission_comment,
    )
    from nexus.research.hybrid_replication_prospective import ProspectiveExecutionGuard

    snapshot = TaskSnapshot.create(
        repository="James3014/Nexus-new",
        issue_number=1990,
        created_at="2026-10-07T12:00:00Z",
        captured_at="2026-10-07T12:00:01Z",
        issue_updated_at="2026-10-07T12:00:00Z",
        title="Lost ack control",
        body="Implement bounded shadow change.",
        pre_implementation_revision="a" * 40,
        default_branch="main",
        source_event_id="lost-ack:1990",
    )
    store = AutomaticReplicationStore(tmp_path / "store")
    store.capture(snapshot, admission_disposition="PRE_AUTOMATION_PROVISIONAL_CAPTURE")
    receipt = AdmissionReceipt.create(
        snapshot=snapshot,
        disposition="ADMITTED_PRIMARY_FRESH_TASK",
        activation_boundary="2026-10-07T11:59:59Z",
        activation_state="AUTOMATIC_CAPTURE_READY",
        exclusion_set_sha256="6" * 64,
        issue_state_at_admission="open",
        implementation_pr_numbers=(),
        tracked_parent_issue_number=None,
        tracked_parent_created_at=None,
        admitted_at="2026-10-07T12:00:02Z",
    )
    store.apply_admission(receipt)
    guard = ProspectiveExecutionGuard(store_root=tmp_path / "store", snapshot=snapshot)
    monkeypatch.setattr(
        "nexus.research.hybrid_replication_prospective._gh_list",
        lambda path: (
            [{"body": build_admission_comment(receipt)}] if path.endswith("/comments") else []
        ),
    )
    monkeypatch.setattr(
        "nexus.research.hybrid_replication_prospective._gh_json",
        lambda *args: {"state": "open", "updated_at": "2026-10-07T12:00:02Z"},
    )
    guard.ensure_execution_start()

    cwd = guard.shadow_source("c")
    cwd.mkdir(parents=True)
    operation_root = tmp_path / "operations"
    op_dir = operation_root / "operations" / "agyop_existing"
    op_dir.mkdir(parents=True)
    prompt = "same prompt"
    prompt_sha = live._sha256_bytes(prompt.encode("utf-8"))
    operation = {
        "operation_id": "agyop_existing",
        "status": "COMPLETED",
        "provider": "agy",
        "model": live.EXACT_AGY_MODEL,
        "observed_provider": "agy",
        "observed_model": live.EXACT_AGY_MODEL,
        "prompt_sha256": prompt_sha,
        "cwd": str(cwd.resolve()),
        "created_at": "2026-10-07T12:00:03Z",
        "provider_started_at": "2026-10-07T12:00:04Z",
    }
    (op_dir / "operation.json").write_text(json.dumps(operation), encoding="utf-8")
    (op_dir / "stdout.log").write_text("", encoding="utf-8")
    (op_dir / "stderr.log").write_text("", encoding="utf-8")

    dispatch = tmp_path / live.CANONICAL_AGY_DISPATCH_NAME
    dispatch.write_text("stub", encoding="utf-8")
    monkeypatch.setattr(live, "resolve_canonical_agy_dispatch_path", lambda _: dispatch)
    monkeypatch.setattr(
        live,
        "_run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("dispatcher must not relaunch after lost ack")
        ),
    )
    monkeypatch.setattr(
        live,
        "poll_agy_operation",
        lambda *args, **kwargs: (operation, False, None),
    )

    record, _, _, _, timed_out, err, _ = live._run_agy_dispatch(
        cwd=cwd,
        prompt=prompt,
        mode="accept-edits",
        binding={"strong_online": {"effort": "medium"}},
        operation_root=operation_root,
        prospective_guard=guard,
        effect_slot="c",
    )

    assert record is not None
    assert record["operation_id"] == "agyop_existing"
    assert timed_out is False
    assert err is None
