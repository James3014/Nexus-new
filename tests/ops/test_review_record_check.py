"""Review record present (#2290): the advisory check and its workflow."""

from __future__ import annotations

import json
import urllib.error
from pathlib import Path

import pytest
import yaml

from scripts.ops import review_record_check as rrc

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "review-record-present.yml"
TOKEN = "tok" + "en-" + "R" * 20
HEAD = "8d70e3ff83eb16c7b1f4af93ae9d87e01d5fe129"
OLD = "1e9f3d4ec0000000000000000000000000000000"
RISKY = [{"filename": "scripts/ops/pr_impact_gate.py", "status": "modified"}]
DOCS = [{"filename": "docs/a.md", "status": "modified"}]

# Real record shapes posted on 2026-10-15 (#2285, #2279, #2263, #2281).
OPUS_RECORD = (
    "## Review record — Claude (claude-opus-5-5), session bundle-C-nightly\n\n"
    f"- Head reviewed: `{HEAD}`\n- Verdict: **ACCEPT**\n- Scope: test-only.\n"
)
SHORT_RECORD = "**Claude review** (Claude Opus 5.5): **ACCEPT@8d70e3ff8**.\n"
CODEX_RECORD = (
    "**Codex adversarial review**, 3 rounds: r1 REJECT (fixed), r2 REJECT (fixed), "
    f"**r3 ACCEPT@{HEAD}**.\n"
)
CODEX_REBUTTAL = (
    f"Review record for the final head {HEAD}.\n\n"
    "**Independent review (Claude/Opus):** ACCEPT at a9f9b0c8e, 18 rounds.\n\n"
    "**Adversarial review (Codex, 17 rounds):** rounds 1-16 fixed. Round 17 (REJECT) is "
    "**rebutted, not fixed**: cap reached.\n"
)
COMBINED_RECORD = (
    "## Review record\n\n**Reviewer:** a separate Claude Opus 5.5 review agent.\n"
    f"**Head:** `{HEAD}`. **Verdict: ACCEPT.** No blocking findings.\n\n"
    "**Codex adversarial review record**\n"
    "**Round 1 @ 09e25e8f5: REJECT, 2 findings** (one fixed, one rebutted).\n"
    f"**Round 2 @ {HEAD}: ACCEPT.** Codex found no new issues.\n"
)


def _c(body: str) -> dict:
    return {"body": body, "user": {"login": "james3014-nexus-agent[bot]"}}


def _fake(pull=None, files=(), comments=(), reviews=(), calls=None):
    pull = pull if pull is not None else {"head": {"sha": HEAD}}

    def fetch(url, token):
        assert token == TOKEN
        if calls is not None:
            calls.append(url)
        if url.endswith("/pulls/7"):
            return pull
        page = int(url.rsplit("page=", 1)[1])
        for key, items in (("files", files), ("comments", comments), ("reviews", reviews)):
            if f"/{key}?" in url:
                return list(items)[(page - 1) * 100 : page * 100]
        raise AssertionError(url)

    return fetch


def _posts(fail=False):
    posted: list[tuple[str, dict]] = []

    def post(url, token, payload):
        assert token == TOKEN
        if fail:
            raise urllib.error.URLError("status api down")
        posted.append((url, payload))
        return {}

    return posted, post


# -- head naming ------------------------------------------------------------------------


def test_names_head_accepts_full_sha_and_prefix_of_nine_or_more():
    assert rrc.names_head(f"ACCEPT at {HEAD}", HEAD)
    assert rrc.names_head("ACCEPT@8d70e3ff8", HEAD)
    assert rrc.names_head(f"ACCEPT at {HEAD.upper()}", HEAD)
    assert not rrc.names_head("ACCEPT@8d70e3ff", HEAD)  # 8 chars: too short
    assert not rrc.names_head(f"ACCEPT at {OLD}", HEAD)
    assert not rrc.names_head("ACCEPT at 8d70e3ff83eb16c7b1f4af93ae9d87e01d5fe12a", HEAD)


