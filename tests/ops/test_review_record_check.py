"""Review record present (#2290): the advisory check and its workflow."""

from __future__ import annotations

import json
import time
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
    assert (rrc.classify_record(claude_section, HEAD) or {}).get("rebuttal_at_cap") is False
    # Since #2992 the unresolved "r3 REJECT" in the Claude section also withdraws the
    # Claude ACCEPT above it, so the record is missing before the cross-model check.
    assert rrc.evaluate(HEAD, RISKY, [_c(claude_section)], [])["status"] == "MISSING_RECORD"


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


@pytest.mark.parametrize(
    "path",
    [
        "nexus/orchestrator/self_hosted_task_service.py",
        "nexus/orchestrator/self_hosted_task_service_parts/__init__.py",
        "nexus/orchestrator/self_hosted_task_service_parts/sub/mixin.py",
        "nexus/orchestrator/unified_mcp_gateway.py",
        "nexus/orchestrator/unified_mcp_gateway_parts/__init__.py",
        "nexus/orchestrator/unified_mcp_gateway_parts/assist_jobs.py",
    ],
)
def test_big_file_split_surfaces_are_high_risk(path):
    assert rrc.high_risk_paths([{"filename": path}]) == [path]


@pytest.mark.parametrize(
    "path",
    [
        "nexus/orchestrator/unified_mcp_gateway_helpers.py",
        "nexus/orchestrator/self_hosted_task_service_v2.py",
        "nexus/orchestrator/unified_mcp_gateway_parts_old/x.py",
        "nexus/orchestrator/self_hosted_task_service_parts.py",
        "nexus/orchestrator/unified_mcp_gateway_parts",
        "tests/orchestrator/unified_mcp_gateway_parts/test_x.py",
    ],
)
def test_split_surface_near_misses_are_not_high_risk(path):
    # Segment-exact by construction: the module entries end in ".py" and the package
    # entries end in "/", so startswith() cannot reach sibling names.
    assert rrc.high_risk_paths([{"filename": path}]) == []


def test_moving_code_out_of_a_split_surface_counts_by_its_old_name():
    moved = [
        {
            "filename": "nexus/orchestrator/gateway_helpers.py",
            "previous_filename": "nexus/orchestrator/unified_mcp_gateway_parts/helpers.py",
        }
    ]
    assert rrc.high_risk_paths(moved) == ["nexus/orchestrator/unified_mcp_gateway_parts/helpers.py"]


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


# -- Gemini round 3 ---------------------------------------------------------------------


def test_nested_list_items_are_not_code():
    body = (
        "## Review record — Claude (claude-opus-5-5)\n"
        f"- Head reviewed: `{HEAD}`\n    - Verdict: **ACCEPT**\n"
    )
    record = rrc.classify_record(body, HEAD)
    assert record is not None and record["verdict"] is True and record["claude"]
    record = rrc.classify_record(f"Head {HEAD}\n    Claude ACCEPT@{HEAD}\n", HEAD)
    assert record is not None and record["verdict"] is False  # indented code stays skipped


def test_possessive_apostrophes_are_not_quotes_but_quoted_tokens_are():
    for line in (f"Claude's verdict: ACCEPT@{HEAD}", f"Opus's review: ACCEPT@{HEAD}"):
        assert rrc.is_verdict_line(line), line
    for line in (f"Claude: Verdict: 'ACCEPT' at {HEAD}", f'Claude: Verdict: "ACCEPT" at {HEAD}'):
        assert not rrc.is_verdict_line(line), line


def test_a_round_marker_restarts_the_negation_window():
    line = f"Claude: r1 ACCEPT at {OLD} with one should-fix, r2 ACCEPT at {HEAD}"
    record = rrc.classify_record(line, HEAD)
    assert record is not None and record["verdict"] is True
    assert not rrc.is_verdict_line(f"Claude: We cannot, under any circumstances, ACCEPT at {HEAD}")


def test_hyphenated_non_accept_is_not_a_verdict():
    for line in (f"Claude: non-ACCEPT at {HEAD}", f"Claude: un-ACCEPT at {HEAD}"):
        assert not rrc.is_verdict_line(line), line
    assert rrc.is_verdict_line(f"Claude - ACCEPT at {HEAD}")


def test_withdrawals_later_on_the_line_deny_an_unbound_verdict():
    for line in (
        f"Claude: ACCEPT, pending CI at {HEAD}",
        f"Claude: ACCEPT, only if tests pass at {HEAD}",
        f"Claude: ACCEPT; cannot merge {HEAD}",
        f"Claude: ACCEPT, withheld until review at {HEAD}",
    ):
        assert not rrc.is_verdict_line(line), line
    assert rrc.is_verdict_line(f"Claude ACCEPT@{HEAD}; Codex review still pending")


def test_a_later_reject_at_the_head_withdraws_a_historical_rebuttal():
    body = (
        f"Head reviewed: {HEAD}\nClaude: ACCEPT@{HEAD}\n## Codex\n"
        f"- r3 REJECT at {OLD}: rebutted\n"
        f"- r4 REJECT at {HEAD}: critical security issue, DO NOT MERGE!\n"
    )
    assert rrc.evaluate(HEAD, RISKY, [_c(body)], [])["status"] == "MISSING_CROSS_MODEL"


def test_rebutted_but_it_was_not_is_not_a_rebuttal():
    body = (
        f"Head reviewed: {HEAD}\nClaude: ACCEPT@{HEAD}\n## Codex\n"
        "- r3 REJECT: author claims finding was rebutted, but it was not.\n"
    )
    record = rrc.classify_record(body, HEAD)
    assert record is not None and record["rebuttal_at_cap"] is False


def test_a_neutral_heading_closes_the_reviewer_section():
    body = f"Head reviewed: {HEAD}\n## Codex Review\n- r1 REJECT\n## Author Response\n- Verdict: ACCEPT\n"
    record = rrc.classify_record(body, HEAD)
    assert record is not None and record["verdict"] is False


def test_head_label_binds_through_verbose_phrasing():
    body = f"Head commit for this round is {HEAD}\n**Claude**: ACCEPT"
    record = rrc.classify_record(body, HEAD)
    assert record is not None and record["verdict"] is True


def test_an_authors_self_check_is_not_a_review():
    for body in (
        f"Author (Claude) self-check: ACCEPT@{HEAD}",
        f"Author (Opus 5.5) status at head {HEAD}: ACCEPT",
    ):
        record = rrc.classify_record(body, HEAD)
        assert record is not None and record["verdict"] is False, body


def test_a_sub_heading_inside_a_review_record_keeps_the_section():
    body = (
        "## Review record — Claude (claude-opus-5-5)\n"
        f"- Head reviewed: `{HEAD}`\n### Findings\n- none blocking\n### Verdict\n**ACCEPT**\n"
    )
    record = rrc.classify_record(body, HEAD)
    assert record is not None and record["verdict"] is True and record["claude"]
    same_level = body.replace("### Verdict", "## Verdict")
    record = rrc.classify_record(same_level, HEAD)
    assert record is not None and record["verdict"] is False


def test_a_later_word_only_withdraws_a_verdict_when_the_line_borrows_a_sha():
    for body in (
        f"Head reviewed: {HEAD}\n**Claude**\n- Verdict: **ACCEPT** — nothing blocked\n",
        f"Head reviewed: {HEAD}\n**Claude**\n**Verdict: ACCEPT.** One nit is pending a follow-up.\n",
        f"Head reviewed: {HEAD}\n**Claude**\nVerdict: ACCEPT. I cannot reproduce the old failure.\n",
    ):
        record = rrc.classify_record(body, HEAD)
        assert record is not None and record["verdict"] is True, body


def test_a_parenthetical_aside_does_not_disable_a_reviewer_header():
    # #2296's record (#2299): the Gemini header carries a "Codex ... out of credits" aside.
    # Its round-2 sha was that PR's head; an all-digit sha of another commit binds nothing.
    body = (
        f"## Review record (coordinator workspace-c6), head {HEAD}\n\n"
        "**Independent Claude review (Opus 5.5, separate agent)**\n"
        f"- Round 2 @{HEAD[:7]}: **ACCEPT.** Mutants killed.\n\n"
        "**Cross-model review (agy Gemini 3.8 Flash High, Owner-approved Codex substitute; "
        'Codex: "Your workspace is out of credits")**\n'
        "- Round 1 @9154965: REJECT. F-01 rebutted.\n"
        f"- Round 2 @{HEAD[:7]}: **ACCEPT.** Rebuttal accepted; F-03 judged fixed.\n"
    )
    record = rrc.classify_record(body, HEAD)
    assert record is not None and record["claude"] is True and record["cross_model"] is True
    assert rrc.evaluate(HEAD, RISKY, [_c(body)], [])["status"] == "OK"
    # The not-run forms outside parentheses still open no section.
    pending = body.replace(
        "**Cross-model review (agy Gemini 3.8 Flash High, Owner-approved Codex substitute; "
        'Codex: "Your workspace is out of credits")**',
        "**Cross-model review: pending (Codex out of credits)**",
    )
    assert rrc.evaluate(HEAD, RISKY, [_c(pending)], [])["status"] == "MISSING_CROSS_MODEL"


def test_a_header_whose_parenthetical_starts_with_a_not_run_word_opens_no_section():
    a1 = (
        f"## Review record, head {HEAD}\n**Independent Claude review (Opus 5.5)**\n"
        f"- Round 2: ACCEPT @ {HEAD}\n\n**Codex adversarial review (pending)**\n\n"
        f"Overall verdict: ACCEPT @ {HEAD}\n"
    )
    assert rrc.evaluate(HEAD, RISKY, [_c(a1)], [])["status"] == "MISSING_CROSS_MODEL"
    a3 = f"Head reviewed: {HEAD}\n**Claude review**: ACCEPT\n**Codex review** (skipped)\nVerdict: ACCEPT @ {HEAD}\n"
    assert rrc.evaluate(HEAD, RISKY, [_c(a3)], [])["status"] == "MISSING_CROSS_MODEL"
    # An aside that merely mentions Codex's state keeps the Gemini header alive.
    ok = f"Head reviewed: {HEAD}\n**Claude review**: ACCEPT\n**Gemini review (Codex pending)**\nVerdict: ACCEPT @ {HEAD}\n"
    assert rrc.evaluate(HEAD, RISKY, [_c(ok)], [])["status"] == "OK"


@pytest.mark.parametrize(
    "header",
    [
        "**Codex review (still pending)**",
        "**Codex review (gpt-5.6, not run)**",
        "**Codex review (currently unavailable)**",
        "**Codex review (run skipped)**",
        '**Codex review ("pending")**',
    ],
)
def test_a_not_run_word_anywhere_in_the_headers_own_parenthetical_opens_no_section(header):
    body = f"Head reviewed: {HEAD}\n**Claude review**: ACCEPT\n{header}\nVerdict: ACCEPT @ {HEAD}\n"
    assert rrc.evaluate(HEAD, RISKY, [_c(body)], [])["status"] == "MISSING_CROSS_MODEL"


# -- #2308: merge-only delta, widened not-run words, same-line not-run header ----------------

R_OLD = "1e9f3d4ec" + "0" * 31  # the reviewed head
M_HEAD = HEAD  # the head after the author merged main
MAIN_PARENT = "a" * 40  # a commit already on main
FOREIGN = "b" * 40  # a non-merge commit that is not on main
SPINE_MID = "c" * 40


def _commit(sha, *parents):
    return {"sha": sha, "parents": [{"sha": p} for p in parents]}


def _compare_payload(commits, files=(), status="ahead", behind_by=0, **extra):
    payload = {
        "status": status,
        "ahead_by": len(commits),
        "behind_by": behind_by,
        "total_commits": len(commits),
        "commits": list(commits),
        "files": list(files),
    }
    payload.update(extra)
    return payload


