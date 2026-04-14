from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_mod


def test_run_fails_fast_when_task_requests_file_output_without_output_file():
    runner = CliRunner()
    res = runner.invoke(cli_mod.nexus, ["nexus", "run", "請將結果寫入 /tmp/result.md"])
    assert res.exit_code != 0
    assert "--output-file" in res.output


def test_run_writes_output_file_when_explicit_path_provided(monkeypatch, tmp_path):
    class _FakeHub:
        def __init__(self, *_args, **_kwargs):
            pass

        def make_pre_routing_decision(self, *_args, **_kwargs):
            return {"nas_autotune_needed": False}

    monkeypatch.setattr("nexus.core.context_hub.ContextHub", _FakeHub)
    monkeypatch.setattr(cli_mod, "REPO_ROOT", tmp_path)

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