def test_head_prefix_inside_a_longer_hex_run_does_not_count():
    # 8d70e3ff83eb... embedded in a 50-hex blob is not a reference to the head.
    assert not rrc.names_head("ff" * 5 + HEAD, HEAD)
    assert not rrc.names_head(HEAD + "ab", HEAD)
    assert rrc.names_head(f"sha256:{HEAD}", HEAD)  # a separator before it is fine


def test_min_prefix_constant_drives_the_regex():
    assert rrc.names_head(HEAD[: rrc.MIN_PREFIX], HEAD)
    assert not rrc.names_head(HEAD[: rrc.MIN_PREFIX - 1], HEAD)


# -- verdict lines -------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "Verdict: **ACCEPT**",
        "r1 REJECT (fixed), r2 REJECT (fixed), **r3 ACCEPT@8d70e3ff8**",
        f"Claude ACCEPT@{HEAD}; Codex review still pending",
        "**r3 ACCEPT@8d70e3ff8**",
        "Independent Opus: APPROVE@8d70e3ff8 (375 tests)",
        "ACCEPT",
    ],
)
def test_positive_verdict_lines(line):
    assert rrc.is_verdict_line(line)


@pytest.mark.parametrize(
    "line",
    [
        f"Verdict: REPAIR_REQUIRED at {HEAD}. Cannot ACCEPT until finding 1 fixed.",
        f"NOT ACCEPTED @ {HEAD}",
        f"Pushed {HEAD}. Please APPROVE.",
        f"Codex r1 REJECT@{HEAD}: two findings, fixing.",
        f"Codex ACCEPT pending at {HEAD}",
        "Codex accepted the rebuttal",  # lowercase prose is not a verdict token
        "ACCEPT is what we need before merge",
    ],
)
def test_negated_or_prose_lines_are_not_verdicts(line):
    assert not rrc.is_verdict_line(line)


# -- record classification ------------------------------------------------------------


def test_classify_record_reads_family_and_head_binding():
    opus = rrc.classify_record(OPUS_RECORD, HEAD)
    assert opus is not None
    assert (opus["verdict"], opus["claude"], opus["cross_model"]) == (True, True, False)
    assert opus["rebuttal_at_cap"] is False
    short = rrc.classify_record(SHORT_RECORD, HEAD)
    assert short is not None and short["claude"] and short["verdict"]
    codex = rrc.classify_record(CODEX_RECORD, HEAD)
    assert codex is not None and codex["cross_model"] and codex["verdict"]
    assert rrc.classify_record("Codex accepted the rebuttal at " + OLD, HEAD) is None


def test_classify_record_combined_comment_credits_both_families():
    both = rrc.classify_record(COMBINED_RECORD, HEAD)
    assert both is not None
    assert both["claude"] is True and both["cross_model"] is True
    assert len(both["verdict_lines"]) == 2


def test_verdict_without_reviewer_identity_is_not_a_record():
    bare = rrc.classify_record("ACCEPT@8d70e3ff8", HEAD)
    assert bare is not None and bare["verdict"] is False
    assert rrc.evaluate(HEAD, DOCS, [_c("ACCEPT@8d70e3ff8")], [])["status"] == "MISSING_RECORD"


def test_verdict_bound_to_another_sha_in_the_same_comment_does_not_count():
    body = f"Head reviewed: {HEAD}\nClaude ACCEPT@{OLD[:9]} (previous round)\n"
    record = rrc.classify_record(body, HEAD)
    # The ACCEPT clause names a different sha; the Head line cannot rebind it.
    assert record is not None and record["verdict"] is False
    body2 = f"Codex r2 ACCEPT@{OLD[:9]}; later pushed {HEAD} without re-review\n"
    record2 = rrc.classify_record(body2, HEAD)
    assert record2 is not None and record2["verdict"] is False