def _delta_fetch(
    *,
    commits=None,
    main_status="behind",
    main_ahead=0,
    changed=({"filename": "elsewhere/x.py"},),
    pr_at_old=({"filename": "docs/a.md"},),
    side_changed=({"filename": "main/other.py"},),
    api_error=False,
    compare_extra=None,
    pr_files=DOCS,
    comments=None,
    reviews=(),
):
    commits = commits if commits is not None else [_commit(M_HEAD, R_OLD, MAIN_PARENT)]
    comments = comments if comments is not None else [_c(OPUS_RECORD.replace(HEAD, R_OLD[:12]))]
    delta = _compare_payload(commits, changed, **(compare_extra or {}))
    base_fetch = _fake(files=pr_files, comments=comments, reviews=reviews)

    def fetch(url, token):
        if "/compare/" in url:
            if api_error:
                raise urllib.error.URLError("compare down")
            spec = url.split("/compare/", 1)[1].split("?", 1)[0]
            left, right = spec.split("...")
            if left == R_OLD and right == M_HEAD:
                return delta
            if left == "main":
                return {"status": main_status, "ahead_by": main_ahead, "behind_by": 3}
            if left == R_OLD:  # what the base gained on a side parent since the reviewed head
                return _compare_payload([], side_changed)
            raise AssertionError(url)
        if "/commits/" in url:
            return {"sha": R_OLD}
        return base_fetch(url, token)

    return fetch


def _delta_fetch_with_old_pr_files(pr_at_old, **kw):
    inner = _delta_fetch(**kw)

    def fetch(url, token):
        if "/compare/main...%s" % R_OLD in url:
            return _compare_payload([], pr_at_old)
        return inner(url, token)

    return fetch


def _run_delta(fetch):
    posted, post = _posts()
    rc = rrc.run("o/r", 7, TOKEN, fetch, post)
    return rc, posted[0][1]


def _pull_main():
    return {"head": {"sha": HEAD}, "base": {"ref": "main"}}


def _delta_case(**kw):
    kw.setdefault("pr_at_old", ({"filename": "docs/a.md"},))
    fetch = _delta_fetch_with_old_pr_files(kw.pop("pr_at_old"), **kw)

    def wrapped(url, token):
        if url.endswith("/pulls/7"):
            return _pull_main()
        return fetch(url, token)

    return _run_delta(wrapped)


def test_merge_only_delta_accepts_the_record_at_the_reviewed_head():
    rc, status = _delta_case()
    assert rc == 0 and status["state"] == "success"
    assert f"record at {R_OLD[:9]}, merge-only delta verified" in status["description"]


def test_merge_only_delta_rejects_a_changed_pr_path():
    rc, status = _delta_case(changed=({"filename": "docs/a.md"},))
    assert rc == 1 and status["state"] == "failure" and "older head only" in status["description"]


def test_merge_only_delta_rejects_a_renamed_pr_path():
    changed = ({"filename": "elsewhere/new.py", "previous_filename": "docs/a.md"},)
    assert _delta_case(changed=changed)[0] == 1


def test_merge_only_delta_rejects_a_path_the_pr_touched_at_the_reviewed_head():
    # the merge reverted a file the review covered: it is gone from the PR list now
    rc, _ = _delta_case(
        changed=({"filename": "scripts/gone.py"},), pr_at_old=({"filename": "scripts/gone.py"},)
    )
    assert rc == 1


def test_merge_only_delta_rejects_a_non_merge_commit_on_the_spine():
    assert _delta_case(commits=[_commit(M_HEAD, R_OLD)])[0] == 1


def test_merge_only_delta_rejects_a_foreign_commit_not_on_main():
    commits = [_commit(M_HEAD, SPINE_MID, MAIN_PARENT), _commit(SPINE_MID, R_OLD, FOREIGN)]
    # the first side parent (main) is on main, FOREIGN is not
    inner = _delta_fetch(commits=commits)

    def fetch(url, token):
        if url.endswith("/pulls/7"):
            return _pull_main()
        if f"/compare/main...{FOREIGN}" in url:
            return {"status": "ahead", "ahead_by": 1, "behind_by": 0}
        if f"/compare/main...{R_OLD}" in url:
            return _compare_payload([], [{"filename": "docs/a.md"}])
        return inner(url, token)

    assert _run_delta(fetch)[0] == 1


def test_merge_only_delta_accepts_a_chain_of_merges():
    commits = [_commit(M_HEAD, SPINE_MID, MAIN_PARENT), _commit(SPINE_MID, R_OLD, "d" * 40)]
    rc, status = _delta_case(commits=commits)
    assert rc == 0 and "merge-only delta verified" in status["description"]


@pytest.mark.parametrize(
    "extra",
    [
        {"status": "diverged"},
        {"status": "behind"},
        {"behind_by": 1},
        {"ahead_by": 7},
        {"total_commits": 250},
        {"total_commits": "2"},
    ],
)
def test_merge_only_delta_rejects_a_non_ahead_or_truncated_compare(extra):
    assert _delta_case(compare_extra=extra)[0] == 1


def test_merge_only_delta_rejects_a_truncated_file_list():
    files = tuple({"filename": f"f{i}.py"} for i in range(300))
    assert _delta_case(changed=files)[0] == 1


def test_merge_only_delta_rejects_when_the_compare_api_errors():
    rc, status = _delta_case(api_error=True)
    assert rc == 1 and "older head only" in status["description"]


def test_merge_only_delta_rejects_a_side_parent_not_on_main():
    assert _delta_case(main_status="ahead", main_ahead=2)[0] == 1
    assert _delta_case(main_status="diverged")[0] == 1


def test_merge_only_delta_never_runs_when_the_head_is_already_recorded():
    calls: list[str] = []
    fetch = _fake(files=DOCS, comments=[_c(OPUS_RECORD)], calls=calls)
    assert rrc.run("o/r", 7, TOKEN, fetch, _posts()[1]) == 0
    assert not any("/compare/" in u for u in calls)


def test_merge_only_delta_holds_for_the_cross_model_requirement_too():
    risky_files = RISKY
    claude_old = _c(OPUS_RECORD.replace(HEAD, R_OLD[:12]))
    codex_old = _c(CODEX_RECORD.replace(HEAD, R_OLD))
    ok = _delta_case(
        pr_files=risky_files, pr_at_old=RISKY, comments=[claude_old, codex_old], changed=()
    )
    assert ok[0] == 0 and "merge-only delta verified" in ok[1]["description"]
    # the same Codex record without a verified delta does not count
    bad = _delta_case(
        pr_files=risky_files,
        comments=[claude_old, codex_old],
        changed=({"filename": "scripts/ops/pr_impact_gate.py"},),
    )
    assert bad[0] == 1


def test_evaluate_uses_a_delta_verified_head_only_when_told_to():
    old = _c(OPUS_RECORD.replace(HEAD, R_OLD))
    assert rrc.evaluate(HEAD, DOCS, [old], [])["status"] == "MISSING_RECORD"
    report = rrc.evaluate(HEAD, DOCS, [old], [], (R_OLD,))
    assert report["status"] == "OK" and report["delta_verified_heads"] == [R_OLD]


def test_delta_verified_record_does_not_rescue_a_missing_cross_model_requirement():
    old = _c(OPUS_RECORD.replace(HEAD, R_OLD))
    assert rrc.evaluate(HEAD, RISKY, [old], [], (R_OLD,))["status"] == "MISSING_CROSS_MODEL"


@pytest.mark.parametrize(
    "header",
    [
        "**Codex review (awaiting)**",
        "**Codex review (in progress)**",
        "**Codex review (queued)**",
        "**Codex review (running)**",
        "**Codex review awaiting**",
        "**Codex review in progress**",
        "**Codex review queued**",
        "**Codex review running**",
        "Codex: queued",
        "Codex adversarial review: awaiting",
    ],
)
def test_not_run_words_do_not_open_a_cross_model_section(header):
    assert rrc._label_family(header) is None
    body = f"## Review record — Claude Opus, head {HEAD}\nVerdict: ACCEPT\n\n{header}\nACCEPT\n"
    record = rrc.classify_record(body, HEAD)
    assert record is not None and record["claude"] and not record["cross_model"]


@pytest.mark.parametrize(
    "line",
    [
        f"**Codex (not run)**: ACCEPT @ {HEAD}",
        f"**Codex review (awaiting)**: ACCEPT @ {HEAD}",
        f"**Codex (queued)**: r2 ACCEPT@{HEAD}",
        f"**Gemini (unavailable)**: r1 REJECT, r2 ACCEPT @ {HEAD}",
        f"Codex: queued — ACCEPT @ {HEAD}",
    ],
)
def test_a_disabled_label_on_the_verdict_line_names_no_family(line):
    record = rrc.classify_record(f"## Review record\n{line}\n", HEAD)
    assert record is None or not record["cross_model"]
    report = rrc.evaluate(HEAD, RISKY, [_c(OPUS_RECORD), _c(line)], [])
    assert report["status"] == "MISSING_CROSS_MODEL"


def test_a_disabled_label_does_not_fall_back_to_the_previous_claude_header():
    body = f"## Claude review\n**Codex (not run)**: ACCEPT @ {HEAD}\n"
    record = rrc.classify_record(body, HEAD)
    assert record is not None and not record["claude"] and not record["cross_model"]


def test_a_live_codex_verdict_line_still_counts():
    record = rrc.classify_record(f"**Codex (round 2)**: ACCEPT @ {HEAD}\n", HEAD)
    assert record is not None and record["cross_model"]


_GATE = {"filename": "nexus/gate.py"}


def test_an_evil_merge_that_keeps_the_reviewed_tree_is_not_accepted():
    # parents (R, main@X) with R's tree: compare R...M is empty, but main's file X reverted
    # shows up as a new PR path at the head
    rc, status = _delta_case(changed=(), pr_files=DOCS + [_GATE])
    assert rc == 1 and "older head only" in status["description"]


def test_a_base_change_to_a_pr_path_on_the_side_parent_is_not_accepted():
    assert _delta_case(side_changed=({"filename": "docs/a.md"},))[0] == 1
    assert (
        _delta_case(
            side_changed=({"filename": "docs/gone.md"},),
            pr_at_old=({"filename": "docs/a.md"}, {"filename": "docs/gone.md"}),
            pr_files=DOCS + [{"filename": "docs/gone.md"}],
        )[0]
        == 1
    )


def test_a_truncated_side_parent_change_list_is_not_accepted():
    files = tuple({"filename": f"m{i}.py"} for i in range(300))
    assert _delta_case(side_changed=files)[0] == 1


def test_an_honest_merge_where_main_changed_a_non_pr_file_is_accepted():
    rc, status = _delta_case(
        side_changed=({"filename": "main/other.py"}, {"filename": "main/more.py"}),
        changed=({"filename": "main/other.py"}, {"filename": "main/more.py"}),
    )
    assert rc == 0 and "merge-only delta verified" in status["description"]


def test_the_compare_file_list_is_read_from_page_one_only():
    urls: list[str] = []

    def fetch(url, token):
        urls.append(url)
        assert "page=1" in url  # later pages carry no "files" key
        return {"files": [{"filename": "a.py"}, {"filename": "b.py", "previous_filename": "c.py"}]}

    assert rrc._compare_files(fetch, "https://api.github.com/repos/o/r", TOKEN, "x", "y") == {
        "a.py",
        "b.py",
        "c.py",
    }
    assert len(urls) == 1


def test_gemini_with_codex_out_of_credits_aside_still_credits_cross_model():
    line = (
        "- Cross-model adversarial review (Gemini 3.8 Flash High via agy, Codex out of "
        f"credits): ACCEPT @ {HEAD}"
    )
    record = rrc.classify_record(f"## Review record\n{line}\n", HEAD)
    assert record is not None and record["cross_model"]


