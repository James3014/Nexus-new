#!/usr/bin/env python3
"""Check that Wiki retrieval artifacts are reproducible from committed HEAD sources.

Reads the committed compiler, manifest, and wiki sources from a Git ref,
rebuilds the three generated artifacts in a temporary directory, and compares
them byte-for-byte against the committed artifacts.

CLI:
    --check     compare expected outputs against existing files, exit 0 if match, 1 if drift
    --repo-root PATH
    --ref REF       Git ref to check (default: HEAD)
    --json          output results as JSON
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA = "nexus.wiki.committed-reproducibility.v1"
ARTIFACT_NAMES = ["agent-index.json", "llms.txt", "wikilink-graph.json"]
GENERATED_DIR = "nexus_wiki_vault/99_Schema/generated"
MANIFEST_PATH = "nexus_wiki_vault/99_Schema/WIKI_AUTHORITY_MANIFEST.yaml"
COMPILER_PATH = "scripts/ops/build_wiki_agent_index.py"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_show(repo_root: Path, ref: str, path: str) -> bytes | None:
    """Read a file's content at a specific Git ref."""
    try:
        result = subprocess.run(
            ["git", "show", f"{ref}:{path}"],
            cwd=repo_root,
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        return result.stdout
    except Exception:
        return None


def git_rev_parse(repo_root: Path, ref: str) -> str | None:
    """Resolve a Git ref to a full commit SHA."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", ref],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()
    except Exception:
        return None


def list_wiki_files_at_ref(repo_root: Path, ref: str) -> list[str]:
    """List all .md files in the wiki vault at a specific Git ref."""
    try:
        result = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", ref, "nexus_wiki_vault/"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return []
        return [f for f in result.stdout.strip().splitlines() if f.endswith(".md")]
    except Exception:
        return []


def rebuild_artifacts(
    repo_root: Path, ref: str, tmp_dir: Path
) -> dict[str, bytes] | None:
    """Rebuild generated artifacts in a temporary directory using committed sources."""
    # Write committed compiler
    compiler_content = git_show(repo_root, ref, COMPILER_PATH)
    if compiler_content is None:
        return None
    compiler_path = tmp_dir / "build_wiki_agent_index.py"
    compiler_path.write_bytes(compiler_content)

    # Write committed manifest
    manifest_content = git_show(repo_root, ref, MANIFEST_PATH)
    if manifest_content is None:
        return None
    manifest_dir = tmp_dir / "nexus_wiki_vault" / "99_Schema"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "WIKI_AUTHORITY_MANIFEST.yaml").write_bytes(manifest_content)

    # Write committed wiki sources
    wiki_files = list_wiki_files_at_ref(repo_root, ref)
    for wiki_file in wiki_files:
        content = git_show(repo_root, ref, wiki_file)
        if content is None:
            return None
        dest = tmp_dir / wiki_file
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)

    # Create output directory
    output_dir = tmp_dir / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Run the compiler
    vault_root = tmp_dir / "nexus_wiki_vault"
    manifest_path = vault_root / "99_Schema" / "WIKI_AUTHORITY_MANIFEST.yaml"
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(compiler_path),
                "--write",
                "--vault-root", str(vault_root),
                "--authority-manifest", str(manifest_path),
                "--output-dir", str(output_dir),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            return None
    except Exception:
        return None

    # Read generated artifacts
    artifacts: dict[str, bytes] = {}
    for name in ARTIFACT_NAMES:
        path = output_dir / name
        if not path.exists():
            return None
        artifacts[name] = path.read_bytes()

    return artifacts


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check Wiki retrieval artifact committed-tree reproducibility"
    )
    parser.add_argument(
        "--check", action="store_true", help="Check reproducibility"
    )
    parser.add_argument(
        "--repo-root", type=str, default=".", help="Repository root path"
    )
    parser.add_argument(
        "--ref", type=str, default="HEAD", help="Git ref to check"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output results as JSON"
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()

    # Resolve ref
    resolved_ref = git_rev_parse(repo_root, args.ref)
    if resolved_ref is None:
        result = {
            "schema": SCHEMA,
            "ref": args.ref,
            "status": "invalid",
            "artifacts": {},
        }
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"ERROR: Invalid Git ref: {args.ref}", file=sys.stderr)
        sys.exit(2)

    # Read committed artifacts
    committed_artifacts: dict[str, dict] = {}
    for name in ARTIFACT_NAMES:
        path = f"{GENERATED_DIR}/{name}"
        content = git_show(repo_root, args.ref, path)
        if content is None:
            committed_artifacts[name] = {
                "expected_sha256": "",
                "tracked_sha256": "",
                "match": False,
            }
        else:
            tracked_sha = sha256_bytes(content)
            committed_artifacts[name] = {
                "expected_sha256": "",
                "tracked_sha256": tracked_sha,
                "match": False,
            }

    # Rebuild from committed sources
    with tempfile.TemporaryDirectory(prefix="wiki-repro-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        rebuilt = rebuild_artifacts(repo_root, args.ref, tmp_path)

    if rebuilt is None:
        for name in ARTIFACT_NAMES:
            committed_artifacts[name]["match"] = False
        result = {
            "schema": SCHEMA,
            "ref": resolved_ref,
            "status": "invalid",
            "artifacts": committed_artifacts,
        }
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print("ERROR: Failed to rebuild artifacts from committed sources", file=sys.stderr)
        sys.exit(2)

    # Compare
    all_match = True
    for name in ARTIFACT_NAMES:
        rebuilt_sha = sha256_bytes(rebuilt[name])
        committed_artifacts[name]["expected_sha256"] = rebuilt_sha
        match = committed_artifacts[name]["tracked_sha256"] == rebuilt_sha
        committed_artifacts[name]["match"] = match
        if not match:
            all_match = False

    status = "match" if all_match else "drift"
    result = {
        "schema": SCHEMA,
        "ref": resolved_ref,
        "status": status,
        "artifacts": committed_artifacts,
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if all_match:
            print("CHECK PASSED: all committed artifacts reproducible from committed sources")
        else:
            print("CHECK FAILED: artifact drift detected")
            for name, info in committed_artifacts.items():
                if not info["match"]:
                    print(f"  DRIFT: {name}")
                    print(f"    expected: {info['expected_sha256']}")
                    print(f"    tracked:  {info['tracked_sha256']}")

    sys.exit(0 if all_match else 1)


if __name__ == "__main__":
    main()
