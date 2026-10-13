"""Nightly quarantine entry: tests/nexus/orchestrator/test_owner_representation.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/nexus/orchestrator/test_owner_representation.py",
    "disposition": "quarantine-product-bug?",
    "issue": "#1924",
    "cause": "fails in isolation: scripts/ops/workforce_model_autoupdate.py (#1996/#1997) creates GitHub Issues/PRs programmatically (gh issue create at ~L1581, gh pr create plan text at L1486) outside the owner-representation transport inventory; the source scan only catches the literal plan string. Needs an owner decision to inventory/authorize the autoupdater route or move it behind the governed publisher; rewording the string would hide a real write sink",
    "tests": ("test_no_silent_github_write_sink_in_source[gh_cli_issue_pr_create]",),
}
