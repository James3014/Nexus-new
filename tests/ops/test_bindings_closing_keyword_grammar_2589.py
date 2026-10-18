"""#2589: the bindings check must see every closing keyword GitHub acts on.

PR #2549 squash-merged with the commit line ``fix: #2532 projection honours ...``
in its body. GitHub read ``fix: #2532`` as a closing keyword and closed the
KEEP_OPEN P0 Issue #2532, while "Bindings preflight (default branch)" was green
because the keyword pattern required whitespace right after the keyword and
missed the colon form.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from nexus.services import issue_closure_guard
from scripts.ops import trusted_merge_lane_gate as gate

# The exact commit subject from PR #2549 (squash commit 2095ef107, line 70).
PR_2549_COMMIT_LINE = (
    "fix: #2532 projection honours the whole Core verdict; r1 review fixes (Refs #2532)"
)

GITHUB_CLOSING_FORMS = [
    ("fix: #2532", "fix"),
    ("Fixes: #2532", "fixes"),
    ("FIXED #2532", "fixed"),
    ("close #2532", "close"),
    ("Closes: #2532", "closes"),
    ("closed:#2532", "closed"),
    ("Resolve James3014/Nexus-new#2532", "resolve"),
    ("resolves: https://github.com/James3014/Nexus-new/issues/2532", "resolves"),
    ("RESOLVED : #2532", "resolved"),
    ("fixes GH-2532", "fixes"),
]

NOT_CLOSING_FORMS = [
    "Refs #2532",
    "fix(#2532): scope label",
    "prefix #2532",
    "fixing #2532",
    "#2532 remains open",
]


def _intent_body(issue: int, on_merge: str, prose: str) -> str:
    intent = gate.render_intent([{"issue": issue, "on_merge": on_merge}])
    return f"{prose}\n\n{intent}\n"


def _repo_with_commit(tmp_path: Path, message: str) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (
        ["init", "-q", "-b", "main"],
        ["config", "user.name", "Test"],
        ["config", "user.email", "test@example.invalid"],
        ["commit", "-q", "--allow-empty", "-m", "base"],
    ):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    base = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "--allow-empty", "-m", message],
        check=True,
        capture_output=True,
    )
    head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    return repo, base, head


def _final_binding(body: str, *, base: str, head: str, title: str, messages: str):
    return gate.validate_final_merge_intent_binding(
        pr_body=body,
        pr_number=2549,
        head_sha=head,
        base_sha=base,
        expected_pr_number=2549,
        expected_head_sha=head,
        expected_base_sha=base,
        merge_method="squash",
        commit_title=title,
        commit_message=messages,
    )


def test_pr_2549_commit_line_blocks_keep_open_issue(tmp_path: Path) -> None:
    """Reproduces #2549: a KEEP_OPEN Issue closed by 'fix: #2532' in a commit message."""
    message = f"{PR_2549_COMMIT_LINE}\n\nReview r1 fixes.\n\nRefs #2532."
    repo, base, head = _repo_with_commit(tmp_path, message)
    body = _intent_body(2532, "KEEP_OPEN", "Implements the projection. Refs #2532.")
    messages = gate._candidate_commit_messages(repo, base_sha=base, head_sha=head)

    with pytest.raises(gate.IssueClosureIntentError) as exc:
        _final_binding(
            body,
            base=base,
            head=head,
            title="feat: Issue promise coverage projection (#2532)",
            messages=messages,
        )

    text = str(exc.value)
    assert text.startswith("REJECTED_CLOSING_KEYWORD_FOR_KEEP_OPEN_IN_FINAL_MERGE_FIELDS")
    # Where it is and what to do, inside the first 300 characters that the
    # preflight and the sibling check print.
    head_text = text[:300]
    assert "commit messages line 1" in head_text
    assert "fix: #2532 projection" in head_text
    assert "Refs #2532" in head_text


