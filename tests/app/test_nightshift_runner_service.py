import pytest
from pathlib import Path
from nexus.app.nightshift_runner_service import AutoResearchNightShift

def test_nightshift_service_init(tmp_path: Path):
    runner = AutoResearchNightShift(project_root=tmp_path, task="test-task")
    assert runner.task == "test-task"
    assert runner.project_root == tmp_path.resolve()


def test_nightshift_uses_injected_context_hub(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    hub = object()

    runner = AutoResearchNightShift(project_root=tmp_path, task="test-task", context_hub=hub)

    assert runner.hub is hub


def test_nightshift_policy_bypass_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NIGHTSHIFT_BYPASS_POLICY", "1")
    runner = AutoResearchNightShift(project_root=tmp_path, task="test-task")
    assert runner._check_policy_readiness() is True


def test_nightshift_tier1_validation_uses_py_compile_for_nongit_fixture(tmp_path: Path):
    runner = AutoResearchNightShift(
        project_root=tmp_path,
        task="benchmark task",
        target_file="demo.py",
        test_file="tests",
    )
    (tmp_path / "demo.py").write_text("def ok() -> int:\n    return 1\n", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_demo.py").write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
        "from demo import ok\n\n"
        "def test_ok():\n"
        "    assert ok() == 1\n",
        encoding="utf-8",
    )

    ok, msg = runner._run_tier1_validation(tmp_path)
    assert ok is True
    assert msg == "tier1_pass"
