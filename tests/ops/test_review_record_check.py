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
    assert "no Claude/Opus ACCEPT/APPROVE verdict" in report["reason"]


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


# -- round 2 regressions (allow-list verdict position, section headers, cap rule) --------

DISPOSITION_TABLE = (
    f"## Review round 1 (head faf38bce9) → repaired in 20d54b496, merged main → head {HEAD}\n\n"
    "**Independent Claude (Opus 5.5): REPAIR_REQUIRED, 14 findings.** "
    "**Gemini 3.8 Flash High: REJECT, 12 findings.**\n\n"
    "| # | Finding | Disposition |\n|---|---|---|\n"
    "| O1 | HIGH: any ACCEPT/APPROVE word counted | **Fixed.** Verdicts are read per clause. |\n"
    "| O3 | MEDIUM: rebuttal too loose | **Fixed.** Needs rebutted plus cap (3 rounds), Gemini. |\n"
    "| G1 | NIT | **Accepted, documented.** |\n\n"
    "Dry run: #2286 → MISSING_CROSS_MODEL (its Codex ACCEPT was at an older head).\n"
)


def test_an_authors_disposition_table_is_not_a_record():
    # #2293's own round-1 comment: names the head, quotes ACCEPT/rebutted/cap/Codex/Gemini.
    record = rrc.classify_record(DISPOSITION_TABLE, HEAD)
    assert record is not None
    assert record["verdict"] is False and record["rebuttal_at_cap"] is False
    assert rrc.evaluate(HEAD, RISKY, [_c(DISPOSITION_TABLE)], [])["status"] == "MISSING_RECORD"


@pytest.mark.parametrize(
    "line",
    [
        "Awaiting Codex ACCEPT@{h}",
        "Need Codex ACCEPT@{h}",
        "Requesting Codex ACCEPT@{h}",
        "Codex should ACCEPT@{h}",
        "Codex will ACCEPT at {h}",
        "Codex: no ACCEPT at {h}",
        "Codex never said ACCEPT at {h}",
        "Codex ACCEPT withheld at {h}",
        "Codex ACCEPT blocked at {h}",
        "Codex: conditional ACCEPT@{h} (fix finding 2 first)",
        "Gemini ACCEPT@{h}?",
        "- [ ] Codex ACCEPT@{h}",
        'coord ready Nexus-new#1 --as x --note "head {h}; Claude ACCEPT@{h}; Codex ACCEPT@{h}"',
        "Codex: ACCEPT at {h} only if X",
        "I don't ACCEPT@{h}",
        "won't ACCEPT@{h}",
        "would ACCEPT@{h} if the test were red first",
        "will ACCEPT@{h} once CI is green",
        "| Codex | ACCEPT@{h} |",
        "> Codex ACCEPT@{h}",
        "Codex r3 REJECT@{h}; cannot ACCEPT",
    ],
)
def test_wishes_conditions_and_quotes_are_not_verdicts(line):
    assert not rrc.is_verdict_line(line.format(h=HEAD))
    body = f"Head {HEAD}\n" + line.format(h=HEAD)
    record = rrc.classify_record(body, HEAD)
    assert record is None or record["cross_model"] is False


@pytest.mark.parametrize(
    "line",
    [
        "Codex @ {h}: **Verdict: ACCEPT.** Not a product bug.",
        "Codex ACCEPT@{h}: P2 is NOT blocking",
        "Codex ACCEPT@{h}: the regression was not reproduced",
        "Codex ACCEPT@{h} (please note the residual nit)",
        "Codex ACCEPT@{h} (earlier REJECT addressed)",
        "Codex r2 ACCEPT@{h} (the race noted before is fixed)",
        "Codex ACCEPT@{h}: holds until main moves",
        "Codex ACCEPT@{h}; no new findings",
        "Codex ACCEPT@{h} (two Low residuals, neither blocking)",
        "Codex: ACCEPT at {h} after the round-2 repair",
        "**Gemini 3.8 Flash High** (approved substitute): **ACCEPT@{h}**.",
        "**Round 2 @ {h}: ACCEPT.** Codex found no new issues.",
        "- **Gemini round 3 @ {h}: ACCEPT.**",
        "Cross-model (agy Gemini 3.8 Flash High, Codex substitute): r5 REJECT 3 → fixed, r6 ACCEPT@{h} 0 new",
    ],
)
def test_real_cross_model_accept_shapes_count(line):
    text = line.format(h=HEAD)
    assert rrc.is_verdict_line(text)
    record = rrc.classify_record(text, HEAD)
    assert record is not None and record["cross_model"] is True


