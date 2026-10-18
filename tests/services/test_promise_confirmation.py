"""RED contract for the per-promise confirmation report (#2532 stage 3, #2453 input)."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from nexus.orchestrator.task_contract import (
    issue_promise_set_identity,
    parse_issue_promise_set,
)
from nexus.services.promise_confirmation import (
    build_promise_confirmation_report,
    emit_promise_blocks,
    emit_witness_templates,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _cli_pythonpath() -> str:
    # Keep the caller's PYTHONPATH: CI runs pytest with the dependencies only
    # on PYTHONPATH (python -S), so replacing it would hide pydantic.
    existing = os.environ.get("PYTHONPATH")
    return os.pathsep.join([str(REPO_ROOT), *([existing] if existing else [])])


def _parsed(body: str) -> dict:
    parsed = parse_issue_promise_set(body)
    assert parsed is not None
    return parsed


HEAD = "a" * 40
MERGE = "b" * 40
LIVE = "c" * 40
OTHER = "d" * 40
NOW = "2026-10-18T12:00:00Z"
PR_CREATED = "2026-10-17T00:00:00Z"
PR_MERGED = "2026-10-17T06:00:00Z"
OBSERVED_POST = "2026-10-17T08:00:00Z"
OBSERVED_PRE = "2026-10-17T03:00:00Z"


def stmt(pid: str, entry: str = "real-entry") -> dict:
    return {
        "promise_id": pid,
        "statement": f"statement {pid}",
        "observe": "output shows X",
        "entry": f"{entry}-{pid}",
        "counterexample": "output shows Y",
    }


def body_for(statements, phases_risks, generation=1) -> str:
    return "Issue text\n\n" + emit_promise_blocks(statements, generation, phases_risks)


def pr(merged=True, number=2549) -> dict:
    return {
        "number": number,
        "head_sha": HEAD,
        "merge_sha": MERGE if merged else None,
        "created_at": PR_CREATED,
        "merged_at": PR_MERGED if merged else None,
    }


def contains_all(ancestor, commit):
    return True


def witness_comment(
    pid,
    *,
    phase="POST_MERGE",
    result="PASS",
    commit=LIVE,
    by="worker-a",
    entry=None,
    identity=None,
    body=None,
    observed=None,
    pr_no=2549,
    extra=None,
    author="bot",
    assoc="OWNER",
    updated=None,
):
    payload = {
        "promise_id": pid,
        "promise_set_identity": identity,
        "phase": phase,
        "pr": pr_no,
        "commit": commit,
        "entry": entry if entry is not None else f"real-entry-{pid}",
        "result": result,
        "observed_at": observed or (OBSERVED_POST if phase == "POST_MERGE" else OBSERVED_PRE),
        "by": by,
        "evidence": "ran it, saw output",
    }
    if extra:
        payload.update(extra)
    text = body if body is not None else json.dumps(payload)
    return {
        "body": f"<!-- NEXUS_PROMISE_WITNESS_V1\n{text}\nNEXUS_PROMISE_WITNESS_V1 -->",
        "created_at": OBSERVED_POST,
        "updated_at": updated or OBSERVED_POST,
        "author": author,
        "author_association": assoc,
    }


def confirmation_comment(
    identity,
    verdicts,
    *,
    confirmer="reviewer-b",
    commit=LIVE,
    created="2026-10-18T01:00:00Z",
    checked=True,
    author="bot",
    assoc="OWNER",
    updated=None,
):
    payload = {
        "promise_set_identity": identity,
        "commit": commit,
        "confirmer": confirmer,
        "promises": [
            {"promise_id": p, "verdict": v, "counterexample_checked": checked, "note": "n"}
            for p, v in verdicts.items()
        ],
    }
    return {
        "body": "<!-- NEXUS_PROMISE_CONFIRMATION_V1\n"
        + json.dumps(payload)
        + "\nNEXUS_PROMISE_CONFIRMATION_V1 -->",
        "created_at": created,
        "updated_at": updated or created,
        "author": author,
        "author_association": assoc,
    }


def setup(pids=("P1",), phase="POST_MERGE", risk="STANDARD", generation=1):
    statements = [stmt(p) for p in pids]
    pr_map = {p: (phase, risk) for p in pids}
    body = body_for(statements, pr_map, generation)
    identity = issue_promise_set_identity(_parsed(body))
    return body, identity


def report(
    body,
    comments,
    *,
    prs=None,
    history=(),
    contains=contains_all,
    authors=(),
    trusted=(),
    issue_created_at: str | None = "2026-01-01T00:00:00Z",
    shared=(),
    author_sessions=("author-session",),
    linked=(),
):
    return build_promise_confirmation_report(
        author_sessions=list(author_sessions),
        linked_pr_created_at=None if linked is None else list(linked),
        author_identities=list(authors),
        trusted_logins=list(trusted),
        issue_created_at=issue_created_at,
        shared_logins=list(shared),
        issue_body=body,
        body_history=None if history is None else list(history),
        comments=comments,
        prs=[pr()] if prs is None else prs,
        contains=contains,
        now=NOW,
    )


def row(rep, pid):
    return next(r for r in rep["promises"] if r["promise_id"] == pid)


def test_no_promise_set_is_not_applicable():
    rep = report("just an issue", [], history=[])
    assert rep["applicable"] is False
    assert rep["recommendation"] == "NOT_APPLICABLE"


def test_tests_green_but_real_entry_not_exercised_is_not_verified():
    body, ident = setup(phase="PRE_MERGE")
    unit = witness_comment("P1", phase="PRE_MERGE", commit=HEAD, identity=ident, entry="unit test")
    rep = report(body, [unit])
    assert row(rep, "P1")["status"] == "UNCOVERED"
    assert "WITNESS_ENTRY_MISMATCH" in row(rep, "P1")["reason_codes"]
    assert rep["recommendation"] == "PROVISIONAL"
    body2, ident2 = setup(phase="POST_MERGE")
    not_ex = witness_comment("P1", result="NOT_EXERCISED", identity=ident2)
    rep2 = report(body2, [not_ex])
    assert row(rep2, "P1")["status"] == "UNCOVERED"
    assert rep2["recommendation"] == "PROVISIONAL"
    assert rep2["uncovered"] == ["P1"]


def test_real_entry_ran_but_observed_error_reports_failed():
    body, ident = setup()
    comments = [
        witness_comment("P1", result="ACTUAL_FAILED", identity=ident, by="w1"),
        witness_comment("P1", result="PASS", identity=ident, by="w2"),
    ]
    rep = report(body, comments)
    assert row(rep, "P1")["status"] == "FAILED"
    assert rep["recommendation"] == "LIVE_FAILED"
    assert rep["failed"] == 1


def test_correct_version_all_promises_witnessed_and_independently_confirmed_supports_verified():
    body, ident = setup(pids=("P1", "P2"))
    comments = [witness_comment(p, identity=ident) for p in ("P1", "P2")]
    comments.append(confirmation_comment(ident, {"P1": "ACCEPT", "P2": "ACCEPT"}))
    rep = report(body, comments)
    assert [row(rep, p)["status"] for p in ("P1", "P2")] == ["WITNESSED", "WITNESSED"]
    assert rep["recommendation"] == "VERIFIED"
    assert rep["claim_ceiling"] == "PROMISE_CONFIRMATION_INPUT_ONLY"
    assert rep["schema"] == "nexus.promise_confirmation_report.v1"
    assert rep["witnessed"] == 2 and rep["promises_total"] == 2


def test_swapped_version_witness_commit_not_containing_merge_is_stale():
    body, ident = setup()
    rep = report(body, [witness_comment("P1", identity=ident)], contains=lambda a, c: False)
    assert row(rep, "P1")["status"] == "STALE"
    assert "WITNESS_COMMIT_NOT_LIVE_MERGE" in row(rep, "P1")["reason_codes"]


def test_swapped_version_edited_promise_statement_is_stale():
    statements = [stmt("P1")]
    body = body_for(statements, {"P1": ("POST_MERGE", "STANDARD")})
    ident = issue_promise_set_identity(_parsed(body))
    edited = body.replace("statement P1", "statement P1 weakened")
    rep = report(edited, [witness_comment("P1", identity=ident)])
    assert row(rep, "P1")["status"] == "STALE"
    assert "PROMISE_STATEMENT_MISMATCH" in row(rep, "P1")["reason_codes"]


def test_swapped_version_changed_promise_set_makes_old_witnesses_stale():
    body_old, ident_old = setup(pids=("P1",), generation=1)
    body_new, _ = setup(pids=("P1", "P2"), generation=2)
    rep = report(body_new, [witness_comment("P1", identity=ident_old)])
    assert row(rep, "P1")["status"] == "STALE"
    assert "WITNESS_PROMISE_SET_MISMATCH" in row(rep, "P1")["reason_codes"]


def test_swapped_version_promise_dropped_after_work_start_is_blocked():
    body_old, _ = setup(pids=("P1", "P2"), generation=1)
    body_new, ident_new = setup(pids=("P1",), generation=2)
    history = [
        {"edited_at": "2026-10-16T00:00:00Z", "body": body_old},
        {"edited_at": "2026-10-17T05:00:00Z", "body": body_new},
    ]
    rep = report(body_new, [witness_comment("P1", identity=ident_new)], history=history)
    assert rep["recommendation"] == "BLOCKED"
    assert "PROMISE_DROPPED_AFTER_WORK_START:P2" in rep["reason_codes"]


def test_swapped_version_extra_field_or_duplicate_key_witness_is_malformed():
    body, ident = setup()
    extra = witness_comment("P1", identity=ident, extra={"approve": True})
    dup = witness_comment("P1", identity=ident, body='{"promise_id":"P1","promise_id":"P1"}')
    rep = report(body, [extra, dup])
    assert rep["malformed_witnesses"] == 2
    assert row(rep, "P1")["status"] == "UNCOVERED"
    assert row(rep, "P1")["witnesses"] == []


def test_partial_coverage_is_provisional_with_third_uncovered():
    body, ident = setup(pids=("P1", "P2", "P3"))
    comments = [witness_comment(p, identity=ident) for p in ("P1", "P2")]
    comments.append(confirmation_comment(ident, {"P1": "ACCEPT", "P2": "ACCEPT", "P3": "ACCEPT"}))
    rep = report(body, comments)
    assert rep["recommendation"] == "PROVISIONAL"
    assert rep["uncovered"] == ["P3"]
    assert rep["witnessed"] == 2


def test_post_merge_promise_with_only_pre_merge_witness_is_insufficient():
    body, ident = setup(phase="POST_MERGE")
    rep = report(body, [witness_comment("P1", phase="PRE_MERGE", commit=HEAD, identity=ident)])
    assert row(rep, "P1")["status"] == "UNCOVERED"
    assert "WITNESS_PHASE_INSUFFICIENT" in row(rep, "P1")["reason_codes"]


def test_high_risk_needs_both_pre_and_post_witnesses():
    body, ident = setup(phase="PRE_MERGE", risk="HIGH")
    pre = witness_comment("P1", phase="PRE_MERGE", commit=HEAD, identity=ident)
    post = witness_comment("P1", phase="POST_MERGE", identity=ident)
    assert row(report(body, [pre]), "P1")["status"] == "UNCOVERED"
    assert row(report(body, [post]), "P1")["status"] == "UNCOVERED"
    assert row(report(body, [pre, post]), "P1")["status"] == "WITNESSED"


def test_confirmer_equal_to_witness_author_is_ignored():
    body, ident = setup()
    comments = [
        witness_comment("P1", identity=ident, by="same"),
        confirmation_comment(ident, {"P1": "ACCEPT"}, confirmer="same"),
    ]
    rep = report(body, comments)
    assert "CONFIRMER_NOT_INDEPENDENT" in row(rep, "P1")["reason_codes"]
    assert rep["recommendation"] == "PROVISIONAL"


@pytest.mark.parametrize("source", ["issue-author", "PR-Author", "author-session"])
def test_confirmer_equal_to_issue_author_pr_author_or_session_is_ignored(source):
    body, ident = setup()
    comments = [
        witness_comment("P1", identity=ident, by="worker"),
        confirmation_comment(ident, {"P1": "ACCEPT"}, confirmer=source.lower()),
    ]
    rep = report(body, comments, authors=["issue-author", "pr-author", "author-session"])
    assert "CONFIRMER_NOT_INDEPENDENT" in row(rep, "P1")["reason_codes"]
    assert rep["recommendation"] == "PROVISIONAL"


def test_emit_blocks_includes_witness_templates():
    text = emit_witness_templates(
        [stmt("P1")], "sha256:" + "1" * 64, {"P1": ("POST_MERGE", "STANDARD")}
    )
    assert "NEXUS_PROMISE_WITNESS_V1" in text
    assert '"entry":"real-entry-P1"' in text.replace(" ", "") or "real-entry-P1" in text
    assert '"promise_id": "P1"' in text and "sha256:" + "1" * 64 in text
    assert "<RESULT>" in text and "<COMMIT>" in text


def test_confirmation_for_old_identity_is_ignored():
    body, ident = setup()
    comments = [
        witness_comment("P1", identity=ident),
        confirmation_comment("sha256:" + "0" * 64, {"P1": "ACCEPT"}),
    ]
    rep = report(body, comments)
    assert rep["recommendation"] == "PROVISIONAL"
    assert rep["ignored_confirmations"]


def test_confirmation_commit_not_live_merge_is_ignored():
    body, ident = setup()
    comments = [
        witness_comment("P1", identity=ident),
        confirmation_comment(ident, {"P1": "ACCEPT"}),
    ]

    def contains(a, c):
        return c != LIVE if c == LIVE else True

    def only_witness_ok(a, c):
        return True

    rep = report(
        body,
        comments[:1] + [confirmation_comment(ident, {"P1": "ACCEPT"}, commit=OTHER)],
        contains=lambda a, c: c != OTHER,
    )
    assert rep["recommendation"] == "PROVISIONAL"
    assert any(
        i["reason"] == "CONFIRMATION_COMMIT_NOT_LIVE_MERGE" for i in rep["ignored_confirmations"]
    )


def test_confirmer_reject_reports_live_failed():
    body, ident = setup()
    comments = [
        witness_comment("P1", identity=ident),
        confirmation_comment(ident, {"P1": "REJECT"}),
    ]
    assert report(body, comments)["recommendation"] == "LIVE_FAILED"


def test_witness_before_merge_is_stale():
    body, ident = setup()
    early = witness_comment("P1", identity=ident, observed="2026-10-17T05:00:00Z")
    rep = report(body, [early])
    assert row(rep, "P1")["status"] == "STALE"
    assert "WITNESS_BEFORE_MERGE" in row(rep, "P1")["reason_codes"]


def test_contains_unknown_is_not_proven():
    body, ident = setup()
    rep = report(body, [witness_comment("P1", identity=ident)], contains=lambda a, c: None)
    assert row(rep, "P1")["status"] == "STALE"


def test_pre_merge_witness_on_other_commit_than_pr_head_is_stale():
    body, ident = setup(phase="PRE_MERGE")
    rep = report(body, [witness_comment("P1", phase="PRE_MERGE", commit=OTHER, identity=ident)])
    assert "WITNESS_COMMIT_NOT_PR_HEAD" in row(rep, "P1")["reason_codes"]
    assert row(rep, "P1")["status"] == "STALE"


def test_unmerged_pr_with_post_merge_requirement_is_blocked():
    body, ident = setup()
    rep = report(body, [], prs=[pr(merged=False)])
    assert rep["recommendation"] == "BLOCKED"
    assert "PR_NOT_MERGED" in rep["reason_codes"]


def test_missing_statement_is_uncovered():
    statements = [stmt("P1")]
    full = emit_promise_blocks(statements, 1, {"P1": ("POST_MERGE", "STANDARD")})
    set_only = "\n".join(full.split("```nexus.issue_promise_statements.v1")[0:1])
    ident = issue_promise_set_identity(_parsed(set_only))
    rep = report(set_only, [witness_comment("P1", identity=ident)])
    assert row(rep, "P1")["status"] == "UNCOVERED"
    assert "PROMISE_STATEMENT_MISSING" in row(rep, "P1")["reason_codes"]


def test_history_unavailable_blocks_verified():
    body, ident = setup()
    comments = [
        witness_comment("P1", identity=ident),
        confirmation_comment(ident, {"P1": "ACCEPT"}),
    ]
    rep = report(body, comments, history=None)
    assert "PROMISE_HISTORY_UNAVAILABLE" in rep["reason_codes"]
    assert rep["recommendation"] == "PROVISIONAL"


def test_set_not_predeclared_blocks_verified():
    body, ident = setup()
    history = [
        {"edited_at": "2026-10-16T00:00:00Z", "body": "no promises yet"},
        {"edited_at": "2026-10-17T05:00:00Z", "body": body},
    ]
    comments = [
        witness_comment("P1", identity=ident),
        confirmation_comment(ident, {"P1": "ACCEPT"}),
    ]
    rep = report(body, comments, history=history)
    assert "PROMISE_SET_NOT_PREDECLARED" in rep["reason_codes"]
    assert rep["recommendation"] == "PROVISIONAL"


def test_no_forbidden_field_names():
    body, ident = setup()
    text = json.dumps(report(body, [witness_comment("P1", identity=ident)]))
    for word in ("approve", "merge_ok", "close", "label"):
        assert f'"{word}' not in text


def test_emit_blocks_round_trip_and_statement_hash_rule():
    import hashlib

    statements = [stmt("P1"), stmt("P2")]
    text = emit_promise_blocks(
        statements, 3, {"P1": ("PRE_MERGE", "HIGH"), "P2": ("POST_MERGE", "STANDARD")}
    )
    parsed = _parsed(text)
    assert parsed["promise_set_generation"] == 3
    by_id = {p["promise_id"]: p for p in parsed["promises"]}
    assert by_id["P1"]["risk"] == "HIGH" and by_id["P2"]["phase"] == "POST_MERGE"
    for s in statements:
        canon = json.dumps(s, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        assert (
            by_id[s["promise_id"]]["statement_sha256"] == hashlib.sha256(canon.encode()).hexdigest()
        )


def test_duplicate_statements_fence_fails_closed():
    body, _ = setup()
    rep = report(body + "\n" + body.split("Issue text")[1], [])
    assert rep["recommendation"] == "BLOCKED"


def test_cli_runs_with_fake_gh_and_reports_not_applicable(tmp_path):
    fake = tmp_path / "fakegh"
    fake.write_text(
        "#!/bin/sh\n"
        'case "$*" in\n'
        '  *graphql*) echo \'{"data":{"repository":{"issue":{"userContentEdits":{"totalCount":0,"nodes":[]}}}}}\' ;;\n'
        '  *comments*) echo "[]" ;;\n'
        '  *pulls/7*) echo \'{"number":7,"head":{"sha":"%s"},"merge_commit_sha":null,"created_at":"%s","merged_at":null}\' ;;\n'
        '  *) echo \'{"body":"plain","number":1}\' ;;\n'
        "esac\n" % (HEAD, PR_CREATED)
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    env = dict(os.environ, NEXUS_GH_BIN=str(fake), PYTHONPATH=_cli_pythonpath())
    out = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/governance/promise_confirmation.py"),
            "--issue",
            "1",
            "--pr",
            "7",
            "--json",
            "--now",
            NOW,
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
    )
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout)["recommendation"] == "NOT_APPLICABLE"


def test_failure_then_pass_without_new_fix_pr_stays_failed():
    body, ident = setup()
    comments = [
        witness_comment(
            "P1", result="ACTUAL_FAILED", identity=ident, observed="2026-10-17T08:00:00Z"
        ),
        witness_comment("P1", result="PASS", identity=ident, observed="2026-10-17T09:00:00Z"),
    ]
    rep = report(body, comments)
    assert row(rep, "P1")["status"] == "FAILED"
    assert rep["recommendation"] == "LIVE_FAILED"


def test_failure_then_fix_pr_merged_then_pass_on_fixed_commit_is_witnessed():
    body, ident = setup()
    fix = {
        "number": 2600,
        "head_sha": "e" * 40,
        "merge_sha": "f" * 40,
        "created_at": "2026-10-17T07:00:00Z",
        "merged_at": "2026-10-17T08:30:00Z",
    }
    comments = [
        witness_comment(
            "P1", result="ACTUAL_FAILED", identity=ident, observed="2026-10-17T08:00:00Z"
        ),
        witness_comment("P1", result="PASS", identity=ident, observed="2026-10-17T09:00:00Z"),
    ]
    rep = report(body, comments, prs=[pr(), fix])
    assert row(rep, "P1")["status"] == "WITNESSED"
    assert "FAILURE_SUPERSEDED_BY_FIX:2600" in row(rep, "P1")["reason_codes"]
    # a PASS that does not contain the fix merge does not supersede
    comments[0] = witness_comment(
        "P1", result="ACTUAL_FAILED", identity=ident, commit=MERGE, observed="2026-10-17T08:00:00Z"
    )
    rep2 = report(
        body, comments, prs=[pr(), fix], contains=lambda a, c: not (a == "f" * 40 and c == LIVE)
    )
    assert row(rep2, "P1")["status"] == "FAILED"


def test_cli_offline_input_needs_no_network(tmp_path):
    body, ident = setup()
    data = {
        "issue_body": body,
        "body_history": [],
        "author_identities": [],
        "comments": [witness_comment("P1", identity=ident)],
        "prs": [pr()],
        "contains": [[MERGE, LIVE, True]],
        "now": NOW,
    }
    path = tmp_path / "in.json"
    path.write_text(json.dumps(data))
    env = dict(os.environ, NEXUS_GH_BIN="/nonexistent/gh", PYTHONPATH=_cli_pythonpath())
    out = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/governance/promise_confirmation.py"),
            "--offline-input",
            str(path),
            "--json",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
    )
    assert out.returncode == 0, out.stderr
    rep = json.loads(out.stdout)
    assert row(rep, "P1")["status"] == "WITNESSED" and rep["recommendation"] == "PROVISIONAL"


# --- review round 1 -------------------------------------------------------------


def test_untrusted_comment_author_witness_is_ignored_and_listed():
    body, ident = setup()
    rando = witness_comment("P1", identity=ident, author="rando", assoc="NONE")
    rep = report(body, [rando])
    assert row(rep, "P1")["status"] == "UNCOVERED"
    assert [b["reason"] for b in rep["ignored_blocks"]] == ["UNTRUSTED_COMMENT_AUTHOR"]


def test_trusted_login_counts_even_without_association():
    body, ident = setup()
    bot = witness_comment("P1", identity=ident, author="agent[bot]", assoc="NONE")
    assert row(report(body, [bot], trusted=["agent[bot]"]), "P1")["status"] == "WITNESSED"


def test_untrusted_confirmation_is_ignored():
    body, ident = setup()
    comments = [
        witness_comment("P1", identity=ident),
        confirmation_comment(ident, {"P1": "ACCEPT"}, author="rando", assoc="CONTRIBUTOR"),
    ]
    rep = report(body, comments)
    assert rep["recommendation"] == "PROVISIONAL"
    assert any(b["reason"] == "UNTRUSTED_COMMENT_AUTHOR" for b in rep["ignored_blocks"])


def test_comment_edited_after_posting_is_ignored():
    body, ident = setup()
    edited = witness_comment("P1", identity=ident, updated="2026-10-17T09:30:00Z")
    rep = report(body, [edited])
    assert row(rep, "P1")["status"] == "UNCOVERED"
    assert [b["reason"] for b in rep["ignored_blocks"]] == ["COMMENT_EDITED_AFTER_POSTING"]


def test_failure_at_old_generation_survives_generation_bump_and_same_commit_pass():
    body1, ident1 = setup(generation=1)
    body2, ident2 = setup(generation=2)
    comments = [
        witness_comment(
            "P1", result="ACTUAL_FAILED", identity=ident1, observed="2026-10-17T08:00:00Z"
        ),
        witness_comment("P1", identity=ident2, observed="2026-10-17T09:00:00Z"),
        confirmation_comment(ident2, {"P1": "ACCEPT"}),
    ]
    rep = report(body2, comments)
    assert row(rep, "P1")["status"] == "FAILED"
    assert rep["recommendation"] == "LIVE_FAILED"


def test_weakening_high_to_standard_after_work_start_blocks_verified():
    old, _ = setup(phase="POST_MERGE", risk="HIGH", generation=1)
    new, ident = setup(phase="POST_MERGE", risk="STANDARD", generation=2)
    history = [
        {"edited_at": "2026-10-16T00:00:00Z", "body": old},
        {"edited_at": "2026-10-17T05:00:00Z", "body": new},
    ]
    comments = [
        witness_comment("P1", identity=ident),
        confirmation_comment(ident, {"P1": "ACCEPT"}),
    ]
    rep = report(new, comments, history=history)
    assert "PROMISE_SET_CHANGED_AFTER_WORK_START" in rep["reason_codes"]
    assert rep["recommendation"] == "PROVISIONAL"


def test_confirmer_who_witnessed_another_promise_is_not_independent():
    body, ident = setup(pids=("P1", "P2"))
    comments = [
        witness_comment("P1", identity=ident, by="A"),
        witness_comment("P2", identity=ident, by="B"),
        confirmation_comment(ident, {"P1": "ACCEPT", "P2": "ACCEPT"}, confirmer="A"),
    ]
    rep = report(body, comments)
    assert "CONFIRMER_NOT_INDEPENDENT" in row(rep, "P2")["reason_codes"]
    assert rep["recommendation"] == "PROVISIONAL"


def test_issue_created_after_work_start_is_not_predeclared():
    body, ident = setup()
    comments = [
        witness_comment("P1", identity=ident),
        confirmation_comment(ident, {"P1": "ACCEPT"}),
    ]
    rep = report(body, comments, issue_created_at="2026-10-17T01:00:00Z")
    assert "PROMISE_SET_NOT_PREDECLARED" in rep["reason_codes"]
    assert rep["recommendation"] == "PROVISIONAL"
    ok = report(body, comments, issue_created_at="2026-10-16T01:00:00Z")
    assert ok["recommendation"] == "VERIFIED"


def test_unmerged_listed_pr_blocks_even_without_post_merge_requirement():
    body, ident = setup(phase="PRE_MERGE", risk="STANDARD")
    rep = report(body, [], prs=[pr(), pr(merged=False, number=2600)])
    assert rep["recommendation"] == "BLOCKED"
    assert "PR_NOT_MERGED" in rep["reason_codes"]


def test_live_for_all_is_false_when_no_listed_pr_is_merged():
    from nexus.services.promise_confirmation import _live_for_all

    assert _live_for_all([pr(merged=False)], LIVE, contains_all) is False
    assert _live_for_all([], LIVE, contains_all) is False


def test_verified_requires_counterexample_checked():
    body, ident = setup()
    comments = [
        witness_comment("P1", identity=ident),
        confirmation_comment(ident, {"P1": "ACCEPT"}, checked=False),
    ]
    assert report(body, comments)["recommendation"] == "PROVISIONAL"


def test_multi_pr_witness_must_contain_every_listed_merge():
    body, ident = setup()
    second = {
        "number": 2600,
        "head_sha": "e" * 40,
        "merge_sha": "f" * 40,
        "created_at": PR_CREATED,
        "merged_at": PR_MERGED,
    }
    rep = report(
        body,
        [witness_comment("P1", identity=ident)],
        prs=[pr(), second],
        contains=lambda a, c: a == MERGE,
    )
    assert row(rep, "P1")["status"] == "STALE"
    assert "WITNESS_COMMIT_NOT_LIVE_MERGE" in row(rep, "P1")["reason_codes"]


def test_future_observed_at_is_malformed():
    body, ident = setup()
    future = witness_comment("P1", identity=ident, observed="2026-10-19T00:00:00Z")
    rep = report(body, [future])
    assert rep["malformed_witnesses"] == 1


def test_superseding_pass_must_be_same_phase():
    body, ident = setup(phase="PRE_MERGE")
    fix = {
        "number": 2600,
        "head_sha": "e" * 40,
        "merge_sha": "f" * 40,
        "created_at": "2026-10-17T07:00:00Z",
        "merged_at": "2026-10-17T08:30:00Z",
    }
    comments = [
        witness_comment(
            "P1", result="ACTUAL_FAILED", identity=ident, observed="2026-10-17T08:00:00Z"
        ),
        witness_comment(
            "P1", phase="PRE_MERGE", commit=HEAD, identity=ident, observed="2026-10-17T09:00:00Z"
        ),
    ]
    rep = report(body, comments, prs=[pr(), fix])
    assert row(rep, "P1")["status"] == "FAILED"


def _run_cli(tmp_path, args, gh_script=None):
    env = dict(os.environ, PYTHONPATH=_cli_pythonpath(), PYTHONWARNINGS="ignore")
    if gh_script is not None:
        fake = tmp_path / "gh"
        fake.write_text(gh_script)
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        env["NEXUS_GH_BIN"] = str(fake)
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/governance/promise_confirmation.py"), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
    )


def test_cli_now_without_z_is_a_clear_error(tmp_path):
    out = _run_cli(
        tmp_path, ["--issue", "1", "--now", "2026-10-18T12:00:00"], "#!/bin/sh\necho '{}'\n"
    )
    assert out.returncode == 2
    assert "Traceback" not in out.stderr and "--now" in out.stderr


def test_cli_gh_failure_is_one_line_error_exit_2(tmp_path):
    out = _run_cli(tmp_path, ["--issue", "1", "--now", NOW], "#!/bin/sh\necho boom >&2\nexit 1\n")
    assert out.returncode == 2
    assert "Traceback" not in out.stderr
    assert len(out.stderr.strip().splitlines()) == 1


def test_never_edited_issue_without_creation_time_cannot_be_verified():
    body, ident = setup(pids=("P1", "P2"))
    comments = [witness_comment(p, identity=ident) for p in ("P1", "P2")]
    comments.append(confirmation_comment(ident, {"P1": "ACCEPT", "P2": "ACCEPT"}))
    rep = report(body, comments, issue_created_at=None)
    assert rep["recommendation"] != "VERIFIED"
    assert "PROMISE_HISTORY_UNAVAILABLE" in rep["reason_codes"]


# --- review round 2 -------------------------------------------------------------

PR2 = {
    "number": 2600,
    "head_sha": "e" * 40,
    "merge_sha": "f" * 40,
    "created_at": "2026-10-17T07:00:00Z",
    "merged_at": "2026-10-17T08:30:00Z",
}


def _m1_only(a, c):
    return c == LIVE or (a == MERGE and c == MERGE)


def test_failure_on_first_merge_survives_second_pr_merge_until_a_fix_pass():
    body, ident = setup()
    comments = [
        witness_comment(
            "P1",
            result="ACTUAL_FAILED",
            commit=MERGE,
            identity=ident,
            observed="2026-10-17T07:00:00Z",
        ),
        witness_comment("P1", identity=ident, observed="2026-10-17T09:00:00Z"),
        confirmation_comment(ident, {"P1": "ACCEPT"}),
    ]
    rep = report(body, comments, prs=[pr(), PR2], contains=_m1_only)
    assert row(rep, "P1")["status"] == "WITNESSED"
    assert "FAILURE_SUPERSEDED_BY_FIX:2600" in row(rep, "P1")["reason_codes"]
    assert rep["recommendation"] == "VERIFIED"


def test_failure_on_first_merge_with_second_pr_merged_and_no_pass_is_failed_not_stale():
    body, ident = setup()
    failure = witness_comment(
        "P1", result="ACTUAL_FAILED", commit=MERGE, identity=ident, observed="2026-10-17T07:00:00Z"
    )
    rep = report(body, [failure], prs=[pr(), PR2], contains=_m1_only)
    assert row(rep, "P1")["status"] == "FAILED"
    assert rep["recommendation"] == "LIVE_FAILED"


def test_failure_on_a_commit_that_never_contained_its_own_merge_does_not_count():
    body, ident = setup()
    failure = witness_comment(
        "P1", result="ACTUAL_FAILED", commit=OTHER, identity=ident, observed="2026-10-17T07:00:00Z"
    )
    rep = report(body, [failure], prs=[pr(), PR2], contains=lambda a, c: False)
    assert row(rep, "P1")["status"] == "STALE"


def test_whitespace_padded_confirmer_is_not_independent():
    body, ident = setup()
    comments = [
        witness_comment("P1", identity=ident, by="Alice"),
        confirmation_comment(ident, {"P1": "ACCEPT"}, confirmer="  alice "),
    ]
    rep = report(body, comments)
    assert "CONFIRMER_NOT_INDEPENDENT" in row(rep, "P1")["reason_codes"]


def test_whitespace_padded_witness_by_is_not_independent_of_confirmer():
    body, ident = setup()
    comments = [
        witness_comment("P1", identity=ident, by=" Alice "),
        confirmation_comment(ident, {"P1": "ACCEPT"}, confirmer="Alice"),
    ]
    assert "CONFIRMER_NOT_INDEPENDENT" in row(report(body, comments), "P1")["reason_codes"]


def test_blank_witness_by_is_malformed():
    body, ident = setup()
    assert (
        report(body, [witness_comment("P1", identity=ident, by="   ")])["malformed_witnesses"] == 1
    )


def test_confirmation_comment_author_in_author_identities_is_ignored_unless_shared_login():
    body, ident = setup()
    comments = [
        witness_comment("P1", identity=ident),
        confirmation_comment(ident, {"P1": "ACCEPT"}, author="Dev-Person"),
    ]
    rep = report(body, comments, authors=["dev-person"])
    assert "CONFIRMER_NOT_INDEPENDENT" in row(rep, "P1")["reason_codes"]
    assert rep["recommendation"] == "PROVISIONAL"
    shared = report(body, comments, authors=["dev-person"], shared=["dev-person"])
    assert shared["recommendation"] == "VERIFIED"


def test_future_dated_confirmation_and_witness_comments_are_ignored():
    body, ident = setup()
    late = "2026-10-19T00:00:00Z"
    wit = witness_comment("P1", identity=ident)
    wit["created_at"] = wit["updated_at"] = late
    conf = confirmation_comment(ident, {"P1": "ACCEPT"}, created=late)
    rep = report(body, [wit, conf])
    assert row(rep, "P1")["status"] == "UNCOVERED"
    assert [b["reason"] for b in rep["ignored_blocks"]] == ["FUTURE_COMMENT", "FUTURE_COMMENT"]


def test_unparseable_pr_created_at_blocks_verified():
    body, ident = setup()
    bad = dict(pr(), created_at="garbage")
    comments = [
        witness_comment("P1", identity=ident),
        confirmation_comment(ident, {"P1": "ACCEPT"}),
    ]
    rep = report(body, comments, prs=[bad])
    assert "PROMISE_HISTORY_UNAVAILABLE" in rep["reason_codes"]
    assert rep["recommendation"] == "PROVISIONAL"


def test_unparseable_issue_created_at_blocks_verified():
    body, ident = setup()
    comments = [
        witness_comment("P1", identity=ident),
        confirmation_comment(ident, {"P1": "ACCEPT"}),
    ]
    rep = report(body, comments, issue_created_at="garbage")
    assert "PROMISE_HISTORY_UNAVAILABLE" in rep["reason_codes"]
    assert rep["recommendation"] == "PROVISIONAL"


def test_unparseable_merged_at_is_treated_as_not_merged():
    body, ident = setup()
    rep = report(body, [], prs=[dict(pr(), merged_at="garbage")])
    assert rep["recommendation"] == "BLOCKED"
    assert "PR_NOT_MERGED" in rep["reason_codes"]


def test_invalid_now_raises_value_error():
    body, _ = setup()
    with pytest.raises(ValueError):
        build_promise_confirmation_report(
            issue_body=body,
            body_history=[],
            comments=[],
            prs=[pr()],
            contains=contains_all,
            now="not-a-time",
            author_identities=[],
        )


def test_comment_without_updated_at_is_ignored_fail_closed():
    body, ident = setup()
    c = witness_comment("P1", identity=ident)
    del c["updated_at"]
    rep = report(body, [c])
    assert row(rep, "P1")["status"] == "UNCOVERED"
    assert [b["reason"] for b in rep["ignored_blocks"]] == ["COMMENT_EDIT_STATE_UNKNOWN"]


def test_cli_offline_invalid_now_is_one_line_exit_2(tmp_path):
    body, _ = setup()
    path = tmp_path / "in.json"
    path.write_text(
        json.dumps({
            "issue_body": body,
            "body_history": [],
            "author_identities": [],
            "comments": [],
            "prs": [pr()],
            "contains": [],
            "now": "bad",
        })
    )
    out = _run_cli(tmp_path, ["--offline-input", str(path), "--json"])
    assert out.returncode == 2 and len(out.stderr.strip().splitlines()) == 1


# --- hardening: author sessions, linked PRs, early NOT_APPLICABLE -----------------


def _verified_inputs():
    body, ident = setup()
    comments = [
        witness_comment("P1", identity=ident),
        confirmation_comment(ident, {"P1": "ACCEPT"}),
    ]
    return body, comments


def test_confirmer_equal_to_author_session_is_not_independent():
    body, ident = setup()
    comments = [
        witness_comment("P1", identity=ident),
        confirmation_comment(ident, {"P1": "ACCEPT"}, confirmer="  Dev-Session "),
    ]
    rep = report(body, comments, author_sessions=["dev-session"])
    assert "CONFIRMER_NOT_INDEPENDENT" in row(rep, "P1")["reason_codes"]
    assert rep["recommendation"] == "PROVISIONAL"


@pytest.mark.parametrize("sessions", [(), ("  ",)])
def test_unknown_author_session_blocks_verified(sessions):
    body, comments = _verified_inputs()
    rep = report(body, comments, author_sessions=sessions)
    assert "AUTHOR_SESSION_UNKNOWN" in rep["reason_codes"]
    assert rep["recommendation"] == "PROVISIONAL"
    assert report(body, comments)["recommendation"] == "VERIFIED"


def test_linked_pr_created_earlier_moves_work_start_back():
    old, _ = setup(pids=("P1", "P2"), generation=1)
    new, ident = setup(pids=("P1",), generation=2)
    history = [
        {"edited_at": "2026-10-16T00:00:00Z", "body": old},
        {"edited_at": "2026-10-17T05:00:00Z", "body": new},
    ]
    late_pr = dict(pr(), created_at="2026-10-17T10:00:00Z", merged_at="2026-10-17T11:00:00Z")
    comments = [witness_comment("P1", identity=ident, observed="2026-10-17T12:00:00Z")]
    without = report(new, comments, prs=[late_pr], history=history)
    assert without["recommendation"] != "BLOCKED"
    linked = report(new, comments, prs=[late_pr], history=history, linked=["2026-10-17T00:00:00Z"])
    assert linked["recommendation"] == "BLOCKED"
    assert "PROMISE_DROPPED_AFTER_WORK_START:P2" in linked["reason_codes"]


@pytest.mark.parametrize("linked", [None, ["garbage"]])
def test_unknown_or_unparseable_linked_prs_block_verified(linked):
    body, comments = _verified_inputs()
    rep = report(body, comments, linked=linked)
    assert "PROMISE_HISTORY_UNAVAILABLE" in rep["reason_codes"]
    assert rep["recommendation"] == "PROVISIONAL"


FAKE_GH = """#!/usr/bin/env python3
import json, sys
routes = json.load(open(__FILE__))
args = sys.argv[1:]
text = " ".join(args)
for key, value in routes.items():
    if (text.endswith(key[1:]) if key.startswith("=") else key in text):
        print(json.dumps(value)); sys.exit(0)