# -- per-repo rebuttal at the cap (#2954, cairnwork#344) ------------------------------


def test_rebuttal_counts_everywhere_except_cairnwork():
    assert rrc.rebuttal_counts("James3014/Nexus-new")
    assert rrc.rebuttal_counts("James3014/nexus-core")
    assert rrc.rebuttal_counts("o/r")
    assert not rrc.rebuttal_counts("cairnwork/cairnwork")
    assert not rrc.rebuttal_counts("Cairnwork/Cairnwork")  # GitHub names are case-insensitive
    assert not rrc.rebuttal_counts(" cairnwork/cairnwork ")
    assert rrc.rebuttal_counts("cairnwork/cairnwork.github.io")  # only the product repo


def test_cairnwork_rebuttal_at_cap_is_not_a_cross_model_record():
    comments = [_c(OPUS_RECORD), _c(CODEX_REBUTTAL)]
    nexus = rrc.evaluate(HEAD, RISKY, comments, [])
    assert nexus["status"] == "OK" and nexus["cross_model"] is True
    cairn = rrc.evaluate(HEAD, RISKY, comments, [], allow_rebuttal=False)
    assert cairn["status"] == "MISSING_CROSS_MODEL" and cairn["cross_model"] is False
    assert "rebuttal at the cap does not count" in cairn["reason"]
    # the #2280 shape (cap in the section header, "Rebutted" lines later) is dropped too
    shaped = (
        f"Head {HEAD}\n**Claude**: ACCEPT@{HEAD}\n**Codex review (3 rounds, cap)**\n"
        "- **r3 REJECT**: early return.\n  - **Rebutted:** verdict unchanged, cap reached.\n"
    )
    assert rrc.evaluate(HEAD, RISKY, [_c(shaped)], [])["status"] == "OK"
    assert rrc.evaluate(HEAD, RISKY, [_c(shaped)], [], allow_rebuttal=False)["status"] == (
        "MISSING_CROSS_MODEL"
    )


def test_cairnwork_still_takes_a_cross_model_accept_and_low_risk_prs():
    accept = [_c(OPUS_RECORD), _c(CODEX_RECORD)]
    assert rrc.evaluate(HEAD, RISKY, accept, [], allow_rebuttal=False)["status"] == "OK"
    # an accept next to an earlier-round rebuttal still counts: only the rebuttal is dropped
    both = [_c(OPUS_RECORD), _c(CODEX_REBUTTAL), _c(CODEX_RECORD)]
    assert rrc.evaluate(HEAD, RISKY, both, [], allow_rebuttal=False)["status"] == "OK"
    # not high risk: no cross-model record needed, the rebuttal changes nothing
    docs = rrc.evaluate(HEAD, DOCS, [_c(OPUS_RECORD), _c(CODEX_REBUTTAL)], [], allow_rebuttal=False)
    assert docs["status"] == "OK"
    # a rebuttal-only comment is no independent record either way
    assert rrc.evaluate(HEAD, DOCS, [_c(CODEX_REBUTTAL)], [], allow_rebuttal=False)["status"] == (
        "MISSING_RECORD"
    )


def test_cairnwork_delta_verified_rebuttal_does_not_count():
    claude_old = _c(OPUS_RECORD.replace(HEAD, R_OLD))
    rebut_old = _c(CODEX_REBUTTAL.replace(HEAD, R_OLD))
    comments = [claude_old, rebut_old]
    assert rrc.evaluate(HEAD, RISKY, comments, [], (R_OLD,))["status"] == "OK"
    assert rrc.evaluate(HEAD, RISKY, comments, [], (R_OLD,), allow_rebuttal=False)["status"] == (
        "MISSING_CROSS_MODEL"
    )


def test_run_drops_the_rebuttal_for_cairnwork_only(capsys):
    comments = [_c(OPUS_RECORD), _c(CODEX_REBUTTAL)]
    for repo, state, rc_want in (
        ("James3014/Nexus-new", "success", 0),
        ("cairnwork/cairnwork", "failure", 1),
    ):
        posted, post = _posts()
        rc = rrc.run(repo, 7, TOKEN, _fake(files=RISKY, comments=comments), post)
        assert rc == rc_want
        ((url, payload),) = posted
        assert url.endswith(f"/repos/{repo}/statuses/{HEAD}") and payload["state"] == state
    assert "MISSING_CROSS_MODEL" in capsys.readouterr().out


def test_run_cairnwork_merge_only_delta_ignores_an_old_rebuttal():
    claude_old = _c(OPUS_RECORD.replace(HEAD, R_OLD[:12]))
    rebut_old = _c(CODEX_REBUTTAL.replace(HEAD, R_OLD))
    fetch = _delta_fetch_with_old_pr_files(
        RISKY, pr_files=RISKY, comments=[claude_old, rebut_old], changed=()
    )

    def wrapped(url, token):
        return _pull_main() if url.endswith("/pulls/7") else fetch(url, token)

    results = {}
    for repo in ("James3014/Nexus-new", "cairnwork/cairnwork"):
        posted, post = _posts()
        results[repo] = (rrc.run(repo, 7, TOKEN, wrapped, post), posted[0][1]["state"])
    assert results["James3014/Nexus-new"] == (0, "success")
    assert results["cairnwork/cairnwork"] == (1, "failure")


# -- #2992: a record for another head, a later REJECT, a capped file list ---------------

STALE_LABEL_RECORD = (
    "## Review record — Claude (claude-opus-5-5)\n"
    f"- Head reviewed: `{R_OLD}`\n- Verdict: **ACCEPT**\n"
    f"- Pushed a fix after review, head is now {HEAD}; not re-reviewed.\n"
)


@pytest.mark.parametrize(
    "tail",
    [
        f"- Pushed a fix after review, head is now {HEAD}; not re-reviewed.\n",
        f"- Merged main → final head {HEAD}\n",
    ],
)
def test_a_bare_verdict_under_an_older_head_label_is_not_read_as_the_new_head(tail):
    body = (
        "## Review record — Claude (claude-opus-5-5)\n"
        f"- Head reviewed: `{R_OLD}`\n- Verdict: **ACCEPT**\n" + tail
    )
    record = rrc.classify_record(body, HEAD)
    assert record is not None and record["claude"] is False
    assert rrc.evaluate(HEAD, DOCS, [_c(body)], [])["status"] == "MISSING_RECORD"
    # The record still belongs to the head it names, so a merge-only delta can carry it.
    old = rrc.classify_record(body, R_OLD)
    assert old is not None and old["claude"] is True


def test_a_head_label_after_the_verdict_still_binds_when_it_is_the_only_head():
    body = f"**Claude review** (Opus)\nVerdict: **ACCEPT**\nHead reviewed: `{HEAD}`\n"
    assert rrc.evaluate(HEAD, DOCS, [_c(body)], [])["status"] == "OK"


def test_prose_naming_another_sha_after_the_word_head_does_not_unbind_the_record():
    # Shape of a real record: the title labels the head, a finding mentions main's sha.
    body = (
        f"## Review record — head `{HEAD}`\n\n"
        "**Independent Claude review** (Claude Opus 5.5): **VERDICT: ACCEPT**.\n"
        f"- Checked on this head and on origin/main {OLD[:9]}.\n\n"
        "**Cross-model review** (Gemini via agy-bulk) @ `8d70e3ff`: **VERDICT: ACCEPT**.\n"
    )
    record = rrc.classify_record(body, HEAD)
    assert record is not None and record["claude"] and record["cross_model"]
    assert rrc.evaluate(HEAD, RISKY, [_c(body)], [])["status"] == "OK"


def test_run_carries_an_older_head_label_record_only_through_a_verified_merge_delta():
    body = STALE_LABEL_RECORD.replace(
        f"- Pushed a fix after review, head is now {HEAD}; not re-reviewed.\n",
        f"- Merged main → final head {HEAD}\n",
    )
    rc, status = _delta_case(comments=[_c(body)])
    assert rc == 0 and status["state"] == "success"
    assert f"record at {R_OLD[:9]}, merge-only delta verified" in status["description"]
    rc, status = _delta_case(comments=[_c(body)], changed=({"filename": "docs/a.md"},))
    assert rc == 1 and status["state"] == "failure"


CLAUDE_AT_HEAD = f"**Claude review** (Claude Opus 5.5): **ACCEPT@{HEAD[:9]}**.\n"


@pytest.mark.parametrize(
    "comments",
    [
        [
            f"Head reviewed: {HEAD}\n**Codex**: r1 ACCEPT\n**Codex**: r2 REJECT — data-loss bug\n"
            "**Claude**: ACCEPT\n"
        ],
        [f"Codex ACCEPT@{HEAD}", f"Codex r2 REJECT@{HEAD}: found a data-loss bug", CLAUDE_AT_HEAD],
        [f"Codex r2: ACCEPT. After the rebase, Codex r3 on head {HEAD}: REJECT\n", CLAUDE_AT_HEAD],
    ],
)
def test_a_later_cross_model_reject_at_the_head_withdraws_its_accept(comments):
    report = rrc.evaluate(HEAD, RISKY, [_c(body) for body in comments], [])
    assert report["status"] == "MISSING_CROSS_MODEL"
    assert "later Codex/Gemini REJECT" in report["reason"]


def test_a_later_claude_reject_at_the_head_withdraws_the_independent_record():
    comments = [_c(OPUS_RECORD), _c(f"**Claude review** (Opus) r2: REJECT at {HEAD}: a regression")]
    report = rrc.evaluate(HEAD, DOCS, comments, [])
    assert report["status"] == "MISSING_RECORD" and "later Claude/Opus REJECT" in report["reason"]


@pytest.mark.parametrize(
    "comments",
    [
        # A later round accepts again.
        [f"Codex r1 REJECT@{HEAD}: two findings", f"Codex r2 ACCEPT@{HEAD}", CLAUDE_AT_HEAD],
        # A round history listed after the summary verdict that ends in an ACCEPT.
        [
            f"**Codex review** @ {HEAD}: **ACCEPT**\n- r1: REJECT (missing test)\n- r2: ACCEPT\n",
            CLAUDE_AT_HEAD,
        ],
        # A numbered later round survives an earlier round listed after it.
        [f"Codex r3 ACCEPT@{HEAD}", f"Recap: Codex r2 REJECT@{HEAD}: one finding", CLAUDE_AT_HEAD],
        # Resolved, negated or quoted rejections withdraw nothing; a table row is read like
        # any line, so a resolved one withdraws nothing either (r5 R6).
        [f"Codex ACCEPT@{HEAD}", f"Codex r2 REJECT@{HEAD} (rebutted, see above)", CLAUDE_AT_HEAD],
        [f"Codex ACCEPT@{HEAD}", f"Codex did not REJECT at {HEAD}", CLAUDE_AT_HEAD],
        [f"Codex ACCEPT@{HEAD}", f'Codex said "REJECT" at {HEAD} in a dry run', CLAUDE_AT_HEAD],
        [
            f"Codex ACCEPT@{HEAD}",
            f"| Codex | r2 | REJECT@{HEAD} | fixed in 1a2b3c4d5 |",
            CLAUDE_AT_HEAD,
        ],
        # A REJECT at another head is about that head.
        [f"Codex r1 REJECT@{OLD[:9]}: fixed later", f"Codex r2 ACCEPT@{HEAD}", CLAUDE_AT_HEAD],
        [CODEX_RECORD, CLAUDE_AT_HEAD],
    ],
)
def test_resolved_or_superseded_rejects_do_not_withdraw(comments):
    assert rrc.evaluate(HEAD, RISKY, [_c(body) for body in comments], [])["status"] == "OK"


