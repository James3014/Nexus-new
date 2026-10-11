from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from nexus.research.flow.meta_opt_preset import APPLY_ENV_FLAG, apply_meta_opt_preset
from scripts.engine.commands.research_actions import run_research_auto_flow

BASE = {
    "timeout_sec": 60,
    "stage1_timeout_sec": 20,
    "max_time_ratio_guard": 1.5,
    "baseline_fast_sec": 9.0,
    "history_window": 5,
    "history_fail_threshold": 2,
    "dynamic_timeout_multiplier": 2.5,
    "min_dynamic_stage1_timeout": 12,
}
ON = {APPLY_ENV_FLAG: "1"}


def _write_report(root: Path, report: dict) -> Path:
    path = root / ".nexus/reports/research/meta-opt-report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def _ok_report(preset: dict, **selected_extra) -> dict:
    return {
        "status": "ok",
        "selected_preset": {
            "preset_name": "p1",
            "status": "ok",
            "preset": preset,
            "report_file": "missing-child.json",
            **selected_extra,
        },
    }


def test_flag_off_leaves_settings_unchanged_and_ignores_report(tmp_path: Path):
    _write_report(tmp_path, _ok_report({"timeout_sec": 5}))
    out, evidence = apply_meta_opt_preset(tmp_path, BASE, env={})
    assert out == BASE
    assert evidence is None
    out, evidence = apply_meta_opt_preset(tmp_path, BASE, env={APPLY_ENV_FLAG: "0"})
    assert out == BASE
    assert evidence is None


def test_flag_on_valid_report_overrides_mapped_keys_with_evidence(tmp_path: Path):
    path = _write_report(
        tmp_path,
        _ok_report({
            "name": "p1",
            "timeout_sec": 90,
            "max_time_ratio_guard": 2,
            "ab_trials": 3,
            "history_window": 0,
            "stage1_timeout_sec": "x",
        }),
    )
    out, evidence = apply_meta_opt_preset(tmp_path, BASE, env=ON)
    assert out["timeout_sec"] == 90
    assert out["max_time_ratio_guard"] == 2.0
    assert out["history_window"] == 5
    assert out["stage1_timeout_sec"] == 20
    assert out["baseline_fast_sec"] == 9.0
    assert evidence is not None
    assert evidence["applied"] is True
    assert evidence["report_path"] == str(path)
    assert evidence["report_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert set(evidence["applied_keys"]) == {"timeout_sec", "max_time_ratio_guard"}
    assert evidence["applied_keys"]["timeout_sec"] == {"from": 60, "to": 90}
    assert set(evidence["rejected_keys"]) == {"history_window", "stage1_timeout_sec"}
    assert sorted(evidence["ignored_keys"]) == ["ab_trials", "name"]


@pytest.mark.parametrize(
    ("report", "reason"),
    [
        (
            {"status": "no_eligible_preset", "selected_preset": None},
            "report_status_no_eligible_preset",
        ),
        ({"status": "ok", "selected_preset": None}, "no_selected_preset"),
        (
            _ok_report({"timeout_sec": 5}, status="simulated_report"),
            "simulated_or_unmeasured_preset",
        ),
        ({**_ok_report({"timeout_sec": 5}), "simulated": True}, "simulated_or_unmeasured_preset"),
    ],
)
def test_flag_on_ineligible_report_unchanged_with_reason(tmp_path: Path, report: dict, reason: str):
    _write_report(tmp_path, report)
    out, evidence = apply_meta_opt_preset(tmp_path, BASE, env=ON)
    assert out == BASE
    assert evidence is not None
    assert evidence["applied"] is False
    assert evidence["reason"] == reason
    assert evidence["report_sha256"]


def test_flag_on_simulated_child_report_is_rejected(tmp_path: Path):
    child = tmp_path / "child.json"
    child.write_text(json.dumps({"simulated": True}), encoding="utf-8")
    _write_report(tmp_path, _ok_report({"timeout_sec": 5}, report_file=str(child)))
    out, evidence = apply_meta_opt_preset(tmp_path, BASE, env=ON)
    assert out == BASE
    assert evidence is not None
    assert evidence["reason"] == "source_report_simulated"


def test_flag_on_malformed_or_missing_report_unchanged_with_reason(tmp_path: Path):
    out, evidence = apply_meta_opt_preset(tmp_path, BASE, env=ON)
    assert out == BASE
    assert evidence is not None
    assert evidence["reason"].startswith("report_unreadable")
    assert evidence["report_sha256"] is None
    path = tmp_path / ".nexus/reports/research/meta-opt-report.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    out, evidence = apply_meta_opt_preset(tmp_path, BASE, env=ON)
    assert out == BASE
    assert evidence is not None
    assert evidence["reason"] == "report_malformed"
    assert evidence["report_sha256"]


def _run_flow(root: Path, calls: list) -> dict:
    report_path = root / "auto-flow-report.json"

    def runner(**kwargs):
        calls.append(kwargs)
        return (
            {
                "chosen_flow": "baseline",
                "result": {"status": "SUCCESS", "elapsed_sec": 0.1},
                "io": {"output_written": False, "output_path": None},
            },
            report_path,
        )

    result = run_research_auto_flow(
        root,
        task_desc="fix race",
        target_file="demo.py",
        test_file="tests/test_demo.py",
        task_type="bug",
        success_criteria="all_target_tests_pass",
        candidate_count=1,
        root_cause_confidence=1.0,
        findings_query=None,
        llm_mode=False,
        llm_baseline=False,
        llm_baseline_required=False,
        force_flow="baseline",
        report_file=str(report_path),
        output_file=None,
        task_id="task-1",
        research_session_id="",
        research_gate=False,
        auto_flow_runner=runner,
        **BASE,
    )
    return result.payload


def test_auto_flow_unchanged_when_flag_off_and_overridden_when_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _write_report(tmp_path, _ok_report({"timeout_sec": 90, "min_dynamic_stage1_timeout": 7}))
    monkeypatch.delenv(APPLY_ENV_FLAG, raising=False)
    calls: list = []
    payload = _run_flow(tmp_path, calls)
    assert {k: calls[0][k] for k in BASE} == BASE
    assert "meta_opt_preset" not in payload

    monkeypatch.setenv(APPLY_ENV_FLAG, "1")
    calls.clear()
    payload = _run_flow(tmp_path, calls)
    assert calls[0]["timeout_sec"] == 90
    assert calls[0]["min_dynamic_stage1_timeout"] == 7
    assert calls[0]["stage1_timeout_sec"] == 20
    assert payload["meta_opt_preset"]["applied"] is True
    assert payload["meta_opt_preset"]["report_sha256"]
