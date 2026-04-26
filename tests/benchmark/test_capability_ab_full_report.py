from pathlib import Path

from scripts.bench import capability_ab_full_report as full_report


def test_run_bucket_passes_tuning_profile(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    class _Res:
        def __init__(self, stdout: str, returncode: int = 0):
            self.stdout = stdout
            self.stderr = ""
            self.returncode = returncode

    def _fake_run(cmd: list[str], cwd: Path):  # noqa: ANN001
        if "capability_ab_runner.py" in " ".join(cmd):
            captured["runner_cmd"] = cmd
            return _Res('{"with_nexus_file":"a.jsonl","without_nexus_file":"b.jsonl"}')
        captured["eval_cmd"] = cmd
        return _Res('{"a":{"summary":{}},"b":{"summary":{}}}')

    monkeypatch.setattr(full_report, "_run", _fake_run)

    out = full_report._run_bucket(
        repo_root=tmp_path,
        output_dir=tmp_path / "out",
        name="daily",
        tasks_file="scripts/bench/capability_tasks_v1.json",
        difficulty="all",
        max_tasks=1,
        tuning_profile="daily",
        with_llm_mode="hard",
        with_model_label="gemini-3-flash-preview",
    )

    cmd = captured["runner_cmd"]
    assert isinstance(cmd, list)
    assert "--tuning-profile" in cmd
    assert "daily" in cmd
    assert "--with-llm-mode" in cmd
    assert "hard" in cmd
    assert "--with-model-label" in cmd
    assert "gemini-3-flash-preview" in cmd
    assert "--disable-learning-loop" in cmd
    assert out["name"] == "daily"
    assert out["kpi"]["overhead_metric"] == "avg_wall_duration_sec"


def test_run_bucket_service_force_baseline(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    class _Res:
        def __init__(self, stdout: str, returncode: int = 0):
            self.stdout = stdout
            self.stderr = ""
            self.returncode = returncode

    def _fake_run(cmd: list[str], cwd: Path):  # noqa: ANN001
        if "capability_ab_runner.py" in " ".join(cmd):
            captured["runner_cmd"] = cmd
            return _Res('{"with_nexus_file":"a.jsonl","without_nexus_file":"b.jsonl"}')
        return _Res('{"a":{"summary":{}},"b":{"summary":{}}}')

    monkeypatch.setattr(full_report, "_run", _fake_run)

    out = full_report._run_bucket(
        repo_root=tmp_path,
        output_dir=tmp_path / "out",
        name="hard",
        tasks_file="scripts/bench/capability_tasks_v1.json",
        difficulty="hard",
        max_tasks=1,
        tuning_profile="iter",
        without_mode="service",
        service_force_baseline=True,
    )

    cmd = captured["runner_cmd"]
    assert isinstance(cmd, list)
    assert "--force-flow" in cmd
    idx = cmd.index("--force-flow")
    assert cmd[idx + 1] == "baseline"
    assert out["kpi"]["overhead_metric"] == "avg_duration_sec"


def test_run_bucket_maps_legacy_service_runner_to_subprocess(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    class _Res:
        def __init__(self, stdout: str, returncode: int = 0):
            self.stdout = stdout
            self.stderr = ""
            self.returncode = returncode

    def _fake_run(cmd: list[str], cwd: Path):  # noqa: ANN001
        if "capability_ab_runner.py" in " ".join(cmd):
            captured["runner_cmd"] = cmd
            return _Res('{"with_nexus_file":"a.jsonl","without_nexus_file":"b.jsonl"}')
        return _Res('{"a":{"summary":{}},"b":{"summary":{}}}')

    monkeypatch.setattr(full_report, "_run", _fake_run)

    full_report._run_bucket(
        repo_root=tmp_path,
        output_dir=tmp_path / "out",
        name="service",
        tasks_file="scripts/bench/capability_tasks_v1.json",
        difficulty="all",
        max_tasks=1,
        with_nexus_runner="service",
        without_mode="service",
    )

    cmd = captured["runner_cmd"]
    assert isinstance(cmd, list)
    idx = cmd.index("--with-nexus-runner")
    assert cmd[idx + 1] == "subprocess"


def test_run_file_task_bucket_uses_emit_ab(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}
    eval_file = tmp_path / "ab_eval.json"
    eval_file.write_text(
        """
{
  "a": {"label": "local-baseline", "summary": {"solve_rate": 0.5, "semantic_verified_rate": 0.0, "trust_mismatch_rate": 1.0, "avg_duration_sec": 1.0}},
  "b": {"label": "gemini-flash-file-task", "summary": {"solve_rate": 1.0, "semantic_verified_rate": 1.0, "trust_mismatch_rate": 0.0, "avg_duration_sec": 10.0}}
}
""".strip(),
        encoding="utf-8",
    )

    class _Res:
        def __init__(self, stdout: str, returncode: int = 0):
            self.stdout = stdout
            self.stderr = ""
            self.returncode = returncode

    def _fake_run(cmd: list[str], cwd: Path):  # noqa: ANN001
        captured["runner_cmd"] = cmd
        return _Res(
            f'{{"with_nexus_file":"with.jsonl","without_nexus_file":"without.jsonl","ab_eval_file":"{eval_file}"}}'
        )

    monkeypatch.setattr(full_report, "_run", _fake_run)

    out = full_report._run_file_task_bucket(
        repo_root=tmp_path,
        output_dir=tmp_path / "out",
        name="flash_file_task_cross_module",
        tasks_file="scripts/bench/capability_flash_xmodule_tasks_v1.json",
        max_tasks=3,
        model="gemini-3-flash-preview",
        timeout_sec=240,
    )

    cmd = captured["runner_cmd"]
    assert isinstance(cmd, list)
    assert "capability_file_task_runner.py" in " ".join(cmd)
    assert "--emit-ab" in cmd
    assert "--model" in cmd
    assert "gemini-3-flash-preview" in cmd
    assert "--context-mode" in cmd
    assert "lean" in cmd
    assert "--invocation-mode" in cmd
    assert "inline" in cmd
    assert out["kpi"]["with_solve_rate"] == 1.0
    assert out["kpi"]["without_solve_rate"] == 0.5
    assert out["kpi"]["delta_semantic_verified_rate"] == 1.0
    assert out["kpi"]["delta_trust_mismatch_rate"] == 1.0


def test_full_report_stress_bucket_adjusts_weights(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {"runner_cmds": []}

    class _Res:
        def __init__(self, stdout: str, returncode: int = 0):
            self.stdout = stdout
            self.stderr = ""
            self.returncode = returncode

    def _fake_run(cmd: list[str], cwd: Path):  # noqa: ANN001
        text = " ".join(cmd)
        if "capability_ab_runner.py" in text:
            cast_cmds = captured["runner_cmds"]
            assert isinstance(cast_cmds, list)
            cast_cmds.append(cmd)
            return _Res('{"with_nexus_file":"a.jsonl","without_nexus_file":"b.jsonl"}')
        return _Res('{"a":{"summary":{}},"b":{"summary":{}}}')

    monkeypatch.setattr(full_report, "_run", _fake_run)
    monkeypatch.setattr(full_report.time, "time", lambda: 1234567890)

    monkeypatch.setattr(
        "sys.argv",
        [
            "capability_ab_full_report.py",
            "--output-dir",
            str(tmp_path / "out"),
            "--enable-stress-cross-bucket",
            "--output-json",
        ],
    )
    rc = full_report.main()
    assert rc == 0
    runner_cmds = captured["runner_cmds"]
    assert isinstance(runner_cmds, list)
    # daily, hard, cross_module, cross_module_stress
    assert len(runner_cmds) == 4
    assert any(
        "--tasks-file" in cmd and any("capability_tasks_cross_module_v1.json" in part for part in cmd)
        for cmd in runner_cmds
    )
    stress_cmd = next(
        cmd
        for cmd in runner_cmds
        if "--tasks-file" in cmd and any("capability_tasks_cross_module_v1.json" in part for part in cmd)
    )
    assert "--force-flow" not in stress_cmd
    assert "--tuning-profile" in stress_cmd
    assert "iter" in stress_cmd
    assert "--without-force-flow" not in stress_cmd


def test_full_report_flash_file_task_bucket_adjusts_weights(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {"runner_cmds": []}
    eval_file = tmp_path / "ab_eval.json"
    eval_file.write_text(
        '{"a":{"summary":{}},"b":{"summary":{"solve_rate":1.0,"semantic_verified_rate":1.0}}}',
        encoding="utf-8",
    )

    class _Res:
        def __init__(self, stdout: str, returncode: int = 0):
            self.stdout = stdout
            self.stderr = ""
            self.returncode = returncode

    def _fake_run(cmd: list[str], cwd: Path):  # noqa: ANN001
        text = " ".join(cmd)
        if "capability_file_task_runner.py" in text:
            cast_cmds = captured["runner_cmds"]
            assert isinstance(cast_cmds, list)
            cast_cmds.append(cmd)
            return _Res(
                f'{{"with_nexus_file":"with.jsonl","without_nexus_file":"without.jsonl","ab_eval_file":"{eval_file}"}}'
            )
        if "capability_ab_runner.py" in text:
            return _Res('{"with_nexus_file":"a.jsonl","without_nexus_file":"b.jsonl"}')
        return _Res('{"a":{"summary":{}},"b":{"summary":{}}}')

    monkeypatch.setattr(full_report, "_run", _fake_run)
    monkeypatch.setattr(full_report.time, "time", lambda: 1234567890)

    monkeypatch.setattr(
        "sys.argv",
        [
            "capability_ab_full_report.py",
            "--output-dir",
            str(tmp_path / "out"),
            "--enable-flash-file-task-bucket",
            "--flash-file-task-max-tasks",
            "2",
            "--output-json",
        ],
    )
    rc = full_report.main()
    assert rc == 0
    runner_cmds = captured["runner_cmds"]
    assert isinstance(runner_cmds, list)
    assert len(runner_cmds) == 1
    assert "--emit-ab" in runner_cmds[0]

    report_file = tmp_path / "out" / "full_ab_report_1234567890.json"
    payload = full_report._load_json_file(report_file)
    assert payload["weights"]["flash_file_task_cross_module"] == 0.25
    assert "flash_file_task_cross_module" in payload["bucket_scores"]
    assert "flash_file_task_cross_module" in payload["realism_bucket_scores"]
    assert payload["realism_score"] >= payload["weighted_score"]
