from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ops import check_golden_finding_owners as owners
from tests.golden_behavior.corpus import CASES, FINDINGS

CORPUS = Path(__file__).with_name("corpus.py")

SYNTHETIC = """
from x import _c

SHARED = ("https://github.com/James3014/Nexus-new/issues/5",)

CASES = (
    _c("GB-001", "t", "invariant", "normal", "e", ("AGENTS.md",), ("tests/a.py::t",)),
    _c("GB-002", "t", "invariant", "normal", "e", SHARED, status="finding", finding_id="GBF-A"),
    _c("GB-003", "t", "invariant", "normal", "e", ("AGENTS.md",), status="finding", finding_id="GBF-B"),
    _c("GB-004", "t", "invariant", "normal", "e", ("AGENTS.md",), status="finding", finding_id="GBF-C"),
)

FINDINGS = {
    "GBF-A": "Issue #6 closed; see PR https://github.com/James3014/Nexus-new/pull/9 and A&#8 noise.",
    "GBF-B": "No owner Issue yet.",
    "GBF-C": "Owner #7 still open.",
}
"""


def _fake(states: dict[int, str], calls: list[int] | None = None):
    def fetch(number: int) -> dict[str, str | None]:
        if calls is not None:
            calls.append(number)
        if number not in states:
            raise RuntimeError("not found")
        state = states[number]
        return {
            "state": state,
            "stateReason": "COMPLETED" if state == "CLOSED" else None,
            "closedAt": "2026-08-17T03:51:10Z" if state == "CLOSED" else None,
        }

    return fetch


def _write(tmp_path: Path) -> Path:
    path = tmp_path / "corpus.py"
    path.write_text(SYNTHETIC, encoding="utf-8")
    return path


def test_collects_owner_issues_from_sources_and_finding_text(tmp_path: Path) -> None:
    cases, findings = owners.load_findings(_write(tmp_path))
    by_id = {case["case_id"]: owners.owner_issues(case, findings) for case in cases}
    assert by_id == {"GB-002": [5, 6], "GB-003": [], "GB-004": [7]}


def test_all_owners_closed_flags_open_finding(tmp_path: Path) -> None:
    calls: list[int] = []
    report = owners.build_report(
        _write(tmp_path), _fake({5: "CLOSED", 6: "CLOSED", 7: "OPEN"}, calls)
    )
    rows = {row["case_id"]: row for row in report["findings"]}
    assert rows["GB-002"]["flags"] == [owners.FLAG_OWNER_CLOSED]
    assert rows["GB-002"]["owner_issues"][0]["closedAt"] == "2026-08-17T03:51:10Z"
    assert rows["GB-003"]["flags"] == []
    assert rows["GB-004"]["flags"] == []
    assert report["flagged"] == ["GB-002"]
    assert sorted(calls) == [5, 6, 7]
    assert report["claim_ceiling"] == "OWNER_STATE_OBSERVATION_ONLY"


def test_partially_open_owners_do_not_flag(tmp_path: Path) -> None:
    report = owners.build_report(_write(tmp_path), _fake({5: "CLOSED", 6: "OPEN", 7: "OPEN"}))
    assert report["flagged"] == []


def test_fetch_failure_is_unknown_not_closed(tmp_path: Path) -> None:
    report = owners.build_report(_write(tmp_path), _fake({5: "CLOSED", 7: "OPEN"}))
    row = next(row for row in report["findings"] if row["case_id"] == "GB-002")
    assert row["flags"] == [owners.FLAG_OWNER_UNKNOWN]
    assert {issue["number"]: issue["state"] for issue in row["owner_issues"]} == {
        5: "CLOSED",
        6: "UNKNOWN",
    }


def test_report_mode_exits_zero_and_strict_exits_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    corpus = str(_write(tmp_path))
    fetch = _fake({5: "CLOSED", 6: "CLOSED", 7: "OPEN"})
    assert owners.main(["--corpus", corpus], fetcher=fetch) == 0
    assert json.loads(capsys.readouterr().out)["flagged"] == ["GB-002"]
    assert owners.main(["--corpus", corpus, "--strict"], fetcher=fetch) == 1
    capsys.readouterr()
    assert (
        owners.main(
            ["--corpus", corpus, "--strict"], fetcher=_fake({5: "OPEN", 6: "OPEN", 7: "OPEN"})
        )
        == 0
    )


def test_real_corpus_findings_match_corpus_without_network() -> None:
    report = owners.build_report(CORPUS, _fake({}))
    finding_cases = [case for case in CASES if case.status == "finding"]
    assert [row["case_id"] for row in report["findings"]] == [
        case.case_id for case in finding_cases
    ]
    assert {row["finding_id"] for row in report["findings"]} == set(FINDINGS)
    rows = {row["case_id"]: row for row in report["findings"]}
    assert [issue["number"] for issue in rows["GB-077"]["owner_issues"]] == [12, 117]
    assert [issue["number"] for issue in rows["GB-079"]["owner_issues"]] == [7, 31, 117]
