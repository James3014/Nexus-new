#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.ops.strict_file_discovery import read_nonempty_json

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPO_ROOT / "docs" / "testing" / "golden_schemas" / "manifest.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_text_lf(path: Path) -> str:
    raw = path.read_bytes()
    if b"\r\n" in raw:
        raise ValueError(f"CRLF newline detected in golden schema: {path}")
    return raw.decode("utf-8")


def check_golden_schema_snapshots(*, root: Path = REPO_ROOT, manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest_file = manifest_path if manifest_path.is_absolute() else root / manifest_path
    manifest_text = _read_text_lf(manifest_file)
    manifest = json.loads(manifest_text)
    failures: list[dict[str, str]] = []
    if manifest.get("schema_version") != "nexus.golden_schema_manifest.v1":
        failures.append({"path": str(manifest_file), "reason": "unsupported_manifest_schema"})

    snapshots = manifest.get("snapshots", [])
    if not isinstance(snapshots, list) or not snapshots:
        failures.append({"path": str(manifest_file), "reason": "snapshots_missing"})
        snapshots = []

    checked: list[dict[str, str]] = []
    for row in snapshots:
        if not isinstance(row, dict):
            failures.append({"path": str(manifest_file), "reason": "invalid_snapshot_row"})
            continue
        rel_path = str(row.get("path") or "")
        expected_hash = str(row.get("sha256") or "")
        expected_schema = str(row.get("schema_version") or "")
        snapshot_path = root / rel_path
        try:
            _read_text_lf(snapshot_path)
            payload = read_nonempty_json(snapshot_path, label="golden schema snapshot")
        except Exception as exc:
            failures.append({"path": rel_path, "reason": f"{type(exc).__name__}:{exc}"})
            continue
        if expected_schema and isinstance(payload, dict) and payload.get("schema_version") != expected_schema:
            failures.append({"path": rel_path, "reason": "snapshot_schema_version_mismatch"})
        actual_hash = _sha256(snapshot_path)
        if actual_hash != expected_hash:
            failures.append({"path": rel_path, "reason": "sha256_mismatch", "actual_sha256": actual_hash})
        checked.append({"path": rel_path, "sha256": actual_hash})

    return {
        "schema_version": "nexus.golden_schema_snapshot_check.v1",
        "status": "PASS" if not failures else "FAIL",
        "manifest_path": str(manifest_file),
        "checked": checked,
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate immutable Nexus golden schema snapshots.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    args = parser.parse_args(argv)
    report = check_golden_schema_snapshots(root=Path(args.repo_root).resolve(), manifest_path=Path(args.manifest))
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
