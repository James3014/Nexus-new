import shutil
import subprocess
import sys
from pathlib import Path

from scripts.ops.seal_governance import IMMUTABLE_PATHS

REPO_ROOT = Path(__file__).resolve().parents[2]
SEAL_SCRIPTS = ("scripts/ops/seal_governance.py", "scripts/ops/verify_governance_seal.py")


def _sandbox(tmp_path: Path) -> Path:
    """Copy the seal scripts and the sealed files into an isolated tree.

    The seal (.nexus/config/governance_seal.json) is a gitignored local artifact,
    so a fresh checkout (CI) has none; the test used to depend on a seal left
    behind by an earlier local run and to tamper with the real repository files.
    The scripts resolve every path relative to the working directory, so running
    them with cwd=sandbox exercises the same code without touching the checkout.
    """
    sandbox = tmp_path / "repo"
    for rel in (*SEAL_SCRIPTS, *IMMUTABLE_PATHS):
        source = REPO_ROOT / rel
        if source.exists():
            target = sandbox / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    return sandbox


def _run(sandbox: Path, script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, script], cwd=sandbox, capture_output=True, text=True, check=False
    )


def test_stage_e(tmp_path: Path):
    print("🧪 Running Stage E Validation...")
    sandbox = _sandbox(tmp_path)
    target_file = sandbox / "scripts/ops/diagnose_regression.py"
    original_content = target_file.read_text()

    # 0. No seal yet: verification fails closed
    res = _run(sandbox, "scripts/ops/verify_governance_seal.py")
    assert res.returncode != 0
    assert "no governance seal found" in res.stdout.lower()

    # 1. Verification with Seal
    print("Case 1: Verification (Initial)")
    assert _run(sandbox, "scripts/ops/seal_governance.py").returncode == 0
    res = _run(sandbox, "scripts/ops/verify_governance_seal.py")
    assert res.returncode == 0

    # 2. Modify and Check Drift
    print("Case 2: Detecting Drift")
    target_file.write_text(original_content + "\n# TAMPERED\n")
    res = _run(sandbox, "scripts/ops/verify_governance_seal.py")
    assert res.returncode != 0
    assert "drift detected" in res.stdout.lower()

    # 3. Reseal and Verify
    print("Case 3: Reseal and Verify")
    assert _run(sandbox, "scripts/ops/seal_governance.py").returncode == 0
    res = _run(sandbox, "scripts/ops/verify_governance_seal.py")
    assert res.returncode == 0

    # The real checkout was never touched.
    assert (REPO_ROOT / "scripts/ops/diagnose_regression.py").read_text() == original_content
    print("✅ Stage E Validation PASS")
