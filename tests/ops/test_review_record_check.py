"""Review record present (#2290): the advisory check and its workflow."""

from __future__ import annotations

import json
import urllib.error
from pathlib import Path

import yaml

from scripts.ops import review_record_check as rrc

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "review-record-present.yml"
TOKEN = "tok" + "en-" + "R" * 20
HEAD = "8d70e3ff83eb16c7b1f4af93ae9d87e01d5fe129"
OLD = "1e9f3d4ec0000000000000000000000000000000"

# Real record shapes posted on 2026-10-15 (#2285, #2279, #2263).
OPUS_RECORD = (
    "## Review record — Claude (claude-opus-5-5), session bundle-C-nightly\n\n"
    f"- Head reviewed: `{HEAD}`\n- Verdict: **ACCEPT**\n- Scope: test-only.\n"
)
SHORT_RECORD = "**Claude review** (Claude Opus 5.5): **ACCEPT@8d70e3ff8**.\n"
CODEX_RECORD = (
    f"**Codex adversarial review**, 3 rounds: r1 REJECT (fixed), r2 REJECT (fixed), "
    f"**r3 ACCEPT@{HEAD}**.\n"
)
CODEX_REBUTTAL = (
    f"Review record for the final head {HEAD}.\n\n**Adversarial review (Codex, 17 rounds):** "
    "rounds 1-16 fixed. Round 17 (REJECT) is **rebutted, not fixed**: cap reached.\n"
)


def _comment(body: str) -> dict:
    return {"body": body, "user": {"login": "james3014-nexus-agent[bot]"}}


def _file(name: str) -> dict:
    return {"filename": name, "status": "modified"}


def _fake(pull=None, files=(), comments=(), reviews=(), calls=None):
    pull = pull if pull is not None else {"head": {"sha": HEAD}}

    def fetch(url, token):
        assert token == TOKEN
        if calls is not None:
            calls.append(url)
        if url.endswith("/pulls/7"):
            return pull
        page = int(url.rsplit("page=", 1)[1])
        for key, items in (("/files", files), ("/comments", comments), ("/reviews", reviews)):
            if f"/{key.strip('/')}?" in url:
                return list(items)[(page - 1) * 100 : page * 100]
        raise AssertionError(url)

    return fetch


def _posts():
    posted: list[tuple[str, dict]] = []

    def post(url, token, payload):
        assert token == TOKEN
        posted.append((url, payload))
        return {}

    return posted, post


# -- pure classification -------------------------------------------------------


def test_names_head_accepts_full_sha_and_prefix_of_nine_or_more():
    assert rrc.names_head(f"ACCEPT at {HEAD}", HEAD)
    assert rrc.names_head("ACCEPT@8d70e3ff8", HEAD)
    assert not rrc.names_head("ACCEPT@8d70e3ff", HEAD)  # 8 chars: too short
    assert not rrc.names_head(f"ACCEPT at {OLD}", HEAD)
    assert not rrc.names_head("ACCEPT at 8d70e3ff83eb16c7b1f4af93ae9d87e01d5fe12a", HEAD)


def test_classify_record_reads_verdict_families_and_rebuttal():
    opus = rrc.classify_record(OPUS_RECORD, HEAD)
    assert opus == {"verdict": True, "rebuttal_at_cap": False, "claude": True, "cross_model": False}
    codex = rrc.classify_record(CODEX_REBUTTAL, HEAD)
    assert codex == {
        "verdict": False,
        "rebuttal_at_cap": True,
        "claude": False,
        "cross_model": True,
    }
    assert rrc.classify_record("Codex accepted the rebuttal at " + OLD, HEAD) is None
    # A lowercase "accepted" is prose, not a verdict token.
    lower = rrc.classify_record(f"Codex accepted the rebuttal at {HEAD}", HEAD)
    assert lower is not None and lower["verdict"] is False


def test_high_risk_paths_follow_the_codex_review_list():
    files = [
        _file("nexus/research/foo.py"),
        _file(".github/workflows/lint.yml"),
        _file("uv.lock"),
        _file("nexus/orchestrator/self_hosted_task_service.py"),
        {"status": "removed"},
    ]
    assert rrc.high_risk_paths(files) == [
        ".github/workflows/lint.yml",
        "nexus/orchestrator/self_hosted_task_service.py",
        "uv.lock",
    ]
    assert rrc.high_risk_paths([_file("tests/ops/test_x.py"), _file("docs/a.md")]) == []


def test_evaluate_low_risk_needs_one_record_at_head():
    missing = rrc.evaluate(HEAD, [_file("docs/a.md")], [_comment("looks good " + OLD)], [])
    assert missing["status"] == "MISSING_RECORD" and missing["independent"] is False
    ok = rrc.evaluate(HEAD, [_file("docs/a.md")], [_comment(SHORT_RECORD)], [])
    assert ok["status"] == "OK" and ok["high_risk"] is False and ok["records_at_head"] == 1


def test_evaluate_record_for_an_older_head_does_not_count():
    old = OPUS_RECORD.replace(HEAD, OLD)
    report = rrc.evaluate(HEAD, [_file("docs/a.md")], [_comment(old)], [])
    assert report["status"] == "MISSING_RECORD" and report["records_at_head"] == 0


