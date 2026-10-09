from __future__ import annotations

from nexus.research.hybrid_replication_live import (
    FROZEN_RECEIPT_SHA256S,
    _c_prompt,
    _valid_probability_distribution,
    build_d2_candidate_packet,
    build_identity_preflight_receipt,
    classify_frozen_task_family,
    resolve_ground_truth_payload,
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
