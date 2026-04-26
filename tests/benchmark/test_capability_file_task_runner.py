from pathlib import Path
from types import SimpleNamespace

from scripts.bench.capability_ab_runner import CapabilityTask
from scripts.bench.capability_file_task_runner import (
    _build_inline_prompt,
    _infer_target_function,
    _extract_written_file_from_stdout,
    _required_behavior_from_task,
    _replace_function_source,
    _write_task_file,
    _to_ab_row,
    run_without_nexus_baseline,
    run_task,
)


def test_file_task_runner_verifies_cross_module_candidate(monkeypatch, tmp_path: Path):
    task = CapabilityTask(
        id="flash-xmod-001",
        difficulty="hard",
        task_type="cross_module_bug",
        task_desc="Fix cross-module retry backoff",
        target_file="runtime/retry_policy.py",
        test_file="tests/test_retry_policy.py",
        success_criteria="all_target_tests_pass",
        fixture_kind="cross_module_retry",
    )

    def fake_run(cmd, **kwargs):
        if cmd and "gemini" in str(cmd[0]):
            prompt = cmd[cmd.index("-p") + 1]
            output_path = Path(str(prompt).split(" to ")[1].split(". ")[0])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                "from runtime.settings import RETRY_LIMITS\n\n"
                "def compute_backoff(attempt: int) -> int:\n"
                "    if attempt <= 0:\n"
                "        raise ValueError('attempt must be positive')\n"
                "    return min(RETRY_LIMITS['max_delay'], RETRY_LIMITS['base_delay'] * (2 ** (attempt - 1)))\n",
                encoding="utf-8",
            )
            return SimpleNamespace(returncode=0, stdout='{"response":"ok","stats":{"models":{"m":{"tokens":{"total":12}}}}}', stderr="")
        return SimpleNamespace(returncode=0, stdout=".", stderr="")

    monkeypatch.setattr("scripts.bench.capability_file_task_runner._resolve_gemini_bin", lambda: "/usr/bin/gemini")
    monkeypatch.setattr("scripts.bench.capability_file_task_runner.subprocess.run", fake_run)

    result = run_task(
        repo_root=tmp_path,
        task=task,
        model="gemini-3-flash-preview",
        timeout_sec=30,
        output_dir=tmp_path / "reports",
    )

    assert result.status == "SUCCESS"
    assert result.semantic_status == "VERIFIED"
    assert result.model_calls == 1
    assert result.total_tokens == 12
    assert Path(result.task_file).exists()
    assert Path(result.output_file).exists()


def test_extract_written_file_from_nested_gemini_response(tmp_path: Path):
    candidate = tmp_path / "candidate.py"
    candidate.write_text("print('ok')\n", encoding="utf-8")
    stdout = (
        '{"response": "{\\"status\\": \\"success\\", '
        f'\\"file_written\\": \\"{candidate}\\"' 
        '}"}'
    )

    assert _extract_written_file_from_stdout(stdout) == candidate


def test_extract_written_file_accepts_file_path_key(tmp_path: Path):
    candidate = tmp_path / "candidate.py"
    candidate.write_text("print('ok')\n", encoding="utf-8")
    stdout = (
        '{"response": "{\\"status\\": \\"success\\", '
        f'\\"file_path\\": \\"{candidate}\\"'
        '}"}'
    )

    assert _extract_written_file_from_stdout(stdout) == candidate


def test_file_task_result_can_be_mapped_to_ab_row(monkeypatch, tmp_path: Path):
    task = CapabilityTask(
        id="flash-xmod-001",
        difficulty="hard",
        task_type="cross_module_bug",
        task_desc="Fix cross-module retry backoff",
        target_file="runtime/retry_policy.py",
        test_file="tests/test_retry_policy.py",
        success_criteria="all_target_tests_pass",
        fixture_kind="cross_module_retry",
    )

    def fake_run(cmd, **kwargs):
        return SimpleNamespace(returncode=0, stdout=".", stderr="")

    monkeypatch.setattr("scripts.bench.capability_file_task_runner.subprocess.run", fake_run)
    result = run_without_nexus_baseline(repo_root=tmp_path, task=task, timeout_sec=30, output_dir=tmp_path / "reports")
    row = _to_ab_row(result, mode="without_nexus", model_label="local-baseline", llm_enabled=False, trust_mismatch=True)

    assert row["mode"] == "without_nexus"
    assert row["model_profile"]["runner_mode"] == "file_task"
    assert row["task_duration_sec"] == row["duration_sec"]
    assert row["report_trust_mismatch"] is True


