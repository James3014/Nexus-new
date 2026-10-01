from __future__ import annotations

from nexus.research.hybrid_replication_live import (
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
        codex_cli="codex-cli 0.159.3",
        previous_codex_cli="codex-cli 0.158.0",
        codex_executable_sha256="61b0194f3bb6534439c8d26a3ed57d0805f84b884588b761795323eeb92fcf70",
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