def test_a_reject_is_credited_to_the_model_named_closest_before_it():
    # Shape of a real cairnwork disposition: the Claude ACCEPT stands, Gemini's REJECT is
    # Gemini's own.
    body = (
        f"Round 3 split: **Independent Claude review** ACCEPT at {HEAD}; "
        f"**Cross-model review** (Gemini 3.8 Flash High) REJECT at {HEAD}.\n"
    )
    record = rrc.classify_record(body, HEAD)
    assert record is not None and record["claude"] is True and record["cross_model"] is False
    assert [e["family"] for e in record["events"] if e["kind"] == "reject"] == ["cross_model"]


def test_a_pr_file_list_at_the_api_cap_counts_as_high_risk():
    files = [{"filename": f"docs/f{i:04}.md"} for i in range(rrc.MAX_PR_FILES)]
    assert rrc.high_risk_paths(files) == [rrc.TRUNCATED_FILES]
    assert rrc.high_risk_paths(files[:-1]) == []
    comments = [_c(OPUS_RECORD)]
    posted, post = _posts()
    assert rrc.run("o/r", 7, TOKEN, _fake(files=files, comments=comments), post) == 1
    assert posted[0][1]["state"] == "failure"
    assert "MISSING_CROSS_MODEL" in posted[0][1]["description"]


def test_a_reviewed_commit_label_without_the_word_head_also_names_the_older_head():
    body = (
        f"**Claude review** (Opus)\nReviewed commit {R_OLD[:12]}\nVerdict: **ACCEPT**\n"
        f"Pushed one more fix; head is now {HEAD}.\n"
    )
    assert rrc.evaluate(HEAD, DOCS, [_c(body)], [])["status"] == "MISSING_RECORD"


@pytest.mark.parametrize(
    "reject_line",
    ["- r3 Codex did not REJECT", '- r3: Codex never said "REJECT"', "- r3: no REJECT this round"],
)
def test_a_negated_or_quoted_round_three_reject_opens_no_rebuttal_at_the_cap(reject_line):
    body = f"Head: {HEAD}\n**Codex review**\n{reject_line}\n- Rebutted\n"
    record = rrc.classify_record(body, HEAD)
    assert record is not None and record["rebuttal_at_cap"] is False
    report = rrc.evaluate(HEAD, RISKY, [_c(body), _c(CLAUDE_AT_HEAD)], [])
    assert report["status"] == "MISSING_CROSS_MODEL"
    # The stated shape still counts.
    assert (rrc.classify_record(CODEX_REBUTTAL, HEAD) or {}).get("rebuttal_at_cap") is True


REBUTTAL_SECTION = (
    f"Head: {HEAD}\n**Codex review**\n- r3 REJECT@{HEAD[:9]}: one finding\n- Rebutted: see #1\n"
)


@pytest.mark.parametrize(
    "later",
    [
        f"Codex r4 REJECT@{HEAD}: a new finding",  # a later comment, a later round
        f"Codex REJECT@{HEAD}: a new finding",  # a later comment, no round
    ],
)
def test_a_later_reject_withdraws_an_earlier_rebuttal_at_the_cap(later):
    assert (rrc.classify_record(REBUTTAL_SECTION, HEAD) or {}).get("rebuttal_at_cap") is True
    ok = rrc.evaluate(HEAD, RISKY, [_c(REBUTTAL_SECTION), _c(CLAUDE_AT_HEAD)], [])
    assert ok["status"] == "OK"
    report = rrc.evaluate(HEAD, RISKY, [_c(REBUTTAL_SECTION), _c(later), _c(CLAUDE_AT_HEAD)], [])
    assert report["status"] == "MISSING_CROSS_MODEL"
    same_comment = REBUTTAL_SECTION + f"- r4: REJECT at {HEAD}: a new finding\n"
    report = rrc.evaluate(HEAD, RISKY, [_c(same_comment), _c(CLAUDE_AT_HEAD)], [])
    assert report["status"] == "MISSING_CROSS_MODEL"


def test_an_earlier_round_reject_recapped_later_keeps_the_rebuttal():
    recap = f"Recap: Codex r2 REJECT@{HEAD}: one finding"
    report = rrc.evaluate(HEAD, RISKY, [_c(REBUTTAL_SECTION), _c(recap), _c(CLAUDE_AT_HEAD)], [])
    assert report["status"] == "OK"


@pytest.mark.parametrize(
    "body",
    [
        f"Claude: ACCEPT@{HEAD}\nClaude r2 REJECT@{HEAD}: a regression\n",
        f"**Claude review** (Opus)\nHead reviewed: {HEAD}\nVerdict: **ACCEPT**\n- r1: REJECT (missing test)\n",
    ],
)
def test_a_numbered_reject_after_an_unnumbered_accept_in_one_comment_withdraws_it(body):
    # Codex r3 on #2993: a round history that ends in a REJECT is an open rejection.
    report = rrc.evaluate(HEAD, DOCS, [_c(body)], [])
    assert report["status"] == "MISSING_RECORD" and "later Claude/Opus REJECT" in report["reason"]


# -- #2993 review: shapes an honest record uses must not read as an open REJECT --------


@pytest.mark.parametrize(
    "body",
    [
        # cairnwork #269: a history line about an earlier round, short sha.
        f"## Review record — head `{HEAD}`\n"
        f"**Independent Claude review** (Claude Opus 5.5): **ACCEPT at {HEAD}**.\n"
        "Previous round (Claude, REJECT at f9ccbf67):\n- MUST-FIX 1: fixed in 9b536cd.\n",
        # Gate verdict values inside a Claude review's findings.
        OPUS_RECORD
        + "- Tested: a missing receipt yields REPAIR_REQUIRED; a tampered one: REJECT.\n",
        OPUS_RECORD + "- Core verdict mapping: stale lease - REJECT, expired - REPAIR_REQUIRED.\n",
        OPUS_RECORD + "- Edge case: verdict: REJECT is returned for an unsigned receipt.\n",
        OPUS_RECORD + "1. CHANGES_REQUESTED reviews are ignored by the gate — intentional.\n",
        # Prose about an earlier head is not a Head label.
        "## Review record — Claude (Opus)\n"
        f"Head reviewed: {HEAD}\nRe-review after fixes from head {OLD[:9]}.\n- Verdict: **ACCEPT**\n",
        f"## Claude review (Opus 5.5): ACCEPT\nHead reviewed: {HEAD}\nPrevious head {OLD[:9]}.\n",
    ],
)
def test_history_lines_gate_words_and_head_prose_keep_an_honest_record(body):
    assert rrc.evaluate(HEAD, DOCS, [_c(body)], [])["status"] == "OK"


def test_a_round_history_heading_keeps_the_cross_model_accept():
    # cairnwork #318: "Round 1 (<sha>) REJECT items:" heads a list of earlier findings.
    body = (
        f"Head reviewed: {HEAD}\n"
        f"**Cross-model review** (Gemini), round 2: **ACCEPT at {HEAD}**.\n"
        "Round 1 (f01100e) REJECT items:\n1. MAJOR: disputed. Gemini: resolved.\n"
        "**Claude** (Opus): ACCEPT\n"
    )
    assert rrc.evaluate(HEAD, RISKY, [_c(body)], [])["status"] == "OK"


def test_a_history_before_the_final_round_keeps_the_record():
    body = (
        f"Head reviewed: {HEAD}\n**Claude review** (Opus): ACCEPT\n**Codex adversarial review**\n"
        f"- r1 at head {OLD[:9]}: REJECT — race in X (fixed)\n- r2: ACCEPT\n"
    )
    assert rrc.evaluate(HEAD, RISKY, [_c(body)], [])["status"] == "OK"


@pytest.mark.parametrize(
    "tail",
    [
        "P1 data loss, not fixed yet",
        "P1 data loss, not addressed",
        "P1 data loss, will be addressed in a follow-up",
        "P1 data loss, needs to be fixed before merge",
    ],
)
def test_a_reject_whose_fix_is_negated_or_postponed_is_still_open(tail):
    comments = [
        _c(f"Codex ACCEPT@{HEAD}"),
        _c(f"Codex r2 REJECT@{HEAD}: {tail}"),
        _c(CLAUDE_AT_HEAD),
    ]
    assert rrc.evaluate(HEAD, RISKY, comments, [])["status"] == "MISSING_CROSS_MODEL"


def test_a_model_named_in_an_aside_does_not_take_the_reject():
    comments = [
        _c(OPUS_RECORD),
        _c(f"**Claude review** (Opus, after the Codex findings) r2: REJECT at {HEAD}"),
    ]
    assert rrc.evaluate(HEAD, DOCS, comments, [])["status"] == "MISSING_RECORD"


def test_a_line_with_too_many_verdict_tokens_is_skipped_and_parsing_stays_fast():
    import time

    crowded = "r1 ACCEPT; " * (rrc.MAX_VERDICTS_PER_LINE + 1)
    assert rrc.verdict_clauses(crowded) == [] and rrc.reject_clauses(crowded) == []
    started = time.monotonic()
    for body in ("r1 ACCEPT; " * 6000, "r1 REJECT; " * 6000, "head" + " " * 65000 + "x"):
        rrc.classify_record(f"{body}\n{HEAD}", HEAD)
    assert time.monotonic() - started < 5  # about 40 s before the bound


# -- #2994: cairnwork's own high-risk paths ----------------------------------------------


@pytest.mark.parametrize(
    ("path", "high"),
    [
        ("src/cairnwork/pipeline.py", True),
        ("scripts/release.sh", True),
        ("REVIEW.md", True),
        ("experimental/x/mod.py", False),
        ("docs/guide.md", False),
        ("tests/test_x.py", False),
        ("srcx/a.py", False),
    ],
)
def test_cairnwork_adds_its_own_high_risk_paths(path, high):
    files = [{"filename": path}]
    assert rrc.high_risk_paths(files, "cairnwork/cairnwork") == ([path] if high else [])
    assert rrc.high_risk_paths(files, "Cairnwork/Cairnwork") == ([path] if high else [])
    # Other repos keep the shared list only.
    assert rrc.high_risk_paths(files, "James3014/Nexus-new") == rrc.high_risk_paths(files)
    renamed = [{"filename": "docs/old.md", "previous_filename": path}]
    assert bool(rrc.high_risk_paths(renamed, "cairnwork/cairnwork")) is high


def test_run_requires_a_cross_model_record_for_a_cairnwork_src_change():
    files = [{"filename": "src/cairnwork/pipeline.py"}]
    for repo, state in (("James3014/Nexus-new", "success"), ("cairnwork/cairnwork", "failure")):
        posted, post = _posts()
        rrc.run(repo, 7, TOKEN, _fake(files=files, comments=[_c(OPUS_RECORD)]), post)
        assert posted[0][1]["state"] == state, repo
    posted, post = _posts()
    comments = [_c(OPUS_RECORD), _c(CODEX_RECORD)]
    assert (
        rrc.run("cairnwork/cairnwork", 7, TOKEN, _fake(files=files, comments=comments), post) == 0
    )
    assert posted[0][1]["state"] == "success"


def test_run_cairnwork_merge_only_delta_still_requires_a_cross_model_record_for_src():
    src = [{"filename": "src/cairnwork/x.py"}]
    fetch = _delta_fetch_with_old_pr_files(src, pr_files=src, changed=())

    def wrapped(url, token):
        return _pull_main() if url.endswith("/pulls/7") else fetch(url, token)

    results = {}
    for repo in ("James3014/Nexus-new", "cairnwork/cairnwork"):
        posted, post = _posts()
        rrc.run(repo, 7, TOKEN, wrapped, post)
        results[repo] = posted[0][1]
    assert results["James3014/Nexus-new"]["state"] == "success"
    assert results["cairnwork/cairnwork"]["state"] == "failure"
    assert "MISSING_CROSS_MODEL" in results["cairnwork/cairnwork"]["description"]


# -- #3002: false passes (short sha, resolution words, delta REJECT, rounds, labels) -------


def _eval3002(comments):
    return rrc.evaluate(HEAD, RISKY, comments, [])


