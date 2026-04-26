from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.soul_artifact_vault import build_vault_record


def _write_receipt(tmp_path: Path, artifact_path: Path, artifact_sha: str) -> Path:
    receipt_path = tmp_path / "delivery_gate.json"
    payload = {
        "branch": "feat/test",
        "head": "abc123",
        "steps": [
            {"name": "integrity", "exit_code": 0},
            {"name": "acceptance", "exit_code": 0},
        ],
        "artifacts": {
            "evidence": {"path": str(artifact_path), "sha256": artifact_sha},
        },
    }
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")
    return receipt_path


def test_soul_artifact_vault_passes_with_valid_artifact_hash(tmp_path: Path) -> None:
    artifact = tmp_path / "evidence.json"
    artifact.write_text("{}", encoding="utf-8")
    import hashlib
    expected = hashlib.sha256(artifact.read_bytes()).hexdigest()
    receipt = _write_receipt(tmp_path, artifact, expected)
    payload, ok = build_vault_record(receipt_path=receipt, output_dir=tmp_path / "records")
    assert ok is True
    assert payload["verification"]["artifacts_ok"] is True
    assert payload["verification"]["trace_ok"] is True
    assert Path(payload["record_path"]).exists()
    assert Path(payload["checksum_path"]).exists()


def test_soul_artifact_vault_fails_on_hash_mismatch(tmp_path: Path) -> None:
    artifact = tmp_path / "evidence.json"
    artifact.write_text("{}", encoding="utf-8")
    receipt = _write_receipt(tmp_path, artifact, "deadbeef")
    payload, ok = build_vault_record(receipt_path=receipt, output_dir=tmp_path / "records")
    assert ok is False
    assert payload["verification"]["artifacts_ok"] is False