def test_cross_model_mention_in_a_claude_verdict_is_not_a_cross_model_record():
    files = RISKY
    pending = _c(f"Claude ACCEPT@{HEAD}; Codex review still pending")
    assert rrc.evaluate(HEAD, files, [pending], [])["status"] == "MISSING_CROSS_MODEL"
    not_run = _c(f"Claude ACCEPT@{HEAD}. No Codex review was run.")
    assert rrc.evaluate(HEAD, files, [not_run], [])["status"] == "MISSING_CROSS_MODEL"
    # The same two lines as separate records: still Claude-only.
    two = [_c(OPUS_RECORD), _c(f"Codex review pending for {HEAD}")]
    assert rrc.evaluate(HEAD, files, two, [])["status"] == "MISSING_CROSS_MODEL"


def test_rebuttal_at_cap_needs_past_tense_and_a_round_number_or_cap():
    ok = rrc.classify_record(CODEX_REBUTTAL, HEAD)
    assert ok is not None and ok["rebuttal_at_cap"] is True
    promised = rrc.classify_record(f"Codex r3 REJECT@{HEAD}; I will rebut later.", HEAD)
    assert promised is not None and promised["rebuttal_at_cap"] is False
    no_cap = rrc.classify_record(f"Codex r1 REJECT@{HEAD}; finding 2 rebutted.", HEAD)
    assert no_cap is not None and no_cap["rebuttal_at_cap"] is False
    claude_only = rrc.classify_record(f"Claude r3 finding rebutted at {HEAD}, cap reached", HEAD)
    assert claude_only is not None and claude_only["rebuttal_at_cap"] is False
    # #2280's shape: the cap is in the section header, "Rebutted" lines later.
    split = (
        f"## Review record — head `{HEAD}`\n\n"
        "**Claude review** (Claude Opus 5.5): **ACCEPT@8d70e3ff8**.\n\n"
        "**Codex adversarial review** (codex exec, read-only), 3 rounds (cap):\n"
        "- **r1 REJECT.** P1 fixed.\n"
        "- **r3 REJECT:** early return (pre-existing).\n"
        "  - **Rebutted:** Codex confirmed blocking=True is unchanged.\n"
        "  - Cap reached (3 rounds).\n"
    )
    record = rrc.classify_record(split, HEAD)
    assert record is not None and record["rebuttal_at_cap"] is True and record["claude"]
    assert rrc.evaluate(HEAD, RISKY, [_c(split)], [])["status"] == "OK"
    # Same shape, but the rebuttal is in a Claude-only section: not a disposition.
    claude_section = split.replace(
        "**Codex adversarial review** (codex exec, read-only)", "Notes"
    ).replace("Codex confirmed", "confirmed")
    assert rrc.evaluate(HEAD, RISKY, [_c(claude_section)], [])["status"] == "MISSING_CROSS_MODEL"


# -- high-risk paths -----------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/lint.yml",
        ".nexus-core/config.toml",
        "scripts/ops/x.py",
        "scripts/ci/x.sh",
        "pyproject.toml",
        "uv.lock",
        "nexus/orchestrator/governed_integration.py",
        "nexus/orchestrator/self_hosted_task_service.py",
        "nexus/orchestrator/target_integration_lifecycle.py",
        "nexus/governance/x.py",
    ],
)
def test_high_risk_paths_follow_the_codex_review_list(path):
    assert rrc.high_risk_paths([{"filename": path}]) == [path]


def test_renamed_high_risk_path_counts_by_its_old_name():
    moved = [{"filename": "tools/old_gate.py", "previous_filename": "scripts/ops/x.py"}]
    assert rrc.high_risk_paths(moved) == ["scripts/ops/x.py"]
    both = [{"filename": "scripts/ci/a.sh", "previous_filename": "scripts/ops/a.sh"}]
    assert rrc.high_risk_paths(both) == ["scripts/ci/a.sh", "scripts/ops/a.sh"]