def _status3002(comments):
    return _eval3002(comments)["status"]


def test_3002_f1_short_sha_accept_is_not_bound_to_the_head():
    # A 7-char sha of an older commit under a comment-level head label is not the head.
    body = (
        f"Head reviewed: {HEAD}\n**Claude review** (Opus): ACCEPT\n"
        "**Codex review**: r1 ACCEPT at 1a2b3c4 (before the last fix)\n"
    )
    result = _eval3002([_c(body)])
    assert result["status"] == "MISSING_CROSS_MODEL"


def test_3002_f1_short_sha_reject_withdraws_the_accept():
    comments = [
        _c(f"Codex ACCEPT@{HEAD}"),
        _c("Codex r2 REJECT@8d70e3f: race in X"),
        _c(CLAUDE_AT_HEAD),
    ]
    assert _status3002(comments) != "OK"


@pytest.mark.parametrize(
    "text",
    [
        "the symlink is resolved after the containment check",
        "the env path can be overridden by PR text",
        "the cache is cleared before the write",
    ],
)
def test_3002_f2_ordinary_words_do_not_resolve_a_reject(text):
    comments = [
        _c(f"Codex ACCEPT@{HEAD}"),
        _c(f"Codex r2 REJECT@{HEAD}: {text}"),
        _c(CLAUDE_AT_HEAD),
    ]
    assert _status3002(comments) != "OK"


def test_3002_f2_a_status_word_still_resolves_a_reject():
    comments = [
        _c(f"Codex ACCEPT@{HEAD}"),
        _c(f"Codex r2 REJECT@{HEAD} (fixed in 1a2b3c4d5)"),
        _c(CLAUDE_AT_HEAD),
    ]
    assert _status3002(comments) == "OK"


def test_3002_f3_delta_path_folds_a_reject_bound_to_the_new_head():
    reject = f"**Claude review** (Opus) r2: REJECT at {HEAD}: a regression"
    rc, status = _delta_case(comments=[_c(OPUS_RECORD.replace(HEAD, R_OLD[:12])), _c(reject)])
    assert rc == 1 and status["state"] == "failure"


def test_3002_f4_rounds_are_compared_within_one_reviewer_only():
    comments = [
        _c(f"Codex r3 ACCEPT@{HEAD}"),
        _c(f"Gemini r1 REJECT@{HEAD}: race in X"),
        _c(CLAUDE_AT_HEAD),
    ]
    assert _status3002(comments) != "OK"
    same = [
        _c(f"Codex r3 ACCEPT@{HEAD}"),
        _c(f"Codex r4 REJECT@{HEAD}: race in X"),
        _c(CLAUDE_AT_HEAD),
    ]
    assert _status3002(same) != "OK"


def test_3002_f5_in_progress_label_does_not_drop_a_reject():
    comments = [
        _c(f"Codex ACCEPT@{HEAD}"),
        _c(f"**Codex r2** (fix in progress): REJECT@{HEAD}: race in X"),
        _c(CLAUDE_AT_HEAD),
    ]
    assert _status3002(comments) != "OK"


def test_3002_f3_delta_path_folds_a_short_prefix_reject_of_the_new_head():
    reject = f"**Claude review** (Opus) r2: REJECT@{HEAD[:7]}: a regression"
    rc, status = _delta_case(comments=[_c(OPUS_RECORD.replace(HEAD, R_OLD[:12])), _c(reject)])
    assert rc == 1 and status["state"] == "failure"


@pytest.mark.parametrize("label", ["(fixing now)", "(fixes in progress)", "(review in-progress)"])
def test_3002_f5_other_in_progress_wordings_do_not_drop_a_reject(label):
    comments = [
        _c(f"Codex ACCEPT@{HEAD}"),
        _c(f"**Codex r2** {label}: REJECT@{HEAD}: race in X"),
        _c(CLAUDE_AT_HEAD),
    ]
    assert _status3002(comments) != "OK"


def test_3002_in_progress_label_cannot_make_an_accept_count():
    for body in (
        f"**Codex r2** (fix in progress): ACCEPT@{HEAD}",
        f"**Codex review** (fix in progress)\nVerdict: **ACCEPT** at {HEAD}",
    ):
        assert _status3002([_c(body), _c(CLAUDE_AT_HEAD)]) == "MISSING_CROSS_MODEL"


def test_3002_delta_path_keeps_an_approved_review_at_the_old_head():
    approved = {"state": "APPROVED", "commit_id": R_OLD, "user": {"login": "x"}}
    rc, status = _delta_case(comments=[], reviews=[approved])
    assert rc == 0 and status["state"] == "success"


@pytest.mark.parametrize(
    "text",
    [
        "resolved path escapes the root",
        "fixed-size buffer overflow",
        "(deferred cleanup frees twice)",
    ],
)
def test_3002_finding_text_that_starts_with_a_status_word_stays_open(text):
    comments = [
        _c(f"Codex ACCEPT@{HEAD}"),
        _c(f"Codex r2 REJECT@{HEAD}: {text}"),
        _c(CLAUDE_AT_HEAD),
    ]
    assert _status3002(comments) != "OK"


@pytest.mark.parametrize("tail", ["-> rebutted: see test", "→ rebutted", ", fixed in 1a2b3c4d5"])
def test_3002_arrow_and_comma_resolutions_still_resolve(tail):
    comments = [
        _c(f"Codex ACCEPT@{HEAD}"),
        _c(f"Codex r2 REJECT@{HEAD} {tail}"),
        _c(CLAUDE_AT_HEAD),
    ]
    assert _status3002(comments) == "OK"


def test_3002_later_short_prefix_reject_on_the_same_line_is_kept():
    line = f"Codex r1 REJECT@1a2b3c4d5 (fixed), r2 REJECT@{HEAD[:7]}: race"
    assert _status3002([_c(f"Codex ACCEPT@{HEAD}"), _c(line), _c(CLAUDE_AT_HEAD)]) != "OK"


def test_3002_line_level_short_sha_of_an_older_commit_does_not_bind_to_the_head():
    body = f"Head reviewed: {HEAD}\n**Claude review** (Opus): ACCEPT\nCodex: ACCEPT. Last checked 1a2b3c4\n"
    assert _status3002([_c(body)]) == "MISSING_CROSS_MODEL"


# -- r5: REJECTs fail closed, ACCEPTs bind only to an unambiguous head -------------------

H7 = HEAD[:7]  # 8d70e3f, the GitHub UI's short sha
NUM_HEAD = "1234567" + HEAD[7:]  # a head whose 7-char prefix is all digits


def _codex_accept_then(*bodies):
    return [_c(f"Codex ACCEPT@{HEAD}"), *[_c(b) for b in bodies], _c(CLAUDE_AT_HEAD)]


@pytest.mark.parametrize(
    "body",
    [
        f"Head reviewed: {HEAD}\n**Codex review**\nr2 REJECT — the ed25519 signature is never checked",
        f"Head reviewed: {HEAD}\n**Codex review**\nr2 REJECT — same bug as fix 1a2b3c4d",
        f"Head reviewed: {HEAD}\nCodex r2: REJECT — deadbeef sentinel leaks into the log",
        f"Head reviewed: {HEAD}\nCodex r2 REJECT: reverts the fix from 1a2b3c4",
    ],
)
def test_r5_r1_a_hex_looking_word_in_the_finding_keeps_the_reject(body):
    assert _status3002(_codex_accept_then(body)) == "MISSING_CROSS_MODEL"


def test_r5_r1_claude_reject_with_a_hex_word_withdraws_the_independent_record():
    comments = [
        _c(f"Head reviewed: {HEAD}\nOpus r1: ACCEPT"),
        _c(f"Head reviewed: {HEAD}\nOpus r2: REJECT — same bug as fix 1a2b3c4d"),
    ]
    assert rrc.evaluate(HEAD, DOCS, comments, [])["status"] == "MISSING_RECORD"


@pytest.mark.parametrize(
    "body",
    [
        f"Codex r1 REJECT@1a2b3c4d5: race in X\nHead reviewed: {HEAD}",
        f"Head reviewed: {HEAD}\n- Round 1 @ 09e25e8f5: REJECT, 2 findings",
        f"Head reviewed: {HEAD}\n**Codex review**\n- Round 1 (dd2a5cd): REJECT, 1 finding",
    ],
)
def test_r5_r1_a_reject_whose_label_binds_another_commit_is_about_that_commit(body):
    assert _status3002(_codex_accept_then(body)) == "OK"


@pytest.mark.parametrize(
    "body",
    [
        f"**Codex review**\nr2 REJECT@{H7}: race in X",
        f"Head reviewed: {H7}\nCodex r2: REJECT — race in X",
        f"Re-review at head {H7}\nCodex r2: REJECT — race in X",
        f"### Codex review\nr2 @{H7}: REJECT",
    ],
)
def test_r5_r2_a_short_prefix_reject_withdraws_the_accept(body):
    assert _status3002(_codex_accept_then(body)) == "MISSING_CROSS_MODEL"


def test_r5_r2_a_short_prefix_claude_reject_on_a_head_line_withdraws():
    comments = [
        _c(f"Head reviewed: {HEAD}\nOpus r1: ACCEPT"),
        _c(f"Head reviewed: {H7}\nOpus r2: REJECT — regression"),
    ]
    assert rrc.evaluate(HEAD, DOCS, comments, [])["status"] == "MISSING_RECORD"


def test_r5_r2_an_all_digit_short_prefix_reject_withdraws():
    comments = [
        _c(f"Head reviewed: {NUM_HEAD}\nOpus r1: ACCEPT"),
        _c("Opus r2 @1234567: REJECT"),
    ]
    assert rrc.evaluate(NUM_HEAD, DOCS, comments, [])["status"] == "MISSING_RECORD"


@pytest.mark.parametrize("old", ["4920381", "49203815"])
def test_r5_r3_an_all_digit_older_sha_does_not_bind_an_accept(old):
    for body in (
        f"Head reviewed: {HEAD}\n**Claude review** (Opus): ACCEPT\n"
        f"**Codex review**: r1 ACCEPT at {old} (before the last fix)\n",
        f"Head reviewed: {HEAD}\n**Claude review** (Opus): ACCEPT\nCodex: ACCEPT. Last checked {old}\n",
    ):
        assert _status3002([_c(body)]) == "MISSING_CROSS_MODEL", body


def test_r5_r4_opus_and_sonnet_are_different_reviewers():
    comments = [_c(f"Opus r3 ACCEPT@{HEAD}"), _c(f"Sonnet r1 REJECT@{HEAD}: data loss")]
    assert rrc.evaluate(HEAD, DOCS, comments, [])["status"] == "MISSING_RECORD"


def test_r5_r4_reviewers_named_only_by_their_section_header_are_different():
    comments = [
        _c(f"Head reviewed: {HEAD}\n### Codex review\nr3: ACCEPT"),
        _c(f"Head reviewed: {HEAD}\n### Gemini review\nr1: REJECT — data loss"),
        _c(CLAUDE_AT_HEAD),
    ]
    assert _status3002(comments) == "MISSING_CROSS_MODEL"


def test_r5_r4_the_same_header_named_reviewer_keeps_its_later_round():
    comments = [
        _c(f"Head reviewed: {HEAD}\n### Codex review\nr3: ACCEPT"),
        _c(f"Head reviewed: {HEAD}\n### Codex review\nr2: REJECT — data loss"),
        _c(CLAUDE_AT_HEAD),
    ]
    assert _status3002(comments) == "OK"