@pytest.mark.parametrize(("text", "keyword"), GITHUB_CLOSING_FORMS)
def test_gate_matches_github_closing_keyword_grammar(text: str, keyword: str) -> None:
    assert gate.find_closing_keyword_references(f"Some prose.\n{text} more words") == [
        (keyword, 2532)
    ]


@pytest.mark.parametrize("text", NOT_CLOSING_FORMS)
def test_gate_ignores_non_closing_references(text: str) -> None:
    assert gate.find_closing_keyword_references(text) == []


@pytest.mark.parametrize(("text", "keyword"), GITHUB_CLOSING_FORMS)
def test_runtime_guard_matches_github_closing_keyword_grammar(text: str, keyword: str) -> None:
    assert issue_closure_guard.find_closing_keyword_references(
        f"Some prose.\n{text} more words"
    ) == [(keyword, 2532)]


@pytest.mark.parametrize("text", NOT_CLOSING_FORMS)
def test_runtime_guard_ignores_non_closing_references(text: str) -> None:
    assert issue_closure_guard.find_closing_keyword_references(text) == []


def test_colon_form_in_pr_body_blocks_keep_open() -> None:
    body = _intent_body(2532, "KEEP_OPEN", "Fixes: #2532 partially.")
    with pytest.raises(gate.IssueClosureIntentError) as exc:
        gate.validate_issue_closure_intent(body)
    text = str(exc.value)
    assert text.startswith("REJECTED_CLOSING_KEYWORD_FOR_KEEP_OPEN:")
    assert "PR body line 1" in text[:300]
    assert "Refs #2532" in text[:300]


def test_body_location_counts_lines_as_written_and_skips_marker_blocks() -> None:
    intent = gate.render_intent([{"issue": 2532, "on_merge": "KEEP_OPEN"}])
    body = f"{intent}\n\nIntro line.\nfixes: #2532 here\n"
    with pytest.raises(gate.IssueClosureIntentError) as exc:
        gate.validate_issue_closure_intent(body)
    expected_line = body.splitlines().index("fixes: #2532 here") + 1
    assert f"PR body line {expected_line}: 'fixes: #2532 here'" in str(exc.value)[:300]


def test_colon_form_for_undeclared_issue_in_commit_fails(tmp_path: Path) -> None:
    repo, base, head = _repo_with_commit(tmp_path, "fix: #77 unrelated cleanup")
    body = _intent_body(2532, "CLOSE", "Closes #2532.")
    messages = gate._candidate_commit_messages(repo, base_sha=base, head_sha=head)
    with pytest.raises(gate.IssueClosureIntentError) as exc:
        _final_binding(body, base=base, head=head, title="feat: thing", messages=messages)
    text = str(exc.value)
    assert text.startswith("UNINTENDED_CLOSING_KEYWORD_FOR_UNTRACKED_ISSUE")
    assert "fix: #77 unrelated cleanup" in text[:300]
    assert "Refs #77" in text[:300]


def test_colon_form_in_pr_title_is_located(tmp_path: Path) -> None:
    repo, base, head = _repo_with_commit(tmp_path, "chore: neutral")
    body = _intent_body(2532, "KEEP_OPEN", "#2532 remains open.")
    messages = gate._candidate_commit_messages(repo, base_sha=base, head_sha=head)
    with pytest.raises(gate.IssueClosureIntentError) as exc:
        _final_binding(body, base=base, head=head, title="Fix: #2532 slice", messages=messages)
    assert "PR title line 1: 'Fix: #2532 slice'" in str(exc.value)[:300]


def test_close_intent_accepts_colon_form(tmp_path: Path) -> None:
    repo, base, head = _repo_with_commit(tmp_path, "fix: #2532 the bug\n\nCloses: #2532.")
    body = _intent_body(2532, "CLOSE", "Closes: #2532.")
    messages = gate._candidate_commit_messages(repo, base_sha=base, head_sha=head)
    result = _final_binding(body, base=base, head=head, title="fix: the bug", messages=messages)
    assert result["status"] == "PASS"
    assert {"issue_number": 2532, "keyword": "fix"} in result["detected_final_closing_references"]
