from __future__ import annotations

from scripts.ops.hybrid_replication_ground_truth import derive_ground_truth


def test_open_issue_has_no_terminal_ground_truth() -> None:
    assert derive_ground_truth(
        repository="James3014/Nexus-new",
        issue={"number": 1400, "state": "open", "closed_at": None},
        pull_requests=[],
    ) is None


def test_merged_pr_is_durable_terminal_ground_truth() -> None:
    result = derive_ground_truth(
        repository="James3014/Nexus-new",
        issue={
            "number": 1400,
            "state": "closed",
            "closed_at": "2026-10-01T03:00:00Z",
        },
        pull_requests=[
            {
                "number": 1401,
                "merged_at": "2026-10-01T02:59:00Z",
                "merge_commit_sha": "a" * 40,
                "html_url": "https://github.com/James3014/Nexus-new/pull/1401",
            }
        ],
    )

    assert result["terminal_state"] == "MERGED"
    assert result["terminal_at"] == "2026-10-01T02:59:00Z"
    assert any("pull/1401" in ref for ref in result["evidence_refs"])


def test_closed_without_merge_remains_distinct_terminal_class() -> None:
    result = derive_ground_truth(
        repository="James3014/Nexus-new",
        issue={
            "number": 1400,
            "state": "closed",
            "closed_at": "2026-10-01T03:00:00Z",
        },
        pull_requests=[],
    )

    assert result["terminal_state"] == "CLOSED_NO_MERGED_PR"
    assert result["terminal_at"] == "2026-10-01T03:00:00Z"
