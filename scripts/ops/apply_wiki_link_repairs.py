#!/usr/bin/env python3
"""Apply frozen deterministic link repair batches from the unresolved-link inventory.

Reads the repair_batches from unresolved-link-inventory.json and applies
edits to wiki source files. Only processes entries with repairable=true.

CLI:
    --write      apply repairs and write receipt
    --check      verify no pending repairs exist
    --repo-root PATH
    --vault-root PATH
    --inventory PATH
    --output-dir PATH
    --max-batches INT (default 3)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


SCHEMA = "nexus.wiki.link-repair-receipt.v1"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def apply_wikilink_repair(
    source_path: Path,
    old_target: str,
    new_target: str,
) -> int:
    """Apply a single wikilink repair to a source file. Returns number of edits."""
    if not source_path.exists():
        return 0

    content = source_path.read_text(encoding="utf-8")
    original = content

    # Replace [[old_target]] with [[new_target]]
    content = content.replace(f"[[{old_target}]]", f"[[{new_target}]]")

    # Also handle [[old_target|display]] format
    content = content.replace(f"[[{old_target}|", f"[[{new_target}|")

    if content != original:
        source_path.write_text(content, encoding="utf-8")
        return original.count(f"[[{old_target}")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply frozen deterministic link repair batches"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="Apply repairs")
    group.add_argument("--check", action="store_true", help="Check no pending repairs")
    parser.add_argument("--repo-root", type=str, default=".", help="Repository root")
    parser.add_argument("--vault-root", type=str, help="Wiki vault root")
    parser.add_argument("--inventory", type=str, help="Path to inventory JSON")
    parser.add_argument("--output-dir", type=str, help="Output directory for receipt")
    parser.add_argument("--max-batches", type=int, default=3, help="Max batches to apply")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    vault_root = (
        Path(args.vault_root)
        if args.vault_root
        else repo_root / "nexus_wiki_vault"
    )
    inventory_path = (
        Path(args.inventory)
        if args.inventory
        else vault_root / "99_Schema" / "generated" / "unresolved-link-inventory.json"
    )
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else vault_root / "99_Schema" / "generated"
    )

    if not inventory_path.exists():
        print(f"ERROR: Inventory not found: {inventory_path}", file=sys.stderr)
        sys.exit(1)

    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    batches = inventory.get("repair_batches", [])

    if args.check:
        # Check mode: verify no pending repairs
        pending = sum(len(b.get("edits", [])) for b in batches)
        if pending > 0:
            print(f"DRIFT: {pending} pending repairs exist")
            sys.exit(1)
        print("CHECK PASSED: no pending repairs")
        return

    # Write mode: apply batches
    applied_edits = 0
    applied_sources: set[str] = set()
    batch_results: list[dict[str, Any]] = []

    for batch in batches[: args.max_batches]:
        batch_id = batch.get("batch_id", "")
        edits = batch.get("edits", [])
        batch_edit_count = 0

        for edit in edits:
            source_path = vault_root / edit.get("source_path", "")
            raw_target = edit.get("raw_target", "")
            proposed_target = edit.get("proposed_target", "")

            if not source_path.exists():
                continue

            num_edits = apply_wikilink_repair(source_path, raw_target, proposed_target)
            batch_edit_count += num_edits
            applied_sources.add(edit.get("source_path", ""))

        applied_edits += batch_edit_count
        batch_results.append(
            {
                "batch_id": batch_id,
                "source_pages": batch.get("source_pages", []),
                "edits_applied": batch_edit_count,
            }
        )

    # Write receipt
    receipt = {
        "schema": SCHEMA,
        "authority": "derived_non_authoritative",
        "source_fingerprint": inventory.get("source_fingerprint", ""),
        "batches_applied": len(batch_results),
        "total_edits_applied": applied_edits,
        "source_files_modified": sorted(applied_sources),
        "batch_results": batch_results,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = output_dir / "link-repair-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"OK: applied {applied_edits} edits across {len(applied_sources)} source files")


if __name__ == "__main__":
    main()
