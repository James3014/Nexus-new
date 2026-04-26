from pathlib import Path

from scripts.bench import capability_wave34_runner as wave34


def test_wave34_runner_smoke(monkeypatch, tmp_path: Path):
    class _Res:
        def __init__(self, stdout: str, returncode: int = 0):
            self.stdout = stdout
            self.stderr = ""
            self.returncode = returncode

    full_ab_report = tmp_path / "full_ab.json"
    full_ab_report.write_text("{}", encoding="utf-8")
    ops_report = tmp_path / "ops_rounds.json"
    ops_report.write_text("{}", encoding="utf-8")
    s_report = tmp_path / "s_grade.json"
    s_report.write_text('{"summary":{"verdict":"S6_PASS"}}', encoding="utf-8")
    guard_report = tmp_path / "guard.json"
    guard_report.write_text("{}", encoding="utf-8")

    def _fake_run(cmd: list[str], cwd: Path):  # noqa: ANN001
        cmd_text = " ".join(cmd)
        if "capability_ab_full_report.py" in cmd_text:
            return _Res(f'{{"report_file":"{full_ab_report}"}}')
        if "capability_ops_loop.py" in cmd_text:
            return _Res(f'{{"report_file":"{ops_report}"}}')
        if "capability_s_grade.py" in cmd_text:
            return _Res(f'{{"report_file":"{s_report}","summary":{{"verdict":"S6_PASS"}}}}')
        if "capability_regression_guard.py" in cmd_text:
            return _Res(f'{{"status":"PASS","failures":[],"report_file":"{guard_report}"}}')
        raise AssertionError(f"unexpected command: {cmd_text}")

    monkeypatch.setattr(wave34, "_run", _fake_run)
    captured: list[list[str]] = []

    def _capture_run(cmd: list[str], cwd: Path):  # noqa: ANN001
        captured.append(cmd)
        return _fake_run(cmd, cwd)

    monkeypatch.setattr(wave34, "_run", _capture_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "capability_wave34_runner.py",
            "--with-llm-mode",
            "hard",
            "--with-model-label",
            "gemini-3-flash-preview",
            "--output-json",
        ],
    )
    rc = wave34.main()
    assert rc == 0
    assert any("--with-llm-mode" in cmd and "hard" in cmd for cmd in captured)
    assert any("--with-model-label" in cmd and "gemini-3-flash-preview" in cmd for cmd in captured)
    runner_modes = [cmd[cmd.index("--with-nexus-runner") + 1] for cmd in captured if "--with-nexus-runner" in cmd]
    assert "service" not in runner_modes
    ops_cmds = [cmd for cmd in captured if "capability_ops_loop.py" in " ".join(cmd)]
    assert len(ops_cmds) == 1
    assert "--force-flow" not in ops_cmds[0]
    assert "--without-mode" not in ops_cmds[0]
    assert "--with-model-label" not in ops_cmds[0]
    guard_cmds = [cmd for cmd in captured if "capability_regression_guard.py" in " ".join(cmd)]
    assert len(guard_cmds) == 1
    idx = guard_cmds[0].index("--min-grade")
    assert guard_cmds[0][idx + 1] == "S9_PASS"


def test_wave34_runner_uses_a_pass_guard_for_offline_mode(monkeypatch, tmp_path: Path):
    class _Res:
        def __init__(self, stdout: str, returncode: int = 0):
            self.stdout = stdout
            self.stderr = ""
            self.returncode = returncode

    report = tmp_path / "report.json"
    report.write_text("{}", encoding="utf-8")
    s_report = tmp_path / "s_grade.json"
    s_report.write_text('{"summary":{"verdict":"A_PASS"}}', encoding="utf-8")
    guard_report = tmp_path / "guard.json"
    guard_report.write_text("{}", encoding="utf-8")
    captured: list[list[str]] = []

    def _fake_run(cmd: list[str], cwd: Path):  # noqa: ANN001
        captured.append(cmd)
        cmd_text = " ".join(cmd)
        if "capability_s_grade.py" in cmd_text:
            return _Res(f'{{"report_file":"{s_report}","summary":{{"verdict":"A_PASS"}}}}')
        if "capability_regression_guard.py" in cmd_text:
            return _Res(f'{{"status":"PASS","failures":[],"report_file":"{guard_report}"}}')
        return _Res(f'{{"report_file":"{report}"}}')

    monkeypatch.setattr(wave34, "_run", _fake_run)
    monkeypatch.setattr("sys.argv", ["capability_wave34_runner.py", "--with-llm-mode", "off", "--output-json"])

    rc = wave34.main()
    assert rc == 0
    guard_cmd = [cmd for cmd in captured if "capability_regression_guard.py" in " ".join(cmd)][0]
    idx = guard_cmd.index("--min-grade")
    assert guard_cmd[idx + 1] == "A_PASS"
