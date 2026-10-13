"""Issue #1897: red governance signals open or update deduplicated Issue comments."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from scripts.ops import governance_signal_issue as signal

REPO = "James3014/Nexus-new"
REPO_ROOT = Path(__file__).resolve().parents[2]


class FakeGh:
    def __init__(self, issues: list[dict[str, Any]] | None = None) -> None:
        self.issues = issues or []
        self.comments: dict[int, list[str]] = {}
        self.calls: list[list[str]] = []

    def __call__(self, args: Sequence[str], stdin: str | None) -> str:
        args = list(args)
        self.calls.append(args)
        if args[:2] == ["issue", "list"]:
            return json.dumps(self.issues)
        if args[:2] == ["label", "create"]:
            return ""
        if args[:2] == ["issue", "create"]:
            number = 900 + len(self.issues)
            title = args[args.index("--title") + 1]
            self.issues.append({"number": number, "title": title})
            return f"https://github.com/{REPO}/issues/{number}\n"
        if args[0] == "api":
            number = int(args[2].split("/")[-2])
            return "".join(json.dumps(body) + "\n" for body in self.comments.get(number, []))
        if args[:2] == ["issue", "comment"]:
            self.comments.setdefault(int(args[2]), []).append(stdin or "")
            return ""
        raise AssertionError(f"unexpected gh call: {args}")


def test_nightly_creates_one_tracking_issue_then_reuses_it() -> None:
    gh = FakeGh()
    first = signal.report_nightly(REPO, "11", "https://run/11", "a" * 40, gh)
    second = signal.report_nightly(REPO, "12", "https://run/12", "b" * 40, gh)
    assert first["issue"] == second["issue"] == 900
    assert sum(call[:2] == ["issue", "create"] for call in gh.calls) == 1
    assert [c for c in gh.calls if c[:2] == ["issue", "create"]][0][-4:-2] == [
        "--label",
        signal.NIGHTLY_LABEL,
    ]
    bodies = gh.comments[900]
    assert len(bodies) == 2
    assert "https://run/11" in bodies[0] and "<!-- nexus-nightly-run:11 -->" in bodies[0]


def test_nightly_comment_is_deduplicated_per_run_id() -> None:
    gh = FakeGh([{"number": 5, "title": signal.NIGHTLY_TITLE}])
    assert signal.report_nightly(REPO, "7", "https://run/7", "a" * 40, gh)["commented"] is True
    assert signal.report_nightly(REPO, "7", "https://run/7", "a" * 40, gh)["commented"] is False
    assert len(gh.comments[5]) == 1
    assert not any(call[:2] == ["issue", "create"] for call in gh.calls)


def test_nightly_ignores_labelled_issues_with_a_different_title() -> None:
    gh = FakeGh([{"number": 5, "title": "something else"}])
    assert signal.report_nightly(REPO, "7", "https://run/7", "a" * 40, gh)["issue"] == 901


def _report(tmp_path: Path, payload: dict[str, Any]) -> Path:
    path = tmp_path / "report.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_golden_owner_flags_comment_once_per_distinct_flag_set(tmp_path: Path) -> None:
    gh = FakeGh()
    flagged = {
        "findings": [
            {"case_id": "GBF-002", "flags": ["OWNER_CLOSED_FINDING_OPEN"]},
            {"case_id": "GBF-003", "flags": []},
        ]
    }
    path = _report(tmp_path, flagged)
    first = signal.report_golden_owners(REPO, 117, path, "https://run/1", gh)
    again = signal.report_golden_owners(REPO, 117, path, "https://run/2", gh)
    assert first["commented"] is True and again["commented"] is False
    assert first["flagged"] == ["GBF-002:OWNER_CLOSED_FINDING_OPEN"]
    flagged["findings"][1]["flags"] = ["OWNER_STATE_UNKNOWN"]
    changed = signal.report_golden_owners(
        REPO, 117, _report(tmp_path, flagged), "https://run/3", gh
    )
    assert changed["commented"] is True
    assert len(gh.comments[117]) == 2


def test_golden_owner_without_flags_never_comments(tmp_path: Path) -> None:
    gh = FakeGh()
    path = _report(tmp_path, {"findings": [{"case_id": "GBF-001", "flags": []}]})
    assert signal.report_golden_owners(REPO, 117, path, "https://run/1", gh)["commented"] is False
    assert gh.calls == []


def test_golden_owner_checker_error_is_surfaced(tmp_path: Path) -> None:
    gh = FakeGh()
    path = _report(tmp_path, {"error": "corpus_findings_invalid"})
    result = signal.report_golden_owners(REPO, 117, path, "https://run/1", gh)
    assert result["commented"] is True
    assert result["flagged"] == ["REPORT_ERROR:corpus_findings_invalid"]


def _workflow(name: str) -> dict[Any, Any]:
    return yaml.safe_load((REPO_ROOT / ".github/workflows" / name).read_text(encoding="utf-8"))


def test_pytest_nightly_signal_job_is_isolated_and_schedule_only() -> None:
    workflow = _workflow("pytest.yml")
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["nightly-signal"]
    assert job["needs"] == "full-regression"
    assert job["if"] == (
        "always() && github.event_name == 'schedule' && needs.full-regression.result == 'failure'"
    )
    assert job["permissions"] == {"contents": "read", "issues": "write"}
    writers = [
        job_id
        for job_id, item in workflow["jobs"].items()
        if (item.get("permissions") or {}).get("issues") == "write"
    ]
    assert writers == ["nightly-signal"]
    checkout, report = job["steps"]
    assert checkout["with"]["persist-credentials"] is False
    assert "governance_signal_issue.py" in report["run"]
    assert "nightly --run-id" in report["run"]
    assert report["env"]["GH_TOKEN"] == "${{ secrets.GITHUB_TOKEN }}"


def test_golden_owner_workflow_is_scheduled_strict_and_comments_on_117() -> None:
    workflow = _workflow("golden-finding-owners.yml")
    triggers = workflow[True]  # PyYAML parses the `on` key as boolean True.
    assert set(triggers) == {"schedule", "workflow_dispatch"}
    assert workflow["permissions"] == {"contents": "read"}
    (job,) = workflow["jobs"].values()
    assert job["permissions"] == {"contents": "read", "issues": "write"}
    steps = {step.get("name"): step for step in job["steps"]}
    assert steps["Checkout exact head"]["with"]["persist-credentials"] is False
    assert (
        "scripts/ops/check_golden_finding_owners.py --strict"
        in steps["Check Golden finding owners"]["run"]
    )
    comment = steps["Comment flagged findings on owner Issue"]
    assert comment["if"] == "steps.check.outputs.status != '0'"
    assert "golden-owners --report" in comment["run"] and "--issue 117" in comment["run"]
    assert steps["Fail on flagged findings"]["if"] == "steps.check.outputs.status != '0'"
