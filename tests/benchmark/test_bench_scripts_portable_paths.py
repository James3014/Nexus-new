from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

import pytest

BENCH_SCRIPTS = [
    "check_post_wiring_regression_readiness.py",
    "rebuild_asr_ceiling_benchmark.py",
    "rebuild_aw_ceiling_rerun.py",
    "rebuild_ax_substrate.py",
    "rebuild_ay_ceiling_rerun.py",
    "rebuild_bc_optimization.py",
    "rebuild_bd_ceiling.py",
    "rebuild_bdc_audit.py",
    "rebuild_bde_audit.py",
    "rebuild_be_optimization.py",
]


@pytest.mark.parametrize(
    "script_name",
    [pytest.param(name, id=name) for name in BENCH_SCRIPTS],
)
def test_bench_script_has_no_user_specific_path(script_name: str) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "bench" / script_name
    content = script_path.read_text(encoding="utf-8")
    assert "jameschen" not in content, f"{script_name} contains user name 'jameschen'"
    assert "/Users/" not in content, f"{script_name} contains user path '/Users/'"


@pytest.mark.parametrize(
    "script_name",
    [pytest.param(name, id=name) for name in BENCH_SCRIPTS],
)
def test_bench_script_repo_root_resolves_to_checkout(script_name: str) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "bench" / script_name
    module_name = f"_bench_script_{script_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None, f"Failed to load spec for {script_path}"
    assert spec.loader is not None, f"Failed to get loader for {script_path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "REPO_ROOT"), f"{script_name} does not define REPO_ROOT"
    assert module.REPO_ROOT == repo_root, (
        f"{script_name} REPO_ROOT ({module.REPO_ROOT}) != checkout root ({repo_root})"
    )


def test_rebuild_bd_ceiling_entrypoint_template_uses_repo_root() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "bench" / "rebuild_bd_ceiling.py"
    module_name = "_bench_inspect_rebuild_bd_ceiling"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None, f"Failed to load spec for {script_path}"
    assert spec.loader is not None, f"Failed to get loader for {script_path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = inspect.getsource(module.step_bd2)

    default_output_lines = [line for line in source.splitlines() if "DEFAULT_OUTPUT =" in line]
    assert len(default_output_lines) == 1, (
        f"Expected 1 DEFAULT_OUTPUT line in step_bd2, found {len(default_output_lines)}"
    )
    line = default_output_lines[0]
    assert "/Users/" not in line, f"DEFAULT_OUTPUT template contains '/Users/': {line}"
    assert "REPO_ROOT" in line, f"DEFAULT_OUTPUT template does not reference REPO_ROOT: {line}"