def test_evaluate_high_risk_needs_a_cross_model_record_too():
    files = [_file("scripts/ops/pr_impact_gate.py")]
    only_opus = rrc.evaluate(HEAD, files, [_comment(OPUS_RECORD)], [])
    assert only_opus["status"] == "MISSING_CROSS_MODEL"
    assert only_opus["high_risk_paths"] == ["scripts/ops/pr_impact_gate.py"]
    both = rrc.evaluate(HEAD, files, [_comment(OPUS_RECORD), _comment(CODEX_RECORD)], [])
    assert both["status"] == "OK" and both["cross_model"] is True
    rebutted = rrc.evaluate(HEAD, files, [_comment(OPUS_RECORD), _comment(CODEX_REBUTTAL)], [])
    assert rebutted["status"] == "OK"
    # A cross-model REJECT without a rebuttal at the cap is not a disposition.
    reject = _comment(f"Codex r1 REJECT@{HEAD}: two findings, fixing.")
    assert rrc.evaluate(HEAD, files, [_comment(OPUS_RECORD), reject], [])["status"] == (
        "MISSING_CROSS_MODEL"
    )


def test_evaluate_counts_a_submitted_approval_at_head():
    reviews = [{"state": "APPROVED", "commit_id": HEAD}]
    assert rrc.evaluate(HEAD, [_file("docs/a.md")], [], reviews)["status"] == "OK"
    stale = [{"state": "APPROVED", "commit_id": OLD}, {"state": "COMMENTED", "commit_id": HEAD}]
    assert rrc.evaluate(HEAD, [_file("docs/a.md")], [], stale)["status"] == "MISSING_RECORD"


# -- run: API, status publication, exit codes -----------------------------------------


def test_run_publishes_success_status_and_writes_report(tmp_path, capsys):
    posted, post = _posts()
    out = tmp_path / "report.json"
    rc = rrc.run(
        "o/r",
        7,
        TOKEN,
        _fake(files=[_file("docs/a.md")], comments=[_comment(OPUS_RECORD)]),
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
    rc = rrc.run("o/r", 7, TOKEN, _fake(files=[_file("docs/a.md")]), post)
    assert rc == 1
    assert posted[0][1]["state"] == "failure"
    assert "MISSING_RECORD" in capsys.readouterr().out


def test_run_no_fail_keeps_exit_zero_but_still_publishes_failure():
    posted, post = _posts()
    rc = rrc.run("o/r", 7, TOKEN, _fake(files=[_file("docs/a.md")]), post, fail_on_missing=False)
    assert rc == 0 and posted[0][1]["state"] == "failure"


def test_run_fails_closed_on_api_error_and_publishes_nothing(capsys):
    posted, post = _posts()

    def broken(url, token):
        raise urllib.error.URLError("down")

    assert rrc.run("o/r", 7, TOKEN, broken, post) == 1
    assert posted == []
    assert "ERROR" in capsys.readouterr().out


def test_run_fails_closed_when_head_is_not_a_sha():
    posted, post = _posts()
    assert rrc.run("o/r", 7, TOKEN, _fake(pull={"head": {"sha": "main"}}), post) == 1
    assert posted == []


def test_run_paginates_comments():
    posted, post = _posts()
    calls: list[str] = []
    comments = [_comment("noise")] * 100 + [_comment(OPUS_RECORD)]
    fetch = _fake(files=[_file("docs/a.md")], comments=comments, calls=calls)
    assert rrc.run("o/r", 7, TOKEN, fetch, post) == 0
    assert any("/comments?per_page=100&page=2" in c for c in calls)


def test_printed_lines_cannot_carry_workflow_commands(capsys):
    posted, post = _posts()
    hostile = _file("docs/::error::x\n##[command]y.md")
    rrc.run("o/r", 7, TOKEN, _fake(files=[hostile]), post)
    out = capsys.readouterr().out
    for line in out.splitlines():
        assert not line.lstrip().startswith("::")
        assert "##[" not in line
    assert "##[" not in posted[0][1]["description"]


def test_description_is_capped():
    report = {"status": "MISSING_RECORD", "reason": "x" * 500}
    assert len(rrc._description(report)) == rrc.MAX_DESCRIPTION


# -- workflow shape --------------------------------------------------------------------


def test_workflow_never_checks_out_pr_code_and_runs_the_script_isolated():
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    triggers = doc.get("on", doc.get(True))
    assert triggers["pull_request_target"]["types"] == ["opened", "synchronize", "reopened"]
    assert "issue_comment" in triggers and "pull_request_review" in triggers
    assert doc["permissions"] == {}
    (job,) = doc["jobs"].values()
    assert job["permissions"] == {"contents": "read", "pull-requests": "read", "statuses": "write"}
    checkout, check = job["steps"]
    assert checkout["with"]["ref"] == "${{ github.event.repository.default_branch }}"
    assert checkout["with"]["persist-credentials"] is False
    assert "python3 -I scripts/ops/review_record_check.py" in check["run"]
    assert "--no-fail" in check["run"] and "pull_request_target" in check["run"]
    assert "PYTHONPATH" not in check.get("env", {})
