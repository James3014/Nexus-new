import zipfile
from pathlib import Path


def test_clean_wheel_contains_registered_cli_entrypoints():
    repo_root = Path(__file__).resolve().parents[2]
    dist_dir = repo_root / "dist"
    wheels = list(dist_dir.glob("*.whl"))
    assert len(wheels) >= 1, "Expected at least one built wheel in dist/"

    wheel_file = wheels[0]
    with zipfile.ZipFile(wheel_file, "r") as zf:
        namelist = set(zf.namelist())

    # Prove scripts package and both console entrypoint targets exist in wheel
    assert "scripts/__init__.py" in namelist
    assert "scripts/engine/nexus_cli.py" in namelist
    assert "scripts/ops/nexus_cueline_worker.py" in namelist