@pytest.mark.parametrize("path", ["AGENTS.md", "MUSE_PROTO.md", "ruff.toml", "pyrightconfig.json"])
def test_governance_and_tool_config_files_are_high_risk(path):
    assert rrc.high_risk_paths([{"filename": path}]) == [path]


def test_ordinary_paths_are_not_high_risk():
    files = [{"filename": "tests/ops/test_x.py"}, {"filename": "docs/a.md"}, {"status": "removed"}]
    assert rrc.high_risk_paths(files) == []


# -- evaluate ----------------------------------------------------------------------


def test_evaluate_low_risk_needs_one_record_at_head():
    missing = rrc.evaluate(HEAD, DOCS, [_c("looks good " + OLD)], [])
    assert missing["status"] == "MISSING_RECORD" and missing["independent"] is False
    ok = rrc.evaluate(HEAD, DOCS, [_c(SHORT_RECORD)], [])
    assert ok["status"] == "OK" and ok["high_risk"] is False and ok["records_at_head"] == 1


def test_evaluate_a_comment_naming_the_head_without_a_verdict_is_not_a_record():
    report = rrc.evaluate(HEAD, DOCS, [_c(f"Pushed {HEAD}, CI running")], [])
    assert report["status"] == "MISSING_RECORD" and report["records_at_head"] == 0
    assert "no reviewer+ACCEPT/APPROVE verdict" in report["reason"]


def test_evaluate_record_for_an_older_head_does_not_count_and_is_named():
    old = OPUS_RECORD.replace(HEAD, OLD)
    report = rrc.evaluate(HEAD, DOCS, [_c(old)], [])
    assert report["status"] == "MISSING_RECORD" and report["records_at_head"] == 0
    assert "older head" in report["reason"]


def test_evaluate_high_risk_needs_a_cross_model_record_too():
    only_opus = rrc.evaluate(HEAD, RISKY, [_c(OPUS_RECORD)], [])
    assert only_opus["status"] == "MISSING_CROSS_MODEL"
    assert only_opus["high_risk_paths"] == ["scripts/ops/pr_impact_gate.py"]
    both = rrc.evaluate(HEAD, RISKY, [_c(OPUS_RECORD), _c(CODEX_RECORD)], [])
    assert both["status"] == "OK" and both["cross_model"] is True
    rebutted = rrc.evaluate(HEAD, RISKY, [_c(OPUS_RECORD), _c(CODEX_REBUTTAL)], [])
    assert rebutted["status"] == "OK"
    combined = rrc.evaluate(HEAD, RISKY, [_c(COMBINED_RECORD)], [])
    assert combined["status"] == "OK"
    reject = _c(f"Codex r1 REJECT@{HEAD}: two findings, fixing.")
    assert rrc.evaluate(HEAD, RISKY, [_c(OPUS_RECORD), reject], [])["status"] == (
        "MISSING_CROSS_MODEL"
    )


def test_evaluate_counts_a_submitted_approval_at_head():
    reviews = [{"state": "APPROVED", "commit_id": HEAD, "user": {"login": "r1"}}]
    assert rrc.evaluate(HEAD, DOCS, [], reviews)["status"] == "OK"
    stale = [{"state": "APPROVED", "commit_id": OLD}, {"state": "COMMENTED", "commit_id": HEAD}]
    assert rrc.evaluate(HEAD, DOCS, [], stale)["status"] == "MISSING_RECORD"


