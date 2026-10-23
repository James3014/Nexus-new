from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "eia_scoreboard", Path(__file__).resolve().parents[2] / "scripts" / "ops" / "eia_scoreboard.py"
)
assert _SPEC and _SPEC.loader
sb = importlib.util.module_from_spec(_SPEC)
sys.modules["eia_scoreboard"] = sb
_SPEC.loader.exec_module(sb)

REPO = "James3014_Nexus-new"


def _w(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _state(root: Path, issue: int, ident: str, **fields) -> None:
    body = {
        "schema": "nexus.external_intelligence_automation_state.v1",
        "issue_number": issue,
        "identity_hash": ident,
        "repository": "James3014/Nexus-new",
    }
    body.update(fields)
    _w(root / "automation" / REPO / f"issue-{issue}-{ident}.json", body)


def _intel(root: Path, effect: str, start: str, end: str, state: str, revision: str) -> None:
    _w(
        root / REPO / "intelligence" / "attempts" / f"{effect}.json",
        {"state": state, "prepared_at": start, "dispatching_at": start, "finished_at": end},
    )
    _w(
        root / REPO / "intelligence" / "requests" / f"{effect}.json",
        {"identity": {"revision": revision, "main_sha": "a" * 40}},
    )


def _op(root: Path, op_id: str, kind: str, start: str, end: str, status: str, **extra) -> None:
    _w(
        root / "open_swe_runtime" / "operations" / f"{op_id}.json",
        {
            "operation_id": op_id,
            "kind": kind,
            "started_at": start,
            "finished_at": end,
            "status": status,
            **extra,
        },
    )


def _receipt(rev: str) -> dict:
    return {"provider_model_revision": rev, "active_latency_seconds": 1.0}


def _fanout(root: Path, effect: str, unit: str, task: str, state: str, op_id: str) -> None:
    _w(
        root / REPO / "fanout" / "attempts" / f"{task}--{unit}--initial.json",
        {
            "envelope_ref": f"/x/intelligence/envelopes/{effect}.json",
            "task_id": task,
            "unit_id": unit,
            "state": state,
            "operation_id": op_id,
        },
    )


def _verification(root: Path, task: str, scope: str, status: str, **extra) -> None:
    _w(
        root / REPO / "closure" / "verifications" / f"{task}--{scope}.json",
        {"task_id": task, "scope": scope, "status": status, "failed_verifier_ids": [], **extra},
    )


@pytest.fixture
def state_root(tmp_path: Path) -> Path:
    root = tmp_path / "state"
    # completed run
    _state(
        root,
        7,
        "c" * 64,
        state="COMPLETE",
        intelligence_effect_id="e1",
        closure_run_id="cl",
        semantic_dispatched=True,
        publication={"task_id": "task-ok"},
        publication_record={"state": "COMPLETED"},
    )
    _intel(root, "e1", "2026-10-14T01:00:00Z", "2026-10-14T01:02:00Z", "COMPLETED", "rev-r1")
    _op(
        root,
        "s1",
        "semantic",
        "2026-10-14T01:00:05Z",
        "2026-10-14T01:01:50Z",
        "INTELLIGENCE_COMPLETED",
        model_invocation_receipts=[_receipt("gpt-x")],
    )
    _fanout(root, "e1", "u1", "task-ok", "COMPLETED", "w1")
    _op(
        root,
        "w1",
        "worker",
        "2026-10-14T01:03:00Z",
        "2026-10-14T01:09:00Z",
        "COMPLETED",
        repair_phase_count=1,
        core_binding_status="BOUND",
        model_invocation_receipts=[_receipt("gpt-x"), _receipt("NOT_MEASURED")],
    )
    _verification(root, "task-ok", "UNIT", "PASS")
    _verification(root, "task-ok", "WHOLE_TASK", "PASS")
    _w(
        root / REPO / "closure" / "acceptance-packets" / "p.json",
        {"task_id": "task-ok", "current_gate": "PENDING_INDEPENDENT_ACCEPTANCE"},
    )
    # semantic-stage failure
    _state(
        root,
        7,
        "d" * 64,
        state="RECONCILIATION_REQUIRED",
        error="ExternalIntelligenceError",
        prior_state="INTELLIGENCE_DISPATCHING",
        intelligence_effect_id="e2",
    )
    _intel(root, "e2", "2026-10-14T00:00:00Z", "2026-10-14T00:05:00Z", "OUTCOME_UNKNOWN", "rev-r0")
    _op(
        root,
        "s2",
        "semantic",
        "2026-10-14T00:00:02Z",
        "2026-10-14T00:04:00Z",
        "OPEN_SWE_OUTCOME_UNKNOWN",
        error="OpenCLIWebModelError",
    )
    # fanout reconciliation block (worker failed)
    _state(
        root,
        8,
        "f" * 64,
        state="RECONCILIATION_REQUIRED",
        error="FANOUT_RECONCILIATION_REQUIRED",
        prior_state="FANOUT_DISPATCHING",
        intelligence_effect_id="e3",
        semantic_dispatched=True,
    )
    _intel(root, "e3", "2026-10-14T02:00:00Z", "2026-10-14T02:02:00Z", "COMPLETED", "rev-r1")
    _op(
        root,
        "s3",
        "semantic",
        "2026-10-14T02:00:01Z",
        "2026-10-14T02:01:50Z",
        "INTELLIGENCE_COMPLETED",
        model_invocation_receipts=[_receipt("gpt-y")],
    )
    _fanout(root, "e3", "u1", "task-fan", "OUTCOME_UNKNOWN", "w3")
    _op(
        root,
        "w3",
        "worker",
        "2026-10-14T02:03:00Z",
        "2026-10-14T02:04:00Z",
        "OPEN_SWE_OUTCOME_UNKNOWN",
        error="OpenCLIWebModelError",
    )
    # verifier block before dispatch
    _state(
        root,
        9,
        "b" * 64,
        state="BLOCKED",
        error="VERIFIER_NOT_AUTHORIZED",
        semantic_dispatched=False,
    )
    return root


def _by_ident(runs: list[dict], char: str) -> dict:
    return next(r for r in runs if r["identity"] == char * 64)


def test_completed_run(state_root: Path) -> None:
    runs, _ = sb.collect(state_root, None)
    run = _by_ident(runs, "c")
    assert run["state"] == "COMPLETE"
    assert run["failed_at"] is None
    assert run["reached"] == "acceptance"
    assert run["task_id"] == "task-ok"
    assert run["revision"] == "rev-r1"
    assert run["model_invocations"] == 3
    assert run["model_revisions"] == ["gpt-x"]
    assert run["unmeasured_invocations"] == 1
    assert run["repair_phases"] == 1
    assert run["acceptance_gate"] == "PENDING_INDEPENDENT_ACCEPTANCE"
    assert run["first_ts"] == "2026-10-14T01:00:00Z"
    assert run["duration_s"] >= 540  # through worker finish at 01:09:00


def test_semantic_failure(state_root: Path) -> None:
    run = _by_ident(sb.collect(state_root, None)[0], "d")
    assert run["failed_at"] == "semantic"
    assert run["reason"] == "ExternalIntelligenceError"
    assert run["detail"] == "OpenCLIWebModelError"
    assert run["reached"] == "preflight"


def test_fanout_reconciliation_block(state_root: Path) -> None:
    run = _by_ident(sb.collect(state_root, None)[0], "f")
    assert run["failed_at"] == "worker"
    assert run["reached"] == "fanout_dispatch"
    assert run["reason"] == "FANOUT_RECONCILIATION_REQUIRED"
    assert run["task_id"] == "task-fan"
    assert run["model_revisions"] == ["gpt-y"]


def test_verifier_block(state_root: Path) -> None:
    run = _by_ident(sb.collect(state_root, None)[0], "b")
    assert run["failed_at"] == "preflight"
    assert run["blocked_by"] == "VERIFIER_NOT_AUTHORIZED"
    assert run["duration_s"] is None
    assert run["ts_source"] == "state_file_mtime_only"


def test_failed_whole_verification_reports_blocker(tmp_path: Path) -> None:
    root = tmp_path / "s"
    _state(
        root,
        1,
        "a" * 64,
        state="RECONCILIATION_REQUIRED",
        prior_state="CLOSURE_DISPATCHING",
        intelligence_effect_id="e",
        closure_run_id="c",
        publication={"task_id": "t"},
    )
    _intel(root, "e", "2026-10-14T01:00:00Z", "2026-10-14T01:01:00Z", "COMPLETED", "r")
    _fanout(root, "e", "u1", "t", "COMPLETED", "w")
    _op(root, "w", "worker", "2026-10-14T01:02:00Z", "2026-10-14T01:03:00Z", "COMPLETED")
    _verification(root, "t", "UNIT", "PASS")
    _verification(
        root, "t", "WHOLE_TASK", "FAIL", failed_integrity_check_ids=["nexus.integrity.scope"]
    )
    run = sb.collect(root, None)[0][0]
    assert run["failed_at"] == "whole_verify"
    assert run["blocked_by"] == "nexus.integrity.scope"


def test_ambiguous_semantic_link_is_reported_not_guessed(tmp_path: Path) -> None:
    root = tmp_path / "s"
    _state(root, 1, "a" * 64, state="RECONCILIATION_REQUIRED", intelligence_effect_id="e")
    _intel(root, "e", "2026-10-14T01:00:00Z", "2026-10-14T01:10:00Z", "OUTCOME_UNKNOWN", "r")
    for n in ("1", "2"):
        _op(
            root,
            f"s{n}",
            "semantic",
            f"2026-10-14T01:0{n}:00Z",
            "2026-10-14T01:05:00Z",
            "X",
            model_invocation_receipts=[_receipt("m")],
        )
    run = sb.collect(root, None)[0][0]
    assert run["model_invocations"] == 0
    assert any(n.startswith("semantic_ops_ambiguous") for n in run["link_notes"])


def test_opencli_failures_in_window(state_root: Path, tmp_path: Path) -> None:
    log = tmp_path / "f.log"
    log.write_text(
        "=== 2026-10-14T00:02:00Z rc=1 cmd=ask\nok: false\nerror:\n  code: COMMAND_EXEC\n  message: x\n"
        "=== 2026-10-13T00:00:00Z rc=2 cmd=detail (redacted)\nerror:\n  code: ARGUMENT\n",
        encoding="utf-8",
    )
    runs, _ = sb.collect(state_root, log)
    run = _by_ident(runs, "d")
    assert run["opencli_failures"] == 1
    assert run["opencli_failure_codes"] == {"COMMAND_EXEC": 1}


def test_markdown_and_jsonl_and_since(state_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert sb.main(["--state-root", str(state_root), "--failure-log", "", "--format", "jsonl"]) == 0
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(rows) == 4
    assert (
        sb.main(["--state-root", str(state_root), "--failure-log", "", "--format", "markdown"]) == 0
    )
    out = capsys.readouterr().out
    assert "- runs: 4" in out and "- completed: 1" in out and "- success rate: 25%" in out
    assert "worker: 1" in out and "semantic: 1" in out
    assert (
        sb.main([
            "--state-root",
            str(state_root),
            "--failure-log",
            "",
            "--since",
            "2026-10-14T01:30:00Z",
            "--format",
            "jsonl",
        ])
        == 0
    )
    since_rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    idents = {r["identity"][0] for r in since_rows}
    assert "f" in idents and not idents & {"c", "d"}


def test_since_naive_datetime_is_utc_under_non_utc_timezone(
    state_root: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    if not hasattr(time, "tzset"):
        pytest.skip("time.tzset is required for process-timezone regression coverage")
    try:
        with monkeypatch.context() as env:
            env.setenv("TZ", "Asia/Taipei")
            time.tzset()
            assert (
                sb.main([
                    "--state-root",
                    str(state_root),
                    "--failure-log",
                    "",
                    "--since",
                    "2026-10-14T01:30:00",
                    "--format",
                    "jsonl",
                ])
                == 0
            )
            naive_rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
            naive_idents = {r["identity"][0] for r in naive_rows}
            assert "f" in naive_idents and not naive_idents & {"c", "d"}

            assert (
                sb.main([
                    "--state-root",
                    str(state_root),
                    "--failure-log",
                    "",
                    "--since",
                    "2026-10-14T09:30:00+08:00",
                    "--format",
                    "jsonl",
                ])
                == 0
            )
            offset_rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
            assert {r["identity"] for r in offset_rows} == {r["identity"] for r in naive_rows}
    finally:
        time.tzset()


def test_filter_since_date_only_remains_utc_midnight() -> None:
    runs = [
        {"first_ts": "2026-10-19T23:59:59Z"},
        {"first_ts": "2026-10-20T00:00:00Z"},
    ]
    assert sb.filter_since(runs, "2026-10-20") == [runs[1]]


def test_read_only(state_root: Path) -> None:
    before = {p: p.read_bytes() for p in state_root.rglob("*") if p.is_file()}
    sb.collect(state_root, None)
    after = {p: p.read_bytes() for p in state_root.rglob("*") if p.is_file()}
    assert before == after


@pytest.mark.parametrize("sub", ["empty", "missing"])
def test_empty_or_missing_dir(tmp_path: Path, sub: str, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "nothing"
    if sub == "empty":
        root.mkdir()
    runs, meta = sb.collect(root, tmp_path / "no.log")
    assert runs == [] and meta["operations_total"] == 0
    assert sb.main(["--state-root", str(root), "--failure-log", ""]) == 0
    out = capsys.readouterr().out
    assert "- runs: 0" in out and "success rate: n/a" in out


def test_wrong_field_types_do_not_crash(tmp_path: Path) -> None:
    root = tmp_path / "state"
    _w(root / "automation" / REPO / "issue-7-aa.json", {"schema": None})
    _state(root, 8, "bb", state="BLOCKED")
    _op(
        root,
        "op1",
        "worker",
        "2026-10-14T00:00:00Z",
        "2026-10-14T00:01:00Z",
        "COMPLETED",
        repair_phase_count="many",
    )
    _verification(root, "t", "UNIT", "FAIL", failed_verifier_ids="not-a-list")
    runs, _meta = sb.collect(root, None)
    assert [r["issue"] for r in runs] == [8]