@pytest.mark.parametrize(
    ("accepts", "reject", "files", "status"),
    [
        (
            f"Opus 4.7 r1 @{HEAD}: ACCEPT",
            f"Opus 4.7 r2 @{HEAD}: REJECT — data loss",
            DOCS,
            "MISSING_RECORD",
        ),
        (
            f"Codex gpt-5.5 r1 @{HEAD}: ACCEPT",
            f"Codex gpt-5.5 xhigh r2 @{HEAD}: REJECT — x",
            RISKY,
            "MISSING_CROSS_MODEL",
        ),
        (
            f"Codex ACCEPT@{HEAD}",
            f"Gemini 3.1 Pro r1 @{HEAD}: REJECT — data loss",
            RISKY,
            "MISSING_CROSS_MODEL",
        ),
        (
            f"Codex ACCEPT@{HEAD}",
            f"Gemini 3.8 Flash High r2 @{HEAD}: REJECT",
            RISKY,
            "MISSING_CROSS_MODEL",
        ),
    ],
)
def test_r5_r5_a_versioned_reviewer_label_still_rejects(accepts, reject, files, status):
    comments = [_c(accepts), _c(reject)]
    if files is RISKY:
        comments.append(_c(CLAUDE_AT_HEAD))
    assert rrc.evaluate(HEAD, files, comments, [])["status"] == status


@pytest.mark.parametrize(
    "body",
    [
        f"Head reviewed: {HEAD}\n**Codex review**\n```\nVERDICT: REJECT\n```",
        f"Head reviewed: {HEAD}\n| Gemini | r1 | REJECT |",
        f"Head reviewed: {HEAD}\n| Reviewer | Round | Verdict |\n|---|---|---|\n| Codex | r2 | REJECT |",
        f"Head reviewed: {HEAD}\n- Round 2\n    Codex: REJECT — X",
        f"Head reviewed: {HEAD}\n> Codex r2: REJECT — X",
        f"Head reviewed: {HEAD}\n- [ ] Codex r2: REJECT — X",
    ],
)
def test_r5_r6_a_reject_on_a_line_skipped_for_accepts_still_withdraws(body):
    assert _status3002(_codex_accept_then(body)) == "MISSING_CROSS_MODEL"


def test_r5_r6_a_fenced_or_tabled_accept_still_does_not_count():
    for body in (f"Head {HEAD}\n```\nCodex ACCEPT@{HEAD}\n```", f"| Codex | ACCEPT@{HEAD} |"):
        assert _status3002([_c(body), _c(CLAUDE_AT_HEAD)]) == "MISSING_CROSS_MODEL"


@pytest.mark.parametrize(
    "line",
    [
        f"Codex r2: ACCEPT — reviewed 1a2b3c4d5, head is now {HEAD} (not reviewed)",
        f"Codex r2: ACCEPT, reviewed 4920381; head now {HEAD}",
    ],
)
def test_r5_r7_an_accept_on_a_line_naming_an_older_sha_and_the_head_is_not_bound(line):
    assert _status3002([_c(line), _c(CLAUDE_AT_HEAD)]) == "MISSING_CROSS_MODEL"


def test_r5_r7_an_accept_bound_by_its_own_sha_still_counts():
    line = f"Codex r2: ACCEPT@{HEAD} (r1 at 1a2b3c4d5 was fixed)"
    assert _status3002([_c(line), _c(CLAUDE_AT_HEAD)]) == "OK"


@pytest.mark.parametrize(
    "body",
    [
        f"**Codex review** (fix in progress)\nVerdict: REJECT at {HEAD} — race in X",
        f"### Codex review (pending)\nVerdict: REJECT at {HEAD} — race in X",
        f"**Codex r2 fix in progress**: REJECT@{HEAD} — race in X",
    ],
)
def test_r5_3004_a_status_label_on_the_header_line_does_not_drop_a_reject(body):
    assert _status3002(_codex_accept_then(body)) == "MISSING_CROSS_MODEL"


def test_r5_3004_a_disabled_header_under_a_claude_section_withdraws_both_families():
    body = (
        f"Head reviewed: {HEAD}\n**Claude review** (Opus)\n- Verdict: ACCEPT\n"
        "**Codex review** (fix in progress)\nVerdict: REJECT — race in X\n"
    )
    report = rrc.evaluate(HEAD, RISKY, [_c(f"Codex ACCEPT@{HEAD}"), _c(body)], [])
    assert report["status"] == "MISSING_RECORD"


def test_r5_r2_a_reject_under_an_older_short_head_label_is_about_that_commit():
    body = f"Head reviewed: {R_OLD[:7]}\nCodex r2: REJECT — race in X\nPushed a fix; head is now {HEAD}.\n"
    assert _status3002(_codex_accept_then(body)) == "OK"


def test_r5_r7_an_accept_at_head_carried_from_identical_content_still_counts():
    # #2697's carried record: the verdict names the head itself; the older sha is an aside.
    body = (
        f"- Claude (Opus) independent review — Verdict: ACCEPT at head {HEAD} "
        "(reviewed content identical to 18de0befa)\n"
        f"- Codex adversarial review r3 — Verdict: ACCEPT at head {HEAD} "
        "(reviewed content identical to 18de0befa)\n"
    )
    assert _status3002([_c(body)]) == "OK"


# -- r5 review round 1: a REJECT whose line names the head, prose after at/on -----------

H9 = HEAD[:9]


@pytest.mark.parametrize(
    "body",
    [
        f"Codex r2 REJECT ({HEAD}): race",
        f"**Codex adversarial review**\n- Verdict: REJECT ({H9}) — race in X",
        f"Codex r2: REJECT — the fix in {H9} reintroduces the race",
        f"**Codex review**: REJECT — reviewed {HEAD}, race in X",
        f"**Codex review**\nVERDICT: REJECT — race. Reviewed {HEAD}.",
        f"Claude ACCEPT@{HEAD}\n**Codex review** r2: REJECT — {HEAD} breaks X",
    ],
)
def test_r5_rr1_a_reject_whose_line_names_the_head_withdraws(body):
    assert _status3002(_codex_accept_then(body)) == "MISSING_CROSS_MODEL"


def test_r5_rr1_a_claude_reject_whose_line_names_the_head_withdraws():
    comments = [
        _c(OPUS_RECORD),
        _c(f"**Independent Claude review** (Opus): REJECT — {HEAD} breaks X"),
    ]
    assert rrc.evaluate(HEAD, DOCS, comments, [])["status"] == "MISSING_RECORD"


@pytest.mark.parametrize(
    "body",
    [
        f"Head reviewed: {HEAD}\nCodex r2: REJECT on ed25519 verification — the key is never checked",
        f"Head reviewed: {HEAD}\nCodex r2: REJECT at deadbeef sentinel handling",
        f"Head reviewed: {HEAD}\n**Codex review (ed25519 signer)**: REJECT — the key is never checked",
        f"Head reviewed: {HEAD}\nCodex (run 20261031) r2: REJECT — race",
    ],
)
def test_r5_rr1_a_finding_word_after_at_or_in_the_label_does_not_unbind(body):
    assert _status3002(_codex_accept_then(body)) == "MISSING_CROSS_MODEL"


def test_r5_rr1_a_claude_reject_on_a_finding_word_withdraws():
    comments = [_c(OPUS_RECORD), _c(f"Head reviewed: {HEAD}\nOpus r2: REJECT on ed25519 path")]
    assert rrc.evaluate(HEAD, DOCS, comments, [])["status"] == "MISSING_RECORD"


@pytest.mark.parametrize(
    "body",
    [
        f"Head reviewed: {HEAD}\nCodex r1: REJECT at 1a2b3c4d5.",
        f"Head reviewed: {HEAD}\nCodex r1: REJECT on 1a2b3c4d5 — race",
        f"Head reviewed: {HEAD}\nCodex r1 1a2b3c4d5: REJECT — race",
    ],
)
def test_r5_rr1_a_reject_bound_to_an_older_sha_stays_with_it(body):
    assert _status3002(_codex_accept_then(body)) == "OK"


def test_r5_rr1_header_named_reviewers_without_a_model_on_the_label_are_never_the_same():
    comments = [
        _c(f"Head reviewed: {HEAD}\n### Review (Codex)\nr3: ACCEPT"),
        _c(f"Head reviewed: {HEAD}\n### Review (Gemini)\nr1: REJECT — data loss"),
        _c(CLAUDE_AT_HEAD),
    ]
    assert _status3002(comments) == "MISSING_CROSS_MODEL"


def test_r5_rr1_a_big_number_on_an_accept_line_is_not_a_sha():
    body = (
        f"## Review record — Claude (claude-opus-5-5), head {HEAD}\n"
        "- Verdict: **ACCEPT** (317 passed, 1234567 assertions)\n"
    )
    assert rrc.evaluate(HEAD, DOCS, [_c(body)], [])["status"] == "OK"


@pytest.mark.parametrize(
    "line", ["- 4920381: **ACCEPT**", "Codex (4920381): ACCEPT", "Codex `4920381` ACCEPT"]
)
def test_r5_rr1_an_all_digit_older_sha_in_a_label_does_not_bind_an_accept(line):
    body = f"Head reviewed: {HEAD}\n**Codex review**\n{line}\n"
    assert _status3002([_c(body), _c(CLAUDE_AT_HEAD)]) == "MISSING_CROSS_MODEL"


# -- r5 review round 2: an ACCEPT line naming any other sha-like run binds nothing ------


@pytest.mark.parametrize(
    "line",
    [
        "**Codex review**: ACCEPT for 492038155",
        "**Codex review**: ACCEPT (last run against 492038155)",
        "Codex r2: ACCEPT, reviewing 492038155",
        "Codex r2: ACCEPT 492038155",
        "Codex r2: ACCEPT — fixed in 492038155123",
        "**Codex review**: ACCEPT for 4920381",
    ],
)
def test_r5_rr2_an_all_digit_older_sha_anywhere_on_the_line_does_not_bind(line):
    body = f"Head reviewed: {HEAD}\n{line}\n"
    assert _status3002([_c(body), _c(CLAUDE_AT_HEAD)]) == "MISSING_CROSS_MODEL"


def test_r5_rr2_an_all_digit_word_ending_a_reject_label_does_not_unbind_it():
    body = f"Head reviewed: {HEAD}\nCodex r2 4920381: REJECT — race"
    assert _status3002(_codex_accept_then(body)) == "MISSING_CROSS_MODEL"


_OLD_SHAS = (
    "1a2b3c4",
    "4920381",
    "49203815",
    "492038155",
    "492038155123",
    "1a2b3c4d5e6f",
    OLD,
    "1234567890" * 4,
)
_ACCEPT_WITH_OLD = (
    "Codex r2 @{x}: ACCEPT",
    "Codex r2 ({x}): ACCEPT",
    "- {x}: **ACCEPT**",
    "Codex r2: ACCEPT@{x}",
    "Codex r2: ACCEPT at head {x}",
    "**Codex review**: ACCEPT for {x}",
    "**Codex review**: ACCEPT (last run against {x})",
    "Codex r2: ACCEPT, reviewing {x}",
    "Codex r2: ACCEPT {x}",
    "Codex r2: ACCEPT — fixed in {x}",
    "Codex r2: ACCEPT `{x}`",
    "Codex r2: ACCEPT; {x}",
    "Codex r2: ACCEPT — reviewed {x}, head is now {h}",
    "Codex r2: ACCEPT ({x} and {h})",
)
_REJECT_WORDS = (
    HEAD,
    HEAD[:9],
    HEAD[:7],
    "ed25519",
    "deadbeef",
    "1234567",
    "20261031",
    "492038155",
)
_REJECT_SHAPES = (
    "Codex r2: REJECT — {w}",
    "Codex r2 REJECT ({w}): race",
    "Codex r2: REJECT on {w} path",
    "Codex r2: REJECT at {w} handling",
    "Codex r2: REJECT — the fix in {w} reintroduces the race",
    "Codex r2: REJECT — reviewed {w}, race",
    "**Codex review** ({w} signer): REJECT — x",
    "| Codex | r2 | REJECT | {w} |",
    "> Codex r2: REJECT — {w}",
    "Codex r2: REJECT — race. Reviewed {w}.",
    "- Codex r2: REJECT (see {w})",
)


