import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


def _run(
    command: list[str], *, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_clean_wheel_contains_and_runs_registered_cli_entrypoints(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    uv = shutil.which("uv")
    assert uv is not None, "uv is required by the repository verification environment"

    dist_dir = tmp_path / "dist"
    build = _run([uv, "build", "--wheel", "--out-dir", str(dist_dir)], cwd=repo_root)
    assert build.returncode == 0, build.stdout + build.stderr

    wheels = sorted(dist_dir.glob("*.whl"))
    assert len(wheels) == 1, f"Expected one freshly built wheel, found {wheels}"

    wheel_file = wheels[0]
    with zipfile.ZipFile(wheel_file, "r") as zf:
        namelist = set(zf.namelist())

    assert "scripts/__init__.py" in namelist
    assert "scripts/engine/nexus_cli.py" in namelist
    assert "scripts/ops/nexus_cueline_worker.py" in namelist

    venv_dir = tmp_path / "venv"
    create_venv = _run([sys.executable, "-m", "venv", str(venv_dir)], cwd=tmp_path)
    assert create_venv.returncode == 0, create_venv.stdout + create_venv.stderr

    venv_python = venv_dir / "bin" / "python"
    install = _run(
        [uv, "pip", "install", "--python", str(venv_python), str(wheel_file)],
        cwd=tmp_path,
    )
    assert install.returncode == 0, install.stdout + install.stderr

    clean_env = os.environ.copy()
    clean_env.pop("PYTHONPATH", None)
    nexus_help = _run([str(venv_dir / "bin" / "nexus"), "--help"], cwd=tmp_path, env=clean_env)
    assert nexus_help.returncode == 0, nexus_help.stdout + nexus_help.stderr

    cueline = _run([str(venv_dir / "bin" / "nexus-cueline-worker")], cwd=tmp_path, env=clean_env)
    assert cueline.returncode == 1
    assert "Empty input provided" in cueline.stderr
    assert "ModuleNotFoundError" not in cueline.stderr
