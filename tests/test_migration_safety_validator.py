import importlib.util
import shutil
import subprocess
from pathlib import Path


def _load_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "core"
        / "migration_safety_validator.py"
    )
    spec = importlib.util.spec_from_file_location("migration_safety_validator", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _init_repo(tmp_path: Path) -> Path:
    if shutil.which("git") is None:
        raise RuntimeError("git is required for this test")
    subprocess.check_call(["git", "init"], cwd=tmp_path)
    subprocess.check_call(["git", "config", "user.email", "test@example.com"], cwd=tmp_path)
    subprocess.check_call(["git", "config", "user.name", "Test"], cwd=tmp_path)
    (tmp_path / "README.md").write_text("x\n", encoding="utf-8")
    subprocess.check_call(["git", "add", "README.md"], cwd=tmp_path)
    subprocess.check_call(["git", "commit", "-m", "init"], cwd=tmp_path)
    return tmp_path


def test_manifest_contract_requires_core_sections(tmp_path):
    mod = _load_module()
    repo = _init_repo(tmp_path)
    (repo / "task_manifest.yaml").write_text("version: v1\n", encoding="utf-8")
    result = mod.check_manifest_contract(repo)
    assert result.ok is False
    assert "missing keys" in result.message


def test_baseline_tag_check_passes_with_tag(tmp_path):
    mod = _load_module()
    repo = _init_repo(tmp_path)
    subprocess.check_call(["git", "tag", "baseline-20260327"], cwd=repo)
    result = mod.check_baseline_tag(repo)
    assert result.ok is True


def test_run_fails_without_baseline_tag(tmp_path):
    mod = _load_module()
    repo = _init_repo(tmp_path)
    (repo / "task_manifest.yaml").write_text(
        "version: v1\ndefaults:\n  max_retry: 1\ntasks:\n  - id: t\n",
        encoding="utf-8",
    )
    rc = mod.run(repo, check_scope=False)
    assert rc == 1