def test_r5_rr2_binding_matrix_fails_closed():
    # An ACCEPT whose line names an older sha anywhere never binds to the head; a REJECT
    # whose line binds it to no older commit is never dropped.
    wrong = []
    for shape in _ACCEPT_WITH_OLD:
        for old in _OLD_SHAS:
            for header in ("", "**Codex review**\n"):
                body = f"Head reviewed: {HEAD}\n{header}{shape.format(x=old, h=HEAD)}\n"
                if _status3002([_c(body), _c(CLAUDE_AT_HEAD)]) == "OK":
                    wrong.append(body)
    for shape in _REJECT_SHAPES:
        for word in _REJECT_WORDS:
            for header in ("", "**Codex review**\n"):
                body = f"Head reviewed: {HEAD}\n{header}{shape.format(w=word)}\n"
                if _status3002(_codex_accept_then(body)) == "OK":
                    wrong.append(body)
    assert wrong == []


def test_r5_rr2_a_nine_digit_run_is_a_sha_even_before_a_unit():
    # Only a 7-8 digit count before its unit is not a sha; 9+ digits are a sha as on main.
    body = f"Head reviewed: {HEAD}\nCodex r2: ACCEPT (317 passed, 492038155 assertions)\n"
    assert _status3002([_c(body), _c(CLAUDE_AT_HEAD)]) == "MISSING_CROSS_MODEL"


# -- burn r10 04 (refs #3011): REJECT shapes that were silently dropped ----------------


@pytest.mark.parametrize(
    ("files", "comments", "status"),
    [
        # The comment names the head only in an ACCEPT@<sha> binding, not after "head".
        (DOCS, [f"Claude: ACCEPT@{HEAD}\nClaude r2: REJECT — a regression\n"], "MISSING_RECORD"),
        (
            RISKY,
            [f"Codex r1 ACCEPT@{HEAD}\nCodex r2: REJECT — data-loss bug\n", CLAUDE_AT_HEAD],
            "MISSING_CROSS_MODEL",
        ),
        # A later ACCEPT of an EARLIER round does not answer the REJECT.
        (
            DOCS,
            [f"Claude r2: ACCEPT@{HEAD}\nClaude r3: REJECT — a regression\nClaude r1: ACCEPT\n"],
            "MISSING_RECORD",
        ),
        # Nor does a later ACCEPT by another reviewer.
        (
            RISKY,
            [
                f"Codex r1 ACCEPT@{HEAD}\nCodex r2: REJECT — race\nGemini r3: ACCEPT\n",
                CLAUDE_AT_HEAD,
            ],
            "MISSING_CROSS_MODEL",
        ),
    ],
)
def test_a_bare_reject_in_a_comment_naming_the_head_only_in_a_binding_withdraws(
    files, comments, status
):
    assert rrc.evaluate(HEAD, files, [_c(body) for body in comments], [])["status"] == status


def test_a_bare_reject_under_a_head_label_for_another_commit_stays_there():
    body = f"Head reviewed: {OLD[:9]}\nCodex r1: REJECT — race\n\nCodex r2: ACCEPT@{HEAD}\n"
    assert rrc.evaluate(HEAD, RISKY, [_c(body), _c(CLAUDE_AT_HEAD)], [])["status"] == "OK"


def test_a_later_round_by_the_same_reviewer_answers_a_bare_reject():
    body = f"Claude r1: ACCEPT@{HEAD}\nClaude r2: REJECT — a regression\nClaude r3: ACCEPT\n"
    assert rrc.evaluate(HEAD, DOCS, [_c(body)], [])["status"] == "OK"


@pytest.mark.parametrize(
    "reason",
    [
        "because the lock is never released",
        "with two findings",
        "due to a race in the writer",
        "since the receipt is unsigned",
        "for missing tests",
        "data loss on retry",
    ],
)
def test_a_reject_followed_by_its_reason_withdraws(reason):
    claude = [
        _c(f"Head reviewed: {HEAD}\n**Claude review** (Opus)\nVerdict: ACCEPT\n"),
        _c(f"Head reviewed: {HEAD}\n**Claude review** (Opus) r2\nVerdict: REJECT {reason}\n"),
    ]
    assert rrc.evaluate(HEAD, DOCS, claude, [])["status"] == "MISSING_RECORD"
    codex = f"Head reviewed: {HEAD}\nCodex r1: ACCEPT\nCodex r2: REJECT {reason}\n"
    report = rrc.evaluate(HEAD, RISKY, [_c(codex), _c(CLAUDE_AT_HEAD)], [])
    assert report["status"] == "MISSING_CROSS_MODEL"


@pytest.mark.parametrize(
    "line",
    [
        "- Gate: REJECT is returned for an unsigned receipt.",
        "- REJECT items were all fixed in the last round.",
        "- REQUEST_CHANGES reviews are not read by the gate.",
        "- The REJECT path now logs the reason.",
    ],
)
def test_a_reject_word_used_as_a_value_in_prose_is_not_a_verdict(line):
    assert rrc.evaluate(HEAD, DOCS, [_c(OPUS_RECORD + line + "\n")], [])["status"] == "OK"


@pytest.mark.parametrize(
    "line",
    [
        # Replayed honest shapes (#2959, cairnwork#289, cairnwork#448).
        "- r1: ACCEPT, superseded by the Claude r1 REJECT finding, which Gemini missed.",
        "Rounds above (Claude r1-r4 REJECT then r5 ACCEPT).",
        "- Claude R2 REJECT / Codex R2 nit 1, a missing guard: fixed in c919c6d.",
    ],
)
def test_a_reject_word_in_a_history_or_disposition_note_is_not_a_verdict(line):
    body = f"Head reviewed: {HEAD}\n**Claude review** (Opus)\nVerdict: ACCEPT\n{line}\n"
    assert rrc.evaluate(HEAD, DOCS, [_c(body)], [])["status"] == "OK"


def test_a_round_history_item_fixed_later_on_its_line_keeps_the_accept():
    # cairnwork#296: the comment names the head only in ACCEPT@<sha>; each REJECT item
    # names the commit that fixed it at the end of its line.
    body = (
        f"## Independent review (Claude Opus)\nVerdict: ACCEPT@{HEAD}\n"
        "- R1 — REJECT: an import-root bypass, reproduced. fixed in f638ca3 + a test.\n"
        "- R3 — REJECT: another vector; verified and fixed in 4dca238.\n"
    )
    assert rrc.evaluate(HEAD, DOCS, [_c(body)], [])["status"] == "OK"


@pytest.mark.parametrize(
    "body",
    [
        # Not fixed: still open.
        f"Claude: ACCEPT@{HEAD}\nClaude r2: REJECT — a regression, not fixed in f638ca3\n",
        # The fix belongs to the next verdict on the line, not to this REJECT.
        f"Claude: ACCEPT@{HEAD}\nClaude r2: REJECT — race; r1 REJECT — leak fixed in f638ca3\n",
        # A REJECT main already read (bound by its own sha, punctuation after it) is not
        # closed by a fix named later on its line: never looser than main.
        f"Claude: ACCEPT@{HEAD}\nClaude r2: REJECT@{HEAD}: a regression; fixed in f638ca3\n",
    ],
)
def test_a_later_fix_closes_only_a_weak_reject_and_only_its_own(body):
    assert rrc.evaluate(HEAD, DOCS, [_c(body)], [])["status"] == "MISSING_RECORD"


@pytest.mark.parametrize(
    ("files", "body", "status"),
    [
        # Only a REJECT main did not read can be answered: one bound to the head by its
        # own sha stays open under a later ACCEPT that is not bound itself.
        (
            DOCS,
            f"Claude r1: ACCEPT@{HEAD}\nClaude r2 @{HEAD[:9]}: REJECT — a regression\n"
            "Claude r3: ACCEPT\n",
            "MISSING_RECORD",
        ),
        (
            DOCS,
            f"Claude r1: ACCEPT@{HEAD}\nClaude r2: REJECT@{HEAD[:9]} — a regression\n"
            "Claude r3: ACCEPT\n",
            "MISSING_RECORD",
        ),
        # The answer must be a later round ...
        (
            DOCS,
            f"Claude r1: ACCEPT@{HEAD}\nClaude r2: REJECT — a regression\nClaude r2: ACCEPT\n",
            "MISSING_RECORD",
        ),
        # ... listed after the REJECT ...
        (
            DOCS,
            f"Claude r1: ACCEPT@{HEAD}\nClaude r3: ACCEPT\nClaude r2: REJECT — a regression\n",
            "MISSING_RECORD",
        ),
        # ... of the same family.
        (
            RISKY,
            f"Codex r1 ACCEPT@{HEAD}\nCodex r2: REJECT — race\nClaude r3: ACCEPT\n",
            "MISSING_CROSS_MODEL",
        ),
    ],
)
def test_an_answer_closes_only_a_weak_reject_by_a_later_round_of_the_same_reviewer(
    files, body, status
):
    comments = [_c(body)] + ([_c(CLAUDE_AT_HEAD)] if files is RISKY else [])
    assert rrc.evaluate(HEAD, files, comments, [])["status"] == status


@pytest.mark.parametrize(
    "rest",
    [
        "is returned for an unsigned receipt.",
        "items were all fixed.",
        "reviews are not read by the gate.",
        "finding was a false alarm.",
        "then r3 ACCEPT.",
        "/ nit 1, a missing guard.",
    ],
)
def test_a_prose_word_right_after_the_token_decides_alone(rest):
    # Label and position both pass ("Claude r2: REJECT"), so only the word after the
    # token keeps the line from reading as a verdict.
    body = f"Head reviewed: {HEAD}\n**Claude review** (Opus)\nVerdict: ACCEPT\nClaude r2: REJECT {rest}\n"
    assert rrc.evaluate(HEAD, DOCS, [_c(body)], [])["status"] == "OK"


@pytest.mark.parametrize(
    "reason",
    [
        "path traversal in the writer",
        "status: the lease is never released",
        "case-sensitive match lets a renamed file through",
        "result cache is never invalidated",
        "token leak in the log",
        "branch protection bypass",
    ],
)
def test_a_reject_reason_starting_with_a_noun_withdraws(reason):
    # Only words honest records were seen to use after the token make it prose; a reason
    # that happens to start with another noun is still a verdict.
    claude = [
        _c(f"Head reviewed: {HEAD}\n**Claude review** (Opus)\nVerdict: ACCEPT\n"),
        _c(f"Head reviewed: {HEAD}\n**Claude review** (Opus) r2\nVerdict: REJECT {reason}\n"),
    ]
    assert rrc.evaluate(HEAD, DOCS, claude, [])["status"] == "MISSING_RECORD"
    codex = f"Head reviewed: {HEAD}\nCodex r1: ACCEPT\nCodex r2: REJECT {reason}\n"
    report = rrc.evaluate(HEAD, RISKY, [_c(codex), _c(CLAUDE_AT_HEAD)], [])
    assert report["status"] == "MISSING_CROSS_MODEL"


# -- #3039 follow-up: a REJECT is judged where it stands, not at an earlier same-text clause


@pytest.mark.parametrize(
    "body",
    [
        # The earlier clause of the same text is not read (a prose word follows its token)
        # and carries a fix note; the later one is a verdict main read.
        f"Head reviewed: {HEAD}\nClaude r1: ACCEPT\n"
        "Claude: REJECT items from r1 fixed in abc1234; Claude: REJECT — a new data-loss bug\n",
        # The same, closed through the answer rule instead of a fix note.
        f"Head reviewed: {HEAD[:7]}\nClaude r1: ACCEPT@{HEAD}\n"
        "Claude r2: REJECT finding noted; Claude r2: REJECT — data loss\nClaude r3: ACCEPT\n",
    ],
)
def test_a_reject_is_judged_at_its_own_position_on_the_line(body):
    assert rrc.evaluate(HEAD, DOCS, [_c(body)], [])["status"] == "MISSING_RECORD"
    codex = body.replace("Claude", "Codex")
    report = rrc.evaluate(HEAD, RISKY, [_c(codex), _c(CLAUDE_AT_HEAD)], [])
    assert report["status"] == "MISSING_CROSS_MODEL"