def test_a_later_changes_requested_by_the_same_reviewer_supersedes_the_approval():
    reviews = [
        {"state": "APPROVED", "commit_id": HEAD, "user": {"login": "r1"}},
        {"state": "CHANGES_REQUESTED", "commit_id": HEAD, "user": {"login": "r1"}},
    ]
    assert rrc.approved_reviews_at_head(reviews, HEAD) == 0
    assert rrc.evaluate(HEAD, DOCS, [], reviews)["status"] == "MISSING_RECORD"
    # A COMMENTED review after the approval does not withdraw it; another reviewer's
    # CHANGES_REQUESTED does not cancel r1's approval either.
    reviews2 = [
        {"state": "APPROVED", "commit_id": HEAD, "user": {"login": "r1"}},
        {"state": "COMMENTED", "commit_id": HEAD, "user": {"login": "r1"}},
        {"state": "CHANGES_REQUESTED", "commit_id": HEAD, "user": {"login": "r2"}},
    ]
    assert rrc.approved_reviews_at_head(reviews2, HEAD) == 1
    dismissed = [
        {"state": "APPROVED", "commit_id": HEAD, "user": {"login": "r1"}},
        {"state": "DISMISSED", "commit_id": HEAD, "user": {"login": "r1"}},
    ]
    assert rrc.approved_reviews_at_head(dismissed, HEAD) == 0


# -- run: API, status publication, exit codes -----------------------------------------


def test_run_publishes_success_status_and_writes_report(tmp_path, capsys):
    posted, post = _posts()
    out = tmp_path / "report.json"
    rc = rrc.run(
        "o/r",
        7,
        TOKEN,
        _fake(files=DOCS, comments=[_c(OPUS_RECORD)]),
        post,
        target_url="https://example.invalid/run/1",
        output=str(out),
    )
    assert rc == 0
    ((url, payload),) = posted
    assert url.endswith(f"/repos/o/r/statuses/{HEAD}")
    assert payload["state"] == "success" and payload["context"] == rrc.STATUS_CONTEXT
    assert payload["target_url"] == "https://example.invalid/run/1"
    assert len(payload["description"]) <= rrc.MAX_DESCRIPTION
    assert json.loads(out.read_text())["status"] == "OK"
    assert "review-record-check: OK" in capsys.readouterr().out


def test_run_missing_record_fails_and_publishes_failure(capsys):
    posted, post = _posts()
    rc = rrc.run("o/r", 7, TOKEN, _fake(files=DOCS), post)
    assert rc == 1
    assert posted[0][1]["state"] == "failure"
    assert "MISSING_RECORD" in capsys.readouterr().out


def test_run_no_fail_keeps_exit_zero_but_still_publishes_failure():
    posted, post = _posts()
    rc = rrc.run("o/r", 7, TOKEN, _fake(files=DOCS), post, fail_on_missing=False)
    assert rc == 0 and posted[0][1]["state"] == "failure"


def test_run_api_error_fails_closed_even_with_no_fail_and_publishes_nothing(capsys):
    posted, post = _posts()

    def broken(url, token):
        raise urllib.error.URLError("down")

    assert rrc.run("o/r", 7, TOKEN, broken, post, fail_on_missing=False) == 1
    assert posted == []
    assert "ERROR" in capsys.readouterr().out


def test_run_error_after_head_is_known_publishes_an_error_status():
    posted, post = _posts()

    def fetch(url, token):
        if url.endswith("/pulls/7"):
            return {"head": {"sha": HEAD}}
        raise OSError("files endpoint down")

    assert rrc.run("o/r", 7, TOKEN, fetch, post, fail_on_missing=False) == 1
    assert posted[0][1]["state"] == "error"


def test_run_unexpected_exception_types_still_fail_closed():
    posted, post = _posts()
    weird = _fake(pull={"head": "not-a-dict"})
    assert rrc.run("o/r", 7, TOKEN, weird, post, fail_on_missing=False) == 1
    assert posted == []

    def attribute_error(url, token):
        raise AttributeError("boom")

    assert rrc.run("o/r", 7, TOKEN, attribute_error, post, fail_on_missing=False) == 1


