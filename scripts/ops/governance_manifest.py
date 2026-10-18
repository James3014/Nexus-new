#!/usr/bin/env python3
"""Check or regenerate nexus/config/governance_manifest.json (#2624).

The manifest seals the sha256 of every ``AntiDrift.IMMUTABLE_FILES`` entry. When one of
those files changes without the manifest, ``EvidenceVerifier.verify`` rejects every task
with ``governance_drift_detected`` (the manifest was stale from 2026-04-19 to 2026-10-11).

    python3 scripts/ops/governance_manifest.py --check   # exit 1 and list drift
    python3 scripts/ops/governance_manifest.py --write   # regenerate after an intended change

``tests/ops/test_governance_manifest_sync.py`` runs ``--check`` semantics in CI, so a PR that
changes an immutable file must regenerate the manifest in the same PR.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nexus.delivery.anti_drift import AntiDrift  # noqa: E402

MANIFEST_RELATIVE_PATH = Path("nexus/config/governance_manifest.json")


def check_manifest(project_root: Path) -> list[str]:
    """Return the immutable files whose hash differs from the manifest (all of them if absent)."""
    manifest = project_root / MANIFEST_RELATIVE_PATH
    passed, results = AntiDrift(project_root, manifest).verify_drift()
    if passed:
        return []
    if "error" in results:
        return list(AntiDrift.IMMUTABLE_FILES)
    return [path for path, row in results.items() if not row["passed"]]


def write_manifest(project_root: Path) -> dict[str, str]:
    return AntiDrift.generate_manifest(project_root, project_root / MANIFEST_RELATIVE_PATH)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check or regenerate the governance manifest.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="fail when the manifest is stale")
    mode.add_argument("--write", action="store_true", help="regenerate the manifest")
    parser.add_argument(
        "--root", type=Path, default=ROOT, help="project root (default: this checkout)"
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()

    if args.write:
        hashes = write_manifest(root)
        print(json.dumps({"written": str(MANIFEST_RELATIVE_PATH), "files": len(hashes)}))
        return 0

    stale = check_manifest(root)
    print(
        json.dumps({"manifest": str(MANIFEST_RELATIVE_PATH), "in_sync": not stale, "stale": stale})
    )
    if stale:
        print(
            "governance manifest is stale; run: python3 scripts/ops/governance_manifest.py --write",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