def test_section_header_decides_the_family_not_a_stray_mention():
    claude_header = (
        f"## Review record — Claude (claude-opus-5-5)\n- Head reviewed: `{HEAD}`\n"
        "- Codex: unavailable (out of credits)\n- Verdict: **ACCEPT**\n"
    )
    record = rrc.classify_record(claude_header, HEAD)
    assert record is not None and record["claude"] and not record["cross_model"]
    assert rrc.evaluate(HEAD, RISKY, [_c(claude_header)], [])["status"] == "MISSING_CROSS_MODEL"
    pending = claude_header.replace("unavailable (out of credits)", "adversarial review: pending")
    assert rrc.evaluate(HEAD, RISKY, [_c(pending)], [])["status"] == "MISSING_CROSS_MODEL"
    # A bare ACCEPT whose section has no label line has no family: not a record.
    no_label = f"Head {HEAD}\nCodex timed out.\nACCEPT"
    record = rrc.classify_record(no_label, HEAD)
    assert record is not None and record["verdict"] is False
    stale_codex = f"## Codex\nr3 ACCEPT at {OLD}\nHead: {HEAD}\nGPT run TBD\nACCEPT"
    # The Codex section's ACCEPT is bound to OLD; the trailing bare ACCEPT inherits the
    # Codex header but is a verdict without a reviewer label of its own: it is counted
    # as cross-model only because the header says so (the convention, documented).
    record = rrc.classify_record(stale_codex, HEAD)
    assert record is not None and record["claude"] is False


def test_both_families_in_one_label_read_as_claude():
    both = f"**Claude review (with Codex notes)**: ACCEPT@{HEAD}"
    record = rrc.classify_record(both, HEAD)
    assert record is not None and record["claude"] and not record["cross_model"]


def test_rebuttal_at_cap_needs_a_round_three_reject_in_a_cross_model_section():
    r1 = f"Head {HEAD}\n**Codex**: r1 REJECT; finding rebutted. Cap is 3 rounds.\nClaude ACCEPT@{HEAD}"
    assert rrc.evaluate(HEAD, RISKY, [_c(r1)], [])["status"] == "MISSING_CROSS_MODEL"
    asserted = (
        f"Head {HEAD}\n**Codex review**: author rebutted all findings, cap reached.\n"
        f"Claude ACCEPT@{HEAD}"
    )
    assert rrc.evaluate(HEAD, RISKY, [_c(asserted)], [])["status"] == "MISSING_CROSS_MODEL"
    real = (
        f"Head {HEAD}\n**Codex adversarial review**, 3 rounds:\n- r1 REJECT: fixed.\n"
        "- **r3 REJECT**: early return.\n  - **Rebutted:** verdict unchanged, cap reached.\n"
        f"\n**Claude**: ACCEPT@{HEAD}"
    )
    assert rrc.evaluate(HEAD, RISKY, [_c(real)], [])["status"] == "OK"
    # Same text but the rebuttal lives in a later Claude section: not a cross-model disposition.
    moved = (
        f"Head {HEAD}\n**Codex adversarial review**, 3 rounds:\n- **r3 REJECT**: early return.\n"
        f"\n**Claude**: ACCEPT@{HEAD}\n- Rebutted: the Codex finding is pre-existing, cap reached.\n"
    )
    assert rrc.evaluate(HEAD, RISKY, [_c(moved)], [])["status"] == "MISSING_CROSS_MODEL"