def test_lean_task_file_excludes_test_body_but_keeps_support_module(tmp_path: Path):
    case_dir = tmp_path / "case"
    runtime_dir = case_dir / "runtime"
    tests_dir = case_dir / "tests"
    runtime_dir.mkdir(parents=True)
    tests_dir.mkdir(parents=True)
    target_file = runtime_dir / "retry_policy.py"
    support_file = runtime_dir / "settings.py"
    test_file = tests_dir / "test_retry_policy.py"
    target_file.write_text("def compute_backoff(attempt):\n    return 0\n", encoding="utf-8")
    support_file.write_text("RETRY_LIMITS = {'base_delay': 1, 'max_delay': 8}\n", encoding="utf-8")
    test_file.write_text("def test_secret_assertion():\n    assert compute_backoff(4) == 8\n", encoding="utf-8")
    task = CapabilityTask(
        id="flash-xmod-001",
        difficulty="hard",
        task_type="cross_module_bug",
        task_desc="Fix cross-module retry backoff",
        target_file="runtime/retry_policy.py",
        test_file="tests/test_retry_policy.py",
        success_criteria="all_target_tests_pass",
        fixture_kind="cross_module_retry",
    )

    task_file = _write_task_file(
        task=task,
        case_dir=case_dir,
        target_file=target_file,
        test_file=test_file,
        output_file=case_dir / "candidate.py",
        test_command=["uv", "run", "pytest", "-q", str(test_file)],
        context_mode="lean",
    )

    text = task_file.read_text(encoding="utf-8")
    assert "runtime/retry_policy.py" in text
    assert "runtime/settings.py" in text
    assert "test_secret_assertion" not in text


def test_micro_task_file_excludes_support_body_but_keeps_behavior_summary(tmp_path: Path):
    case_dir = tmp_path / "case"
    runtime_dir = case_dir / "runtime"
    tests_dir = case_dir / "tests"
    runtime_dir.mkdir(parents=True)
    tests_dir.mkdir(parents=True)
    target_file = runtime_dir / "retry_policy.py"
    support_file = runtime_dir / "settings.py"
    test_file = tests_dir / "test_retry_policy.py"
    target_file.write_text("from runtime.settings import RETRY_LIMITS\n\ndef compute_backoff(attempt):\n    return 0\n", encoding="utf-8")
    support_file.write_text("RETRY_LIMITS = {'base_delay': 1, 'max_delay': 8}\n", encoding="utf-8")
    test_file.write_text("def test_secret_assertion():\n    assert compute_backoff(4) == 8\n", encoding="utf-8")
    task = CapabilityTask(
        id="flash-xmod-001",
        difficulty="hard",
        task_type="cross_module_bug",
        task_desc="Fix cross-module retry backoff. runtime/retry_policy.py must read RETRY_LIMITS from runtime/settings.py and return exponential delays: attempt 1 = 1, attempt 2 = 2, attempt 3 = 4, attempt 4 = 8.",
        target_file="runtime/retry_policy.py",
        test_file="tests/test_retry_policy.py",
        success_criteria="all_target_tests_pass",
        fixture_kind="cross_module_retry",
    )

    task_file = _write_task_file(
        task=task,
        case_dir=case_dir,
        target_file=target_file,
        test_file=test_file,
        output_file=case_dir / "candidate.py",
        test_command=["uv", "run", "pytest", "-q", str(test_file)],
        context_mode="micro",
    )

    text = task_file.read_text(encoding="utf-8")
    assert "runtime/retry_policy.py" in text
    assert "RETRY_LIMITS = {'base_delay': 1" not in text
    assert "test_secret_assertion" not in text
    assert "capped exponential backoff" in text


def test_required_behavior_summarizes_retry_cases():
    out = _required_behavior_from_task(
        "Fix cross-module retry backoff. runtime/retry_policy.py must read RETRY_LIMITS from runtime/settings.py and return exponential delays: attempt 1 = 1, attempt 2 = 2, attempt 3 = 4, attempt 4 = 8."
    )
    assert "compute_backoff" in out
    assert "1, 2, 4, 8" in out


def test_inline_prompt_embeds_task_and_requests_source_only(tmp_path: Path):
    task_file = tmp_path / "task.md"
    output_file = tmp_path / "candidate.py"
    task_file.write_text("## Objective\nFix the bug\n", encoding="utf-8")

    prompt = _build_inline_prompt(task_file=task_file, output_file=output_file)

    assert "Fix the bug" in prompt
    assert "Return ONLY the full updated source code" in prompt
    assert str(output_file) in prompt


def test_replace_function_source_preserves_imports_and_replaces_only_function():
    source = (
        "from runtime.settings import RETRY_LIMITS\n\n"
        "def compute_backoff(attempt: int) -> int:\n"
        "    return RETRY_LIMITS['base_delay']\n\n"
        "OTHER = 1\n"
    )
    fn = (
        "def compute_backoff(attempt: int) -> int:\n"
        "    if attempt <= 0:\n"
        "        raise ValueError('attempt must be positive')\n"
        "    return min(RETRY_LIMITS['max_delay'], RETRY_LIMITS['base_delay'] * (2 ** (attempt - 1)))\n"
    )

    out = _replace_function_source(source, "compute_backoff", fn)

    assert "from runtime.settings import RETRY_LIMITS" in out
    assert "OTHER = 1" in out
    assert "return RETRY_LIMITS['base_delay']\n\nOTHER" not in out
    assert "2 ** (attempt - 1)" in out


def test_infer_target_function_prefers_task_description(tmp_path: Path):
    target = tmp_path / "target.py"
    target.write_text("def other():\n    pass\n", encoding="utf-8")

    assert _infer_target_function("Fix compute_backoff behavior", target) == "compute_backoff"