def test_run_fails_closed_when_head_is_not_a_sha():
    posted, post = _posts()
    assert rrc.run("o/r", 7, TOKEN, _fake(pull={"head": {"sha": "main"}}), post) == 1
    assert posted == []


def test_run_failed_status_publication_is_a_failed_run(capsys):
    _posted, post = _posts(fail=True)
    rc = rrc.run("o/r", 7, TOKEN, _fake(files=DOCS, comments=[_c(OPUS_RECORD)]), post)
    assert rc == 1
    assert "could not publish" in capsys.readouterr().out


def test_run_paginates_comments():
    posted, post = _posts()
    calls: list[str] = []
    comments = [_c("noise")] * 100 + [_c(OPUS_RECORD)]
    fetch = _fake(files=DOCS, comments=comments, calls=calls)
    assert rrc.run("o/r", 7, TOKEN, fetch, post) == 0
    assert any("/comments?per_page=100&page=2" in c for c in calls)


# -- log safety --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "forbidden"),
    [
        ("::error::x", "::"),
        ("   ::warning::x", "::"),
        ("path\n::error::y", "\n"),
        ("path\r::error::y", "\r"),
        ("path ::error::y", " "),
        ("##[command]y", "##["),
        ("a##[b##[c", "##["),
    ],
)
def test_log_safe_neutralizes_workflow_commands(raw, forbidden):
    safe = rrc._log_safe(raw)
    assert not safe.lstrip().startswith("::")
    assert "##[" not in safe
    assert forbidden not in safe or forbidden == "::"
    assert "\n" not in safe and "\r" not in safe


def test_printed_lines_and_description_cannot_carry_workflow_commands(capsys):
    posted, post = _posts()
    hostile = [{"filename": "scripts/ops/::error::x\n##[command]y.py", "status": "modified"}]
    rrc.run("o/r", 7, TOKEN, _fake(files=hostile), post)
    out = capsys.readouterr().out
    assert "scripts/ops/" in out  # the hostile path is printed (high-risk line)
    for line in out.splitlines():
        assert not line.lstrip().startswith("::")
        assert "##[" not in line
    assert "##[" not in posted[0][1]["description"]
    assert "\n" not in posted[0][1]["description"]


def test_description_is_capped():
    report = {"status": "MISSING_RECORD", "reason": "x" * 500}
    assert len(rrc._description(report)) == rrc.MAX_DESCRIPTION


# -- workflow shape --------------------------------------------------------------------


def test_workflow_never_checks_out_pr_code_and_runs_the_script_isolated():
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    triggers = doc.get("on", doc.get(True))
    assert triggers["pull_request_target"]["types"] == ["opened", "synchronize", "reopened"]
    assert triggers["issue_comment"]["types"] == ["created", "edited", "deleted"]
    # pull_request_review runs the PR's own copy of the workflow: never used here.
    assert "pull_request_review" not in triggers and "pull_request" not in triggers
    assert doc["permissions"] == {}
    assert doc["concurrency"] == {
        "group": (
            "review-record-${{ github.event.pull_request.number || "
            "github.event.issue.number || github.run_id }}"
        ),
        "cancel-in-progress": True,
    }
    (job,) = doc["jobs"].values()
    assert job["name"] != rrc.STATUS_CONTEXT  # the status is the signal, not the job
    assert job["permissions"] == {
        "contents": "read",
        "issues": "read",
        "pull-requests": "read",
        "statuses": "write",
    }
    assert "github.event.issue.pull_request" in job["if"]
    checkout, check = job["steps"]
    assert checkout["with"]["ref"] == "${{ github.event.repository.default_branch }}"
    assert checkout["with"]["persist-credentials"] is False
    assert "python3 -I scripts/ops/review_record_check.py" in check["run"]
    assert "--no-fail" in check["run"]
    assert "PYTHONPATH" not in check.get("env", {})
    assert "${{" not in check["run"]  # no PR-controlled text interpolated into the shell