def test_head_label_binding_needs_a_head_word_before_the_sha():
    labelled = f"Head reviewed: `{HEAD}`\n**Claude**: ACCEPT"
    record = rrc.classify_record(labelled, HEAD)
    assert record is not None and record["verdict"] is True
    # The sha appears, but not as a Head label: a bare verdict is unbound.
    unlabelled = f"CI run for {HEAD} is green\n**Claude**: ACCEPT"
    record = rrc.classify_record(unlabelled, HEAD)
    assert record is not None and record["verdict"] is False
    # "ahead of" is not a Head label.
    ahead = f"the branch is ahead of main at {HEAD}\n**Claude**: ACCEPT"
    record = rrc.classify_record(ahead, HEAD)
    assert record is not None and record["verdict"] is False


def test_fenced_code_is_ignored():
    fenced = f"Head {HEAD}\n```\nClaude ACCEPT@{HEAD}\nCodex ACCEPT@{HEAD}\n```\n"
    record = rrc.classify_record(fenced, HEAD)
    assert record is not None and record["verdict"] is False


def test_section_resets_after_a_verdict_line():
    # The Codex header must not carry over into a later bare ACCEPT after Claude's verdict.
    body = f"Head {HEAD}\n**Codex**: r2 ACCEPT at {OLD}\n**Claude**: ACCEPT@{HEAD}\nACCEPT\n"
    record = rrc.classify_record(body, HEAD)
    assert record is not None and record["claude"] is True
    assert record["cross_model"] is False  # the OLD-bound Codex verdict does not count
    # The header family persists through a reviewer's round list (#2288's record shape):
    rounds = (
        f"### Independent Claude review\nReviewer: a separate Claude Opus 5.5 agent.\n"
        f"- **Round 1 @ {OLD}: REJECT.**\n  - HIGH: raised unconditionally.\n"
        f"- **Round 2 @ {OLD}: ACCEPT.** All four closed.\n"
        f"- **Round 3 @ {HEAD}: ACCEPT.**\n"
    )
    record = rrc.classify_record(rounds, HEAD)
    assert record is not None and record["claude"] is True and record["cross_model"] is False


def test_only_github_api_urls_are_ever_opened():
    assert rrc._api_url(f"{rrc.API_ROOT}/repos/o/r/pulls/7") == f"{rrc.API_ROOT}/repos/o/r/pulls/7"
    for bad in ("file:///etc/passwd", "http://api.github.com/x", "https://evil.invalid/x"):
        with pytest.raises(rrc.CheckError):
            rrc._api_url(bad)


def test_negation_anywhere_before_the_token_on_the_line_denies():
    assert not rrc.is_verdict_line(
        f"Codex: We cannot, under any circumstances, ACCEPT this at {HEAD}"
    )
    assert not rrc.is_verdict_line(f"Codex: Do NOT - repeat NOT - ACCEPT this at {HEAD}")
    assert not rrc.is_verdict_line(
        f"Codex r1: REJECT at {HEAD}. ACCEPT will come only after rework."
    )
    # A round list keeps its final ACCEPT: REJECT words deny only inside their own clause.
    assert rrc.is_verdict_line(f"Codex r1 REJECT (fixed), r2 REJECT (fixed), r3 ACCEPT@{HEAD}")


def test_negated_rebuttals_do_not_count():
    for text in (
        f"Head {HEAD}\n**Codex**: round 3: findings not rebutted; cap reached. REJECT.",
        f"Head {HEAD}\n**Codex**: r3 REJECT: 5 bugs found. Author rebutted nothing.",
        f"Head {HEAD}\n**Codex**: r3 REJECT. Nothing was rebutted, no rebuttal accepted.",
    ):
        record = rrc.classify_record(text, HEAD)
        assert record is not None and record["rebuttal_at_cap"] is False, text


