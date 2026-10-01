"""Regression coverage for the legacy Core package namespace retirement."""

import shutil
import subprocess
import zipfile
from pathlib import Path


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)


def _build_wheel(tmp_path: Path) -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    uv = shutil.which("uv")
    assert uv is not None, "uv is required by the repository verification environment"

    dist_dir = tmp_path / "dist"
    build = _run([uv, "build", "--wheel", "--out-dir", str(dist_dir)], cwd=repo_root)
    assert build.returncode == 0, build.stdout + build.stderr

    wheels = sorted(dist_dir.glob("*.whl"))
    assert len(wheels) == 1, f"Expected one freshly built wheel, found {wheels}"
    return wheels[0]


def test_legacy_wheel_releases_product_namespace_and_duplicate_certify_cli(tmp_path):
    wheel_file = _build_wheel(tmp_path)

    with zipfile.ZipFile(wheel_file) as wheel:
        names = set(wheel.namelist())
        entry_points = wheel.read("nexus_legacy-28.3.0.dist-info/entry_points.txt").decode("utf-8")

    assert not any(name == "product" or name.startswith("product/") for name in names)
    assert "nexus-certify" not in entry_points
    assert "nexus=scripts.engine.nexus_cli:nexus" in entry_points
    assert "scripts/__init__.py" in names
    assert "scripts/engine/nexus_cli.py" in names
