from nexus.engine.direct_mode import analyze_task_spec, extract_target_files, extract_verify_commands


def test_analyze_task_spec_enables_direct_mode_for_explicit_repair_spec():
    task_desc = """
    失敗測試:
    1 uv run pytest tests/engine/test_pipeline_stages.py::test_stage_plan
    根因: planner output contract drift
    修法:
    - nexus/engine/pipeline_stages.py:112 tighten fallback behavior
    - tests/engine/test_pipeline_stages.py:47 align assertion
    """

    spec = analyze_task_spec(task_desc)
    assert spec.enabled is True
    assert "nexus/engine/pipeline_stages.py" in spec.target_files
    assert any(cmd.startswith("uv run pytest") for cmd in spec.verify_commands)


def test_analyze_task_spec_keeps_default_route_for_general_request():
    spec = analyze_task_spec("請幫我看一下這個問題，先分析可能原因。")
    assert spec.enabled is False
    assert spec.target_files == []
    assert spec.verify_commands == []


def test_extract_helpers_dedupe_files_and_verify_commands():
    text = """
    - nexus/engine/pipeline.py:90
    - nexus/engine/pipeline.py:140
    1 uv run pytest tests/engine/test_pipeline_stages.py -q
    2 uv run pytest tests/engine/test_pipeline_stages.py -q
    """
    files = extract_target_files(text)
    verify_commands = extract_verify_commands(text)
    assert files == [
        "nexus/engine/pipeline.py",
        "tests/engine/test_pipeline_stages.py",
    ]
    assert verify_commands == ["uv run pytest tests/engine/test_pipeline_stages.py -q"]