def test_a_cross_model_record_alone_is_not_the_independent_review():
    codex_only = rrc.evaluate(HEAD, RISKY, [_c(CODEX_RECORD)], [])
    assert codex_only["status"] == "MISSING_RECORD"
    assert codex_only["cross_model"] is True and codex_only["independent"] is False
    assert rrc.evaluate(HEAD, DOCS, [_c(CODEX_RECORD)], [])["status"] == "MISSING_RECORD"


def test_long_multi_verdict_line_keeps_its_final_accept():
    # #2286's record: one line with three ACCEPTs and a "should-fix" between the first two.
    line = (
        "**Independent review (Claude/Opus, 3 rounds):** ACCEPT at 1e9f3d4ec with one should-fix "
        "(the concurrency comment claimed the controller reads the PR body; it does not) → fixed in "
        f"12f909356, ACCEPT; AGENTS.md trimmed to exactly 12000 bytes in {HEAD} after the required "
        f"impact gate caught test_context_budget → ACCEPT at {HEAD}."
    )
    record = rrc.classify_record(line, HEAD)
    assert record is not None and record["claude"] is True


# -- round 3 (cap) regressions ----------------------------------------------------------


def test_disposition_bullets_are_not_records_and_tokens_are_case_sensitive():
    bullets = (
        f"## Review round 1 (head faf38bce9) → repaired, merged main → head {HEAD}\n\n"
        "- **O14 / G1** NIT: anyone can comment — **Accepted, documented.**\n"
        "- **G12** LOW: APPROVED then CHANGES_REQUESTED — **Fixed.** latest review wins.\n"
        '- **O1** HIGH: any ACCEPT word counted — **Fixed.** ("Verdict: ACCEPT.** …" quoted)\n'
    )
    record = rrc.classify_record(bullets, HEAD)
    assert record is not None and record["verdict"] is False
    assert rrc.evaluate(HEAD, RISKY, [_c(bullets)], [])["status"] == "MISSING_RECORD"
    for prose in (
        f"Head {HEAD}\n- O14: accepted, documented",
        f"Head {HEAD}\n**Claude** review notes: approve the rename later",
        f"Head {HEAD}\n- James: approved the rule change in session.",
        f'Head {HEAD}\nOpus pointed out that a line like "Verdict: ACCEPT" at {HEAD} is parsed.',
        f"Head {HEAD}\n**Claude**: Codex verdict: Accept at {HEAD}",
    ):
        record = rrc.classify_record(prose, HEAD)
        assert record is not None and record["verdict"] is False, prose


def test_a_finding_bullet_naming_a_model_does_not_switch_the_family():
    shape_a = (
        f"## Independent review (Claude Opus 5.5) — head {HEAD}: ACCEPT\n"
        "- **N1:** the Codex prompt template in the skill is stale.\n"
        "**Verdict: ACCEPT**\n"
    )
    record = rrc.classify_record(shape_a, HEAD)
    assert record is not None and record["claude"] and not record["cross_model"]
    assert rrc.evaluate(HEAD, RISKY, [_c(shape_a)], [])["status"] == "MISSING_CROSS_MODEL"
    shape_b = OPUS_RECORD + "- **Note:** Codex review is a separate comment.\n"
    assert rrc.evaluate(HEAD, DOCS, [_c(shape_b)], [])["status"] == "OK"


def test_a_negative_verdict_followed_by_a_conditional_accept_is_not_an_accept():
    for body in (
        f"## Independent review (Claude Opus 5.5), head {HEAD}\n"
        "**Verdict: REJECT** — ACCEPT after the two fixes below.\n",
        f"## Independent review (Claude Opus 5.5), head {HEAD}\n"
        "**Verdict: REPAIR_REQUIRED** — ACCEPT after the two fixes below.\n",
        f"Head {HEAD}\n**Claude** r2 REPAIR_REQUIRED: ACCEPT conditions not met\n",
        f"Head {HEAD}\n**Claude** REJECT: ACCEPT@{HEAD} was premature\n",
    ):
        record = rrc.classify_record(body, HEAD)
        assert record is not None and record["verdict"] is False, body


