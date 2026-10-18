"""The governance manifest must never silently go stale again (#2624)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from nexus.delivery.anti_drift import AntiDrift
from nexus.delivery.evidence_verifier import EvidenceVerifier
from scripts.ops.governance_manifest import MANIFEST_RELATIVE_PATH, check_manifest, write_manifest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "governance_manifest.py"


def _copy_sealed_tree(dst: Path) -> Path:
    for rel in [*AntiDrift.IMMUTABLE_FILES, str(MANIFEST_RELATIVE_PATH)]:
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, target)
    return dst


def test_repository_manifest_is_in_sync_with_immutable_files():
    stale = check_manifest(ROOT)
    assert stale == [], (
        f"immutable files changed without the manifest: {stale}; "
        "run python3 scripts/ops/governance_manifest.py --write in the same PR"
    )


def test_manifest_covers_exactly_the_immutable_files():
    manifest = json.loads((ROOT / MANIFEST_RELATIVE_PATH).read_text())
    assert sorted(manifest) == sorted(AntiDrift.IMMUTABLE_FILES)


def test_check_flags_an_immutable_file_changed_without_manifest(tmp_path):
    root = _copy_sealed_tree(tmp_path)
    assert check_manifest(root) == []
    changed = root / "nexus/delivery/replay_runner.py"
    changed.write_text(changed.read_text() + "\n# drift\n")
    assert check_manifest(root) == ["nexus/delivery/replay_runner.py"]

    write_manifest(root)
    assert check_manifest(root) == []


def test_cli_check_exit_codes(tmp_path):
    root = _copy_sealed_tree(tmp_path)
    ok = subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "--root", str(root)],
        capture_output=True,
        text=True,
    )
    assert ok.returncode == 0, ok.stderr
    assert json.loads(ok.stdout)["in_sync"] is True

    (root / "scripts/ops/nexus_delivery_gate.sh").write_text("echo drift\n")
    bad = subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "--root", str(root)],
        capture_output=True,
        text=True,
    )
    assert bad.returncode == 1
    assert json.loads(bad.stdout)["stale"] == ["scripts/ops/nexus_delivery_gate.sh"]
    assert "--write" in bad.stderr

    regen = subprocess.run(
        [sys.executable, str(SCRIPT), "--write", "--root", str(root)],
        capture_output=True,
        text=True,
    )
    assert regen.returncode == 0, regen.stderr
    again = subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "--root", str(root)],
        capture_output=True,
        text=True,
    )
    assert again.returncode == 0


def test_missing_manifest_is_not_configured_not_drift(tmp_path):
    res = EvidenceVerifier(tmp_path).verify({"version": "1.1.0", "code_artifacts": []})
    assert res["status"] == "NOT_CONFIGURED"
    assert res["reason"] == "governance_manifest_not_configured"
    assert res["status"] != "REJECTED"
    # Nothing was verified, so trust stays LOW (deleting the manifest must not open the gate).
    assert res["overall_trust"] == "LOW"
    assert check_manifest(tmp_path) == list(AntiDrift.IMMUTABLE_FILES)


def test_drifted_manifest_is_still_rejected(tmp_path):
    root = _copy_sealed_tree(tmp_path)
    (root / "nexus/delivery/anti_drift.py").write_text("# tampered\n")
    res = EvidenceVerifier(root).verify({"version": "1.1.0", "code_artifacts": []})
    assert res["status"] == "REJECTED"
    assert res["reason"] == "governance_drift_detected"
