from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.ops.check_golden_schema_snapshots import check_golden_schema_snapshots


def test_golden_schema_snapshot_check_passes_repository_manifest():
    report = check_golden_schema_snapshots()

    assert report["status"] == "PASS"
    assert report["checked"]


def test_golden_schema_snapshot_check_blocks_hash_drift(tmp_path: Path):
    snapshot = tmp_path / "docs" / "testing" / "golden_schemas" / "sample.json"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text('{"schema_version":"sample.v1","field":"value"}\n', encoding="utf-8")
    manifest = snapshot.parent / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "nexus.golden_schema_manifest.v1",
                "snapshots": [
                    {
                        "path": "docs/testing/golden_schemas/sample.json",
                        "schema_version": "sample.v1",
                        "sha256": "deadbeef",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = check_golden_schema_snapshots(root=tmp_path, manifest_path=manifest)

    assert report["status"] == "FAIL"
    assert report["failures"][0]["reason"] == "sha256_mismatch"


def test_golden_schema_snapshot_check_blocks_crlf(tmp_path: Path):
    snapshot = tmp_path / "docs" / "testing" / "golden_schemas" / "sample.json"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_bytes(b'{\r\n  "schema_version": "sample.v1"\r\n}\r\n')
    digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    manifest = snapshot.parent / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "nexus.golden_schema_manifest.v1",
                "snapshots": [
                    {
                        "path": "docs/testing/golden_schemas/sample.json",
                        "schema_version": "sample.v1",
                        "sha256": digest,
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = check_golden_schema_snapshots(root=tmp_path, manifest_path=manifest)

    assert report["status"] == "FAIL"
    assert "CRLF newline detected" in report["failures"][0]["reason"]