def test_repair_required_counts_as_a_round_three_reject_for_the_cap_rule():
    body = (
        f"Head {HEAD}\n**Codex adversarial review**, 3 rounds:\n"
        "- r3 REPAIR_REQUIRED (two findings)\n- Both findings rebutted at the cap.\n"
        f"\n**Claude**: ACCEPT@{HEAD}\n"
    )
    assert rrc.evaluate(HEAD, RISKY, [_c(body)], [])["status"] == "OK"


def test_not_a_header_keeps_a_pending_review_label_from_opening_a_section():
    body = (
        f"## Review record — Claude (claude-opus-5-5)\n- Head reviewed: `{HEAD}`\n"
        "- Codex adversarial review: pending\n- Verdict: **ACCEPT**\n"
    )
    record = rrc.classify_record(body, HEAD)
    assert record is not None and record["claude"] and not record["cross_model"]
    body2 = body.replace("- Codex adversarial review: pending", "- **Codex review:** unavailable")
    record = rrc.classify_record(body2, HEAD)
    assert record is not None and record["claude"] and not record["cross_model"]


def test_alone_on_line_position_does_not_apply_to_a_later_clause():
    record = rrc.classify_record(f"Head {HEAD}\n**Claude review**\nfindings fixed. ACCEPT", HEAD)
    assert record is not None and record["verdict"] is False
    record = rrc.classify_record(f"Head {HEAD}\n**Claude review**\nACCEPT", HEAD)
    assert record is not None and record["verdict"] is True


def test_colon_prefix_needs_a_review_label_word():
    # "Codex: fine" is a key-value line, not a reviewer header.
    body = f"Head {HEAD}\n## Claude review\nCodex: fine with it\nVerdict: ACCEPT\n"
    record = rrc.classify_record(body, HEAD)
    assert record is not None and record["claude"] and not record["cross_model"]


def test_a_rebuttal_on_a_verdict_line_in_a_claude_section_is_not_a_cap_disposition():
    body = (
        f"Head {HEAD}\n**Codex**: r3 REJECT: early return.\n"
        f"**Claude**: ACCEPT@{HEAD}; the Codex r3 finding is rebutted, cap reached.\n"
    )
    assert rrc.evaluate(HEAD, RISKY, [_c(body)], [])["status"] == "MISSING_CROSS_MODEL"


def test_hidden_and_code_like_text_is_skipped():
    for body in (
        f"Head {HEAD}\n<!-- Claude: ACCEPT@{HEAD} -->\n",
        f"Head {HEAD}\n~~~\nClaude ACCEPT@{HEAD}\n~~~\n",
        f"Head {HEAD}\n    Claude ACCEPT@{HEAD}\n",
        f"Head {HEAD}\n+ [ ] Claude ACCEPT@{HEAD}\n",
        f"Head {HEAD}\n1. [ ] Claude ACCEPT@{HEAD}\n",
    ):
        record = rrc.classify_record(body, HEAD)
        assert record is None or record["verdict"] is False, body


def test_negative_verdict_label_denies_without_the_after_word():
    body = (
        f"## Independent review (Claude Opus 5.5), head {HEAD}\n"
        "**Verdict: REJECT** — ACCEPT on the next head.\n"
    )
    record = rrc.classify_record(body, HEAD)
    assert record is not None and record["verdict"] is False


def test_a_reject_word_after_the_token_in_its_clause_denies():
    body = f"Head {HEAD}\n**Claude**\n- G12: APPROVED then CHANGES_REQUESTED\n"
    record = rrc.classify_record(body, HEAD)
    assert record is not None and record["verdict"] is False
