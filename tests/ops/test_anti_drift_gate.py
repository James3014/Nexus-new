from __future__ import annotations

from pathlib import Path

from scripts.ops.anti_drift_gate import run_anti_drift_gate


def test_anti_drift_gate_passes_when_historical_tests_pass(monkeypatch, tmp_path: Path) -> None:
    def _fake_run(*_args, **_kwargs):
        class _R:
            returncode = 0
            stdout = "ok\n"
            stderr = ""
        return _R()

    monkeypatch.setattr("scripts.ops.anti_drift_gate.subprocess.run", _fake_run)
    monkeypatch.setattr("scripts.ops.anti_drift_gate._count_changed_files", lambda *_args, **_kwargs: 5)
    policy = {
        "historical_tests": [{"name": "legacy", "command": "uv run pytest -q tests/x.py"}],
        "min_pass_rate": 1.0,
        "invariance_assertions": {"min_historical_pass_rate": 1.0},
        "belief_jump_guard": {"enabled": False},
    }
    report = run_anti_drift_gate(project_root=tmp_path, policy=policy, report_path=tmp_path / "anti_drift.json")
    assert report["gate_passed"] is True
    assert report["historical_pass_rate"] == 1.0
    assert report["drift_index"] == 0.0


def test_anti_drift_gate_fails_on_suspicious_belief_jump(monkeypatch, tmp_path: Path) -> None:
    report_path = tmp_path / "anti_drift.json"
    report_path.write_text('{"invariance_score": 0.1}', encoding="utf-8")

    def _fake_run(*_args, **_kwargs):
        class _R:
            returncode = 0
            stdout = "ok\n"
            stderr = ""
        return _R()

    monkeypatch.setattr("scripts.ops.anti_drift_gate.subprocess.run", _fake_run)
    monkeypatch.setattr("scripts.ops.anti_drift_gate._count_changed_files", lambda *_args, **_kwargs: 1)
    policy = {
        "historical_tests": [{"name": "legacy", "command": "uv run pytest -q tests/x.py"}],
        "min_pass_rate": 1.0,
        "invariance_assertions": {"min_historical_pass_rate": 1.0},
        "belief_jump_guard": {"enabled": True, "max_score_delta": 0.2, "small_change_max_files": 2},
    }
    out = run_anti_drift_gate(project_root=tmp_path, policy=policy, report_path=report_path)
    assert out["gate_passed"] is False
    assert out["belief_jump_guard"]["reason"] == "score_jump_too_large_for_small_change"