sys.stderr.write("unexpected call: " + text + "\\n"); sys.exit(9)
"""


def _fake_gh(tmp_path, routes):
    data = tmp_path / "routes.json"
    data.write_text(json.dumps(routes))
    fake = tmp_path / "gh"
    fake.write_text(FAKE_GH.replace("__FILE__", repr(str(data))))
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    return fake


def _run_with_fake(tmp_path, routes, extra=()):
    fake = _fake_gh(tmp_path, routes)
    env = dict(
        os.environ, NEXUS_GH_BIN=str(fake), PYTHONPATH=_cli_pythonpath(), PYTHONWARNINGS="ignore"
    )
    return subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/governance/promise_confirmation.py"),
            "--issue",
            "1",
            "--pr",
            "7",
            "--json",
            "--now",
            NOW,
            *extra,
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
    )


def test_cli_not_applicable_fetches_only_the_issue(tmp_path):
    out = _run_with_fake(
        tmp_path, {"=issues/1": {"number": 1, "body": "plain", "user": {"login": "x"}}}
    )
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout)["recommendation"] == "NOT_APPLICABLE"


MARKER = "<!-- NEXUS_AUTHOR_SESSION_V1: sess-a -->"


def _cli_routes(*, pr_body="", timeline=None):
    body, ident = setup()
    rest_comments = []
    for c in (
        witness_comment("P1", identity=ident),
        confirmation_comment(ident, {"P1": "ACCEPT"}, confirmer="sess-a"),
    ):
        rest_comments.append({
            "body": c["body"],
            "created_at": c["created_at"],
            "updated_at": c["updated_at"],
            "author_association": "OWNER",
            "user": {"login": "James3014"},
        })
    timeline = timeline or {
        "pageInfo": {"hasNextPage": False},
        "nodes": [],
    }
    return {
        "timelineItems": {"data": {"repository": {"issue": {"timelineItems": timeline}}}},
        "userContentEdits": {
            "data": {"repository": {"issue": {"userContentEdits": {"totalCount": 0, "nodes": []}}}}
        },
        "issues/1/comments": [rest_comments],
        "=issues/1": {
            "number": 1,
            "body": body,
            "created_at": "2026-01-01T00:00:00Z",
            "user": {"login": "issue-author"},
        },
        "pulls/7": {
            "number": 7,
            "head": {"sha": HEAD},
            "merge_commit_sha": MERGE,
            "created_at": PR_CREATED,
            "merged_at": PR_MERGED,
            "user": {"login": "pr-author"},
            "body": pr_body,
        },
        "compare/": {"status": "ahead"},
    }


def test_cli_reads_author_session_marker_from_pr_body(tmp_path):
    out = _run_with_fake(tmp_path, _cli_routes(pr_body="text\n" + MARKER + "\n"))
    assert out.returncode == 0, out.stderr
    rep = json.loads(out.stdout)
    assert "CONFIRMER_NOT_INDEPENDENT" in row(rep, "P1")["reason_codes"]
    assert rep["recommendation"] == "PROVISIONAL"


def test_cli_without_any_author_session_cannot_verify(tmp_path):
    rep = json.loads(_run_with_fake(tmp_path, _cli_routes()).stdout)
    assert "AUTHOR_SESSION_UNKNOWN" in rep["reason_codes"]
    assert rep["recommendation"] == "PROVISIONAL"


def test_cli_author_session_flag_counts(tmp_path):
    out = _run_with_fake(tmp_path, _cli_routes(), ["--author-session", "sess-a"])
    rep = json.loads(out.stdout)
    assert "AUTHOR_SESSION_UNKNOWN" not in rep["reason_codes"]
    assert "CONFIRMER_NOT_INDEPENDENT" in row(rep, "P1")["reason_codes"]


def test_cli_timeline_pagination_blocks_verified(tmp_path):
    timeline = {"pageInfo": {"hasNextPage": True}, "nodes": []}
    rep = json.loads(_run_with_fake(tmp_path, _cli_routes(timeline=timeline)).stdout)
    assert "PROMISE_HISTORY_UNAVAILABLE" in rep["reason_codes"]


def test_cli_linked_same_repo_pr_marker_and_created_at_are_used(tmp_path):
    node = {
        "source": {
            "__typename": "PullRequest",
            "createdAt": "2026-10-16T00:00:00Z",
            "body": MARKER,
            "repository": {"nameWithOwner": "James3014/Nexus-new"},
        }
    }
    timeline = {"pageInfo": {"hasNextPage": False}, "nodes": [node]}
    rep = json.loads(_run_with_fake(tmp_path, _cli_routes(timeline=timeline)).stdout)
    assert "CONFIRMER_NOT_INDEPENDENT" in row(rep, "P1")["reason_codes"]
    cross = {
        "source": dict(node["source"], repository={"nameWithOwner": "other/repo"}),
    }
    timeline = {"pageInfo": {"hasNextPage": False}, "nodes": [cross]}
    rep = json.loads(_run_with_fake(tmp_path, _cli_routes(timeline=timeline)).stdout)
    assert "AUTHOR_SESSION_UNKNOWN" in rep["reason_codes"]


def test_cli_offline_input_accepts_author_sessions_and_linked_prs(tmp_path):
    body, ident = setup()
    data = {
        "issue_body": body,
        "body_history": [],
        "author_identities": [],
        "author_sessions": ["author-session"],
        "linked_pr_created_at": [],
        "issue_created_at": "2026-01-01T00:00:00Z",
        "comments": [witness_comment("P1", identity=ident)],
        "prs": [pr()],
        "contains": [[MERGE, LIVE, True]],
        "now": NOW,
    }
    path = tmp_path / "in.json"
    path.write_text(json.dumps(data))
    out = _run_cli(tmp_path, ["--offline-input", str(path), "--json"])
    rep = json.loads(out.stdout)
    assert "AUTHOR_SESSION_UNKNOWN" not in rep["reason_codes"]
    assert "PROMISE_HISTORY_UNAVAILABLE" not in rep["reason_codes"]
