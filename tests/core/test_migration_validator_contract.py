import os
import subprocess
import sys
from pathlib import Path

from nexus.core.migration_validator import MigrationValidator


def test_migration_validator_behavior(tmp_path: Path):
    # Test zombie check when no zombies present
    validator = MigrationValidator(tmp_path)
    status, msg = validator.check_zombie_scripts()
    assert status is True
    assert "No zombies found" in msg

    # Test zombie check when zombie script exists
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "linter.py").write_text("# zombie")
    status, msg = validator.check_zombie_scripts()
    assert status is False
    assert "linter.py" in msg

    # Test legacy import check
    test_file = tmp_path / "sample.py"
    test_file.write_text("import scripts.legacy.foo")
    safe, import_msg = validator.check_legacy_imports(test_file)
    assert safe is False
    assert "scripts/legacy" in import_msg

    safe_file = tmp_path / "safe.py"
    safe_file.write_text("import nexus.core.migration_validator")
    safe, import_msg = validator.check_legacy_imports(safe_file)
    assert safe is True

    # Test run_full_scan
    (scripts_dir / "linter.py").unlink(missing_ok=True)
    clean_val = MigrationValidator(tmp_path)
    assert clean_val.run_full_scan() is True


def test_migration_safety_validator_script_entrypoint():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "migrationsafetyvalidator.py"

    env = {**os.environ, "PYTHONPATH": str(repo_root)}
    res = subprocess.run(
        [sys.executable, str(script_path), "--mode", "gatekeeper", "--changes", "nexus/core"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert res.returncode == 0
    assert "Scanning changes in 'nexus/core'" in res.stdout
    assert "passed safety audit" in res.stdout