def test_a_reject_also_counts_for_the_family_read_where_its_text_first_appears():
    # Before #3039 the bare REJECT below was placed at the same text inside the Claude
    # clause and withdrew Claude's ACCEPT; read at its own position it is Codex's. Both
    # readings count (fail closed), so the record stays missing as it was.
    body = (
        f"Head reviewed: {HEAD}\nClaude r1: ACCEPT\n"
        "Claude r3: REJECT — fixed in f638ca3; Codex r3: ACCEPT@8d70e3f; REJECT — data loss\n"
    )
    assert rrc.evaluate(HEAD, DOCS, [_c(body)], [])["status"] == "MISSING_RECORD"


@pytest.mark.parametrize(
    "body",
    [
        # Read at its first same-text place the REJECT is Opus's; at its own place,
        # Claude's. No later Claude round may answer it.
        f"Head reviewed: {HEAD}\nClaude r3: ACCEPT\nOpus, r2: REJECT, fixed, Claude, r2: REJECT\n",
        # The fix note follows only the earlier same-text clause, not this (weak) REJECT.
        f"Claude r1: ACCEPT@{HEAD}\n"
        "Claude: REJECT items fixed in abc1234; Claude: REJECT — the lock leaks\n",
    ],
)
def test_a_reject_read_at_two_places_is_neither_answered_nor_fixed_from_the_other(body):
    assert rrc.evaluate(HEAD, DOCS, [_c(body)], [])["status"] == "MISSING_RECORD"


def test_a_reject_still_counts_for_the_family_read_at_its_own_position():
    # The bare REJECT is Codex's where it stands (after "Codex r3: ACCEPT"), and Claude's
    # where its text first appears: both ACCEPTs are withdrawn.
    body = (
        f"Head reviewed: {HEAD}\nClaude r1: ACCEPT\n"
        "Claude r3: REJECT — fixed in f638ca3; Codex r3: ACCEPT@8d70e3f; REJECT — data loss\n"
    )
    report = rrc.evaluate(HEAD, RISKY, [_c(body), _c(CLAUDE_AT_HEAD)], [])
    assert report["status"] == "MISSING_CROSS_MODEL"


# -- #3040: a round marker inside a label's parenthetical is part of the aside ---------

_DELTA = f"{OLD}..{HEAD}"


@pytest.mark.parametrize(
    "label",
    [
        # #3029's round-3 record shape.
        f"(Claude Haiku 5.5, separate agent; Round 3, delta only `{_DELTA}`)",
        "(Claude Opus 5.5; r2, docs-only delta)",
    ],
)
def test_a_round_marker_inside_a_label_aside_keeps_an_honest_accept(label):
    body = f"## Review record — head `{HEAD}`\n**Independent Claude review** {label}: **ACCEPT at {HEAD}**\n"
    assert rrc.evaluate(HEAD, DOCS, [_c(body)], [])["status"] == "OK"


@pytest.mark.parametrize(
    "line",
    [
        # Denials outside the aside, or in the verdict's own clause, still deny.
        f"**Claude review** (Opus; Round 3): not ACCEPT at {HEAD}",
        f"**Claude review** (Opus; Round 3): ACCEPT at {HEAD} only if CI passes",
        f"**Claude review** r2 not fixed, (Opus; Round 3): ACCEPT at {HEAD}",
        f"**Claude review** (Opus; Round 3), awaiting ACCEPT at {HEAD}",
        # A label the aside disables is still disabled.
        f"**Claude review** (not run; Round 3): ACCEPT at {HEAD}",
        # An unclosed parenthesis is no aside.
        f"**Claude review** (Opus; Round 3, not yet: ACCEPT at {HEAD}",
    ],
)
def test_a_round_marker_inside_an_aside_does_not_hide_a_denial(line):
    assert rrc.evaluate(HEAD, DOCS, [_c(line + "\n")], [])["status"] != "OK"


@pytest.mark.parametrize(
    "label",
    [
        "(r2 not fixed)",
        "(Round 2 REJECT still open)",
        "(Opus; round 3, not yet re-run)",
        "(Opus; round 3, cannot merge yet)",
        "(Opus; round 3, pending CI)",
        '(Opus; round 3, "approved" by the author)',
    ],
)
def test_a_denial_inside_a_round_marked_aside_still_denies(label):
    # Only the scope word "only" and an apostrophe stop denying inside such an aside.
    body = f"## Review record — head `{HEAD}`\n**Independent Claude review** {label}: **ACCEPT at {HEAD}**\n"
    assert rrc.evaluate(HEAD, DOCS, [_c(body)], [])["status"] != "OK"


def test_an_apostrophe_inside_a_round_marked_aside_is_no_quote():
    # cairnwork#257's round-4 record shape.
    label = "(separate agent; round 4, a confirmation of round 3's items beyond the usual cap)"
    body = f"## Review record — head `{HEAD}`\n**Independent Claude review** {label}: **ACCEPT at {HEAD}**\n"
    assert rrc.evaluate(HEAD, DOCS, [_c(body)], [])["status"] == "OK"


def test_a_round_history_inside_an_aside_is_read_from_its_last_round():
    # cairnwork#268's record shape: the aside's earlier round was a REJECT, its last an
    # ACCEPT; as on main, only the words from the last round marker on are checked.
    label = "(Claude Opus 5.5, separate agent; round 1 at 6ed031de REJECT, delta round 2)"
    body = f"## Review record — head `{HEAD}`\n**Independent Claude review** {label}: **ACCEPT at {HEAD}**\n"
    assert rrc.evaluate(HEAD, DOCS, [_c(body)], [])["status"] == "OK"


@pytest.mark.parametrize(
    "label",
    [
        # Each is the only denial in its aside, so each check is pinned on its own.
        "(Opus; round 3, only once CI is green)",
        "(Opus; round 3, only-if the rebase is clean)",
        "(Opus; round 3, only after the rebase)",
        "(Opus; round 3, only-after the rebase)",
        "(Opus; round 3, only\u2010after the rebase)",
        "(Opus; round 3, only, once CI is green)",
        "(Opus; round 3, only)",
        "(Opus; round 3, once CI is green, test-only)",
        "(Opus; round 3, when only)",
        "(Opus; round 3, subject to CI, delta only a1b2c3d..e4f5a6b)",
        "(Opus; round 3, only subject to CI passing)",
        "(Opus; round 3, only with CI green)",
        "(Opus; round 3, only: CI green)",
        "(Opus; round 3, only (CI green))",
        "(Opus; round 3 only, once CI is green)",
        "(Opus; round 3, delta only a1b2c3d..e4f5a6b, once CI is green)",
        "(Opus; round 3, test-only, once CI is green)",
        "(Opus; round 3 (not fixed))",
        "(Opus; round 3, Verdict: REJECTION)",
        # A REJECT in an earlier segment of the aside: no other check reaches it.
        "(Opus; round 3, REJECT items open, delta)",
        '(Opus; round 3, "approved")',
        "(Opus; round 3, “approved”)",
    ],
)
def test_each_denial_inside_a_round_marked_aside_denies_alone(label):
    body = f"## Review record — head `{HEAD}`\n**Independent Claude review** {label}: **ACCEPT at {HEAD}**\n"
    assert rrc.evaluate(HEAD, DOCS, [_c(body)], [])["status"] != "OK"


def test_many_round_markers_in_asides_stay_linear():
    # Thousands of markers inside asides on one line: one pass per line, not per marker.
    line = "(" + " r1" * 4000 + ") " * 1 + "(" + " r2" * 4000 + ")"
    started = time.monotonic()
    rrc.verdict_clauses(f"**Claude review** {line}: ACCEPT at {HEAD}")
    assert time.monotonic() - started < 2.0


def test_deeply_nested_asides_stay_linear():
    line = "(r1 " * 3000 + ")" * 3000
    started = time.monotonic()
    rrc.verdict_clauses(f"**Claude review** {line}: ACCEPT at {HEAD}")
    assert time.monotonic() - started < 2.0


@pytest.mark.parametrize(
    "label",
    [
        "(Opus; round 3, valid on green CI only)",
        "(Opus; round 3, on approval only)",
        "(Opus; round 3, for merge only)",
        "(Opus; round 3, test-only delta, more to come)",
        "(Opus; round 3, test-only delta delta)",
        "(Opus; round 3, pre-test-only delta)",
        "(Opus; round 3, docs-only, then merge)",
        "(Opus; round 3, delta only a1b2c3d)",
        "(Opus; round 3, delta only a1b2c3d..e4f5a6b and the rest)",
        "(Opus; round 3, delta only a1b2c3d..e4f5a6b?)",
        "(Opus; round 3, ok? test-only delta)",
        "(Opus; round 3, merge-only)",
        "(Opus; round 3, given CI green, test-only delta)",
        "(Opus; round 3, tentatively docs-only)",
        "(Opus; round 3, delta only later..e4f5a6b)",
        "(Opus; round 3, docs-only once)",
        "(Opus; round 3, merge only a1b2c3d..e4f5a6b)",
        "(Opus; round 3, docs only)",
        "(Opus; r3-once docs-only)",
        "(Opus; round 3? docs-only)",
        "(Opus; round 3! docs-only)",
        "(Opus; round 3's items, subject to CI)",
        "(Opus; round 3, with CI green, test-only)",
        "(Opus; round 3, merge only)",
    ],
)
def test_only_outside_the_fixed_scope_phrases_at_the_aside_end_denies(label):
    body = f"## Review record — head `{HEAD}`\n**Independent Claude review** {label}: **ACCEPT at {HEAD}**\n"
    assert rrc.evaluate(HEAD, DOCS, [_c(body)], [])["status"] != "OK"


@pytest.mark.parametrize(
    "phrase",
    [
        "docs-only",
        "test-only delta",
        "typing-only delta",
        "delta-only",
        "delta only a1b2c3d..e4f5a6b",
    ],
)
def test_each_fixed_scope_phrase_at_the_aside_end_keeps_an_honest_accept(phrase):
    body = f"## Review record — head `{HEAD}`\n**Independent Claude review** (Opus; round 3, {phrase}): **ACCEPT at {HEAD}**\n"
    assert rrc.evaluate(HEAD, DOCS, [_c(body)], [])["status"] == "OK"


@pytest.mark.parametrize(
    "condition",
    [
        "once CI is green",
        "when CI is green",
        "after the rebase",
        "with CI green",
        "green?",
        "provided CI passes",
        "upon CI passing",
        "assuming CI passes",
        "as long as CI passes",
        "till CI passes",
        "on condition CI passes",
        "conditionally",
    ],
)
def test_an_apostrophe_is_a_quote_again_in_an_aside_stating_a_condition(condition):
    label = f"(Opus; round 3's items, {condition})"
    body = f"## Review record — head `{HEAD}`\n**Independent Claude review** {label}: **ACCEPT at {HEAD}**\n"
    assert rrc.evaluate(HEAD, DOCS, [_c(body)], [])["status"] != "OK"


@pytest.mark.parametrize(
    "label", ["(Opus; round 3 docs-only)", "(Opus; round 3 , docs-only)", "(Opus; r3: docs-only)"]
)
def test_the_scope_phrase_may_follow_the_marker_after_a_space_comma_or_colon(label):
    body = f"## Review record — head `{HEAD}`\n**Independent Claude review** {label}: **ACCEPT at {HEAD}**\n"
    assert rrc.evaluate(HEAD, DOCS, [_c(body)], [])["status"] == "OK"
