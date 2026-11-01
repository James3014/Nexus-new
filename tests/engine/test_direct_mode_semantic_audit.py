from nexus.engine.direct_mode import evaluate_direct_mode_completion


def test_evaluate_direct_mode_completion_detects_unchanged_targets_and_failed_verify(monkeypatch, tmp_path):
    calls = []

    class _Res:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def _fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:3] == ["git", "status", "--short"]:
            return _Res(returncode=0, stdout="")
        return _Res(returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr("nexus.engine.direct_mode.subprocess.run", _fake_run)
    # Verify commands run through the process-group reaping runner (#3052).
    monkeypatch.setattr("nexus.core.argv_command.run_reaping_process_group", _fake_run)

    result = evaluate_direct_mode_completion(
        project_root=tmp_path,
        task_desc=(
            "失敗測試:\n"
            "uv run pytest tests/engine/test_pipeline_stages.py::test_stage_plan -q\n"
            "修法:\n"
            "- nexus/engine/pipeline.py:339\n"
        ),
    )

    assert result["enabled"] is True
    assert "direct_mode_target_files_unchanged" in result["semantic_failures"]
    assert any(item.startswith("direct_mode_verify_failed:") for item in result["semantic_failures"])
    assert result["verify_results"][0]["exit_code"] == 1


def test_evaluate_direct_mode_completion_passes_when_targets_changed_and_verify_passes(monkeypatch, tmp_path):
    class _Res:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def _fake_run(cmd, **kwargs):
        if cmd[:3] == ["git", "status", "--short"]:
            target = cmd[-1]
            if target == "nexus/engine/pipeline.py":
                return _Res(returncode=0, stdout=" M nexus/engine/pipeline.py\n")
            return _Res(returncode=0, stdout="")
        return _Res(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("nexus.engine.direct_mode.subprocess.run", _fake_run)
    # Verify commands run through the process-group reaping runner (#3052).
    monkeypatch.setattr("nexus.core.argv_command.run_reaping_process_group", _fake_run)

    result = evaluate_direct_mode_completion(
        project_root=tmp_path,
        task_desc=(
            "失敗測試:\n"
            "uv run pytest tests/engine/test_pipeline_stages.py::test_stage_plan -q\n"
            "修法:\n"
            "- nexus/engine/pipeline.py:339\n"
        ),
    )

    assert result["enabled"] is True
    assert result["semantic_failures"] == []
    assert result["changed_targets"] == ["nexus/engine/pipeline.py"]
    assert result["verify_results"][0]["exit_code"] == 0


def test_evaluate_direct_mode_completion_never_runs_task_text_through_a_shell(tmp_path):
    # #2635: the verify command is parsed from task text, so a "; cmd" tail must not run.
    marker = tmp_path / "injected"
    result = evaluate_direct_mode_completion(
        project_root=tmp_path,
        task_desc=(
            "失敗測試:\n"
            f"pytest --version ; touch {marker}\n"
            "修法:\n"
            "- nexus/engine/pipeline.py:339\n"
        ),
    )

    assert result["enabled"] is True
    assert not marker.exists()
    assert result["verify_results"][0]["exit_code"] != 0
    assert any(item.startswith("direct_mode_verify_failed:") for item in result["semantic_failures"])
