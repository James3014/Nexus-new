from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_mod


def test_run_fails_fast_when_task_requests_file_output_without_output_file():
    runner = CliRunner()
    res = runner.invoke(cli_mod.nexus, ["nexus", "run", "請將結果寫入 /tmp/result.md"])
    assert res.exit_code != 0
    assert "--output-file" in res.output


def test_run_writes_output_file_when_explicit_path_provided(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(cli_mod, "_execute_single_run_task", lambda *_args, **_kwargs: True)

    out_path = tmp_path / "out" / "task_result.json"
    runner = CliRunner()
    res = runner.invoke(
        cli_mod.nexus,
        ["nexus", "run", "simple-task", "--output-file", str(out_path)],
    )
    assert res.exit_code == 0, res.output
    assert out_path.exists()
    payload = out_path.read_text(encoding="utf-8")
    assert "simple-task" in payload
    assert "output_written" in payload
    assert "SUCCESS" in payload
    assert "[run-classification] verified_pass" in res.output


def test_run_uses_canonical_single_task_executor(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_mod, "REPO_ROOT", tmp_path)
    called = {}

    def _fake_execute(task_text, project_root):
        called["task_text"] = task_text
        called["project_root"] = project_root
        return True

    monkeypatch.setattr(cli_mod, "_execute_single_run_task", _fake_execute)
    runner = CliRunner()
    res = runner.invoke(cli_mod.nexus, ["nexus", "run", "fix canonical seam"])
    assert res.exit_code == 0, res.output
    assert called["task_text"] == "fix canonical seam"
    assert called["project_root"] == tmp_path


def test_run_fails_closed_when_canonical_executor_returns_false(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(cli_mod, "_execute_single_run_task", lambda *_args, **_kwargs: False)
    runner = CliRunner()
    res = runner.invoke(cli_mod.nexus, ["nexus", "run", "broken-task"])
    assert res.exit_code != 0
    assert "[run-classification] runtime_defect" in res.output
