#!/usr/bin/env python3
"""Classify unresolved Wiki links deterministically.

Reads the wikilink-graph.json and agent-index.json to classify every unresolved
link into one of: repo_source, excluded_wiki_target, legacy_or_historical,
placeholder_or_template, exact_alias_match, mechanical_path_error, ambiguous,
missing, unsupported.

CLI:
    --write      write classification artifacts
    --check      verify classification matches existing artifacts
    --repo-root PATH
    --vault-root PATH
    --graph PATH
    --agent-index PATH
    --authority-manifest PATH
    --output-dir PATH
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA = "nexus.wiki.unresolved-link-inventory.v1"
AUTHORITY = "derived_non_authoritative"

CATEGORIES = [
    "repo_source",
    "excluded_wiki_target",
    "legacy_or_historical",
    "placeholder_or_template",
    "exact_alias_match",
    "mechanical_path_error",
    "ambiguous",
    "missing",
    "unsupported",
]

PLACEHOLDER_PATTERNS = {"documentation", "TODO", "TBD", "placeholder", "pending"}

MECHANICAL_TRANSFORMS = [
    ("duplicate_md_suffix", lambda t: t[:-3] if t.endswith(".md.md") else None),
    ("url_decode", lambda t: t.replace("%20", " ") if "%20" in t else None),
    ("duplicate_leading_dot_slash", lambda t: t[2:] if t.startswith("././") else None),
    ("posix_normalize", lambda t: __import__("posixpath").normpath(t)),
]

EXCLUDED_DIRS = {".nexus", ".obsidian", "90_Sources/Archive", "90_Sources/Legacy_Wiki", "99_Schema/generated"}

LEGACY_PREFIXES = ("90_Sources/",)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_path(p: str) -> str:
    """Normalize a vault-relative path."""
    import posixpath
    p = p.replace("\\", "/")
    p = posixpath.normpath(p)
    while p.startswith("./"):
        p = p[2:]
    if p == ".":
        p = ""
    return p


def is_excluded_target(target: str) -> bool:
    """Check if target points to an excluded directory."""
    normalized = normalize_path(target)
    for excluded in EXCLUDED_DIRS:
        if normalized.startswith(excluded):
            return True
    return False


def is_placeholder(target: str) -> bool:
    """Check if target is a known placeholder."""
    return target.strip() in PLACEHOLDER_PATTERNS


def is_repo_source(target: str, repo_root: Path) -> bool:
    """Check if normalized target points outside vault and exists in repo."""
    if target.startswith("..") or target.startswith("/"):
        # Try to resolve as repo-relative path
        repo_path = repo_root / target.lstrip("/").lstrip("..")
        if repo_path.exists():
            return True
    return False


def classify_unresolved(
    entry: dict[str, Any],
    pages_by_rel: dict[str, str],
    pages_by_alias: dict[str, list[str]],
    repo_root: Path,
) -> str:
    """Classify a single unresolved link entry."""
    raw_target = entry.get("raw_target", "")
    syntax = entry.get("syntax", "")
    source_path = entry.get("source_path", "")
    original_reason = entry.get("reason", "")

    # 1. repo_source
    if is_repo_source(raw_target, repo_root):
        return "repo_source"

    # 2. excluded_wiki_target
    if is_excluded_target(raw_target):
        return "excluded_wiki_target"

    # 3. legacy_or_historical - check source classification
    # This is checked externally by looking at source page classification

    # 4. placeholder_or_template
    if is_placeholder(raw_target):
        return "placeholder_or_template"

    # 5. unsupported (malformed syntax)
    if syntax == "unsupported" or raw_target.startswith("Flow - [["):
        return "unsupported"

    # 6. exact_alias_match
    normalized = normalize_path(raw_target)
    cf_target = normalized.lower()
    if cf_target in pages_by_alias:
        candidates = pages_by_alias[cf_target]
        if len(candidates) == 1:
            return "exact_alias_match"

    # 7. mechanical_path_error
    for transform_name, transform_fn in MECHANICAL_TRANSFORMS:
        transformed = transform_fn(normalized)
        if transformed is not None and transformed != normalized:
            if transformed in pages_by_rel or transformed + ".md" in pages_by_rel:
                return "mechanical_path_error"

    # 8. ambiguous (original reason from graph)
    if original_reason == "ambiguous":
        return "ambiguous"

    # 9. missing
    return "missing"


def check_mechanical_transform(
    raw_target: str, pages_by_rel: dict[str, str]
) -> tuple[str, str] | None:
    """Check if a mechanical transform resolves the target. Returns (transform_name, resolved) or None."""
    normalized = normalize_path(raw_target)
    for transform_name, transform_fn in MECHANICAL_TRANSFORMS:
        transformed = transform_fn(normalized)
        if transformed is not None and transformed != normalized:
            if transformed in pages_by_rel:
                return transform_name, transformed
            if transformed + ".md" in pages_by_rel:
                return transform_name, transformed + ".md"
    return None


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


class UnresolvedLinkClassifier:
    def __init__(
        self,
        repo_root: Path,
        vault_root: Path,
        graph_path: Path,
        agent_index_path: Path,
        authority_manifest_path: Path,
    ):
        self.repo_root = repo_root
        self.vault_root = vault_root
        self.graph_path = graph_path
        self.agent_index_path = agent_index_path
        self.authority_manifest_path = authority_manifest_path

        # Load data
        self.graph = self._load_json(graph_path)
        self.agent_index = self._load_json(agent_index_path)
        self.manifest = self._load_yaml(authority_manifest_path)

        # Build indexes
        self.pages_by_rel: dict[str, str] = {}
        self.pages_by_alias: dict[str, list[str]] = {}
        self.pages_by_classification: dict[str, str] = {}
        self._build_indexes()

    def _load_json(self, path: Path) -> dict:
        if not path.exists():
            print(f"ERROR: File not found: {path}", file=sys.stderr)
            sys.exit(1)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_yaml(self, path: Path) -> dict:
        if not path.exists():
            print(f"ERROR: File not found: {path}", file=sys.stderr)
            sys.exit(1)
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _build_indexes(self) -> None:
        """Build indexes from agent-index.json."""
        for page in self.agent_index.get("pages", []):
            rel = page.get("path", "")
            page_id = page.get("id", "")
            self.pages_by_rel[rel] = page_id
            self.pages_by_classification[rel] = page.get("classification", "")

            # Index aliases
            aliases = page.get("aliases", [])
            if isinstance(aliases, list):
                for alias in aliases:
                    cf_alias = alias.lower()
                    self.pages_by_alias.setdefault(cf_alias, []).append(rel)

    def classify_all(self) -> dict[str, Any]:
        """Classify all unresolved links."""
        entries = []
        category_counts: dict[str, int] = {cat: 0 for cat in CATEGORIES}

        # Check if source is legacy
        def is_legacy_source(source_path: str) -> bool:
            classification = self.pages_by_classification.get(source_path, "")
            if classification in ("legacy", "historical", "superseded"):
                return True
            for prefix in LEGACY_PREFIXES:
                if source_path.startswith(prefix):
                    return True
            return False

        for unresolved in self.graph.get("unresolved_links", []):
            category = classify_unresolved(
                unresolved, self.pages_by_rel, self.pages_by_alias, self.repo_root
            )

            # Override: if source is legacy, force legacy_or_historical
            if is_legacy_source(unresolved.get("source_path", "")):
                if category not in ("repo_source", "excluded_wiki_target"):
                    category = "legacy_or_historical"

            entry = {
                "source_id": unresolved.get("source", ""),
                "source_path": unresolved.get("source_path", ""),
                "source_classification": self.pages_by_classification.get(
                    unresolved.get("source_path", ""), ""
                ),
                "raw_target": unresolved.get("raw_target", ""),
                "syntax": unresolved.get("syntax", ""),
                "original_reason": unresolved.get("reason", ""),
                "category": category,
                "evidence": {
                    "candidate_paths": [],
                    "repo_path_exists": False,
                    "exact_alias": "",
                    "mechanical_transform": "",
                },
                "repairable": False,
                "proposed_target": "",
                "batch_id": "",
            }

            # Build evidence
            if category == "repo_source":
                entry["evidence"]["repo_path_exists"] = True
            elif category == "exact_alias_match":
                normalized = normalize_path(unresolved.get("raw_target", ""))
                cf = normalized.lower()
                if cf in self.pages_by_alias:
                    candidates = self.pages_by_alias[cf]
                    if len(candidates) == 1:
                        entry["evidence"]["exact_alias"] = candidates[0]
                        entry["proposed_target"] = self.pages_by_rel.get(
                            candidates[0], ""
                        )
                        entry["repairable"] = True
            elif category == "mechanical_path_error":
                transform = check_mechanical_transform(
                    unresolved.get("raw_target", ""), self.pages_by_rel
                )
                if transform:
                    transform_name, resolved = transform
                    entry["evidence"]["mechanical_transform"] = transform_name
                    entry["proposed_target"] = self.pages_by_rel.get(resolved, "")
                    entry["repairable"] = True

            entries.append(entry)
            category_counts[category] = category_counts.get(category, 0) + 1

        # Build repair batches
        repair_batches = self._build_repair_batches(entries)

        return {
            "schema": SCHEMA,
            "authority": AUTHORITY,
            "source_fingerprint": self.agent_index.get("source_fingerprint", ""),
            "total_unresolved": len(entries),
            "category_counts": category_counts,
            "entries": entries,
            "repair_batches": repair_batches,
        }

    def _build_repair_batches(self, entries: list[dict]) -> list[dict]:
        """Build frozen repair batches from repairable entries."""
        # Filter to repairable entries with allowed categories
        allowed_categories = {"exact_alias_match", "mechanical_path_error"}
        repairable = [
            e
            for e in entries
            if e["repairable"]
            and e["category"] in allowed_categories
            and e["source_classification"] in ("current", "active", "")
            and not e["source_path"].startswith("90_Sources/")
        ]

        # Group by source_path
        by_source: dict[str, list[dict]] = {}
        for entry in repairable:
            source = entry["source_path"]
            by_source.setdefault(source, []).append(entry)

        # Build batches (max 5 source pages, max 20 edits per batch)
        batches = []
        current_batch: list[dict] = []
        current_edit_count = 0
        current_sources: set[str] = set()

        for source, edits in sorted(by_source.items()):
            if len(current_sources) >= 5 or current_edit_count + len(edits) > 20:
                if current_batch:
                    batches.append(
                        {
                            "batch_id": f"batch_{len(batches) + 1}",
                            "source_pages": sorted(current_sources),
                            "edits": current_batch,
                        }
                    )
                current_batch = []
                current_edit_count = 0
                current_sources = set()

            current_batch.extend(edits)
            current_edit_count += len(edits)
            current_sources.add(source)

        if current_batch:
            batches.append(
                {
                    "batch_id": f"batch_{len(batches) + 1}",
                    "source_pages": sorted(current_sources),
                    "edits": current_batch,
                }
            )

        return batches[:3]  # Max 3 batches


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Classify unresolved Wiki links deterministically"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="Write output files")
    group.add_argument("--check", action="store_true", help="Check outputs match")
    parser.add_argument("--repo-root", type=str, default=".", help="Repository root")
    parser.add_argument("--vault-root", type=str, help="Wiki vault root")
    parser.add_argument("--graph", type=str, help="Path to wikilink-graph.json")
    parser.add_argument("--agent-index", type=str, help="Path to agent-index.json")
    parser.add_argument(
        "--authority-manifest", type=str, help="Path to authority manifest"
    )
    parser.add_argument("--output-dir", type=str, help="Output directory")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    vault_root = (
        Path(args.vault_root)
        if args.vault_root
        else repo_root / "nexus_wiki_vault"
    )
    graph_path = (
        Path(args.graph)
        if args.graph
        else vault_root / "99_Schema" / "generated" / "wikilink-graph.json"
    )
    agent_index_path = (
        Path(args.agent_index)
        if args.agent_index
        else vault_root / "99_Schema" / "generated" / "agent-index.json"
    )
    manifest_path = (
        Path(args.authority_manifest)
        if args.authority_manifest
        else vault_root / "99_Schema" / "WIKI_AUTHORITY_MANIFEST.yaml"
    )
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else vault_root / "99_Schema" / "generated"
    )

    classifier = UnresolvedLinkClassifier(
        repo_root, vault_root, graph_path, agent_index_path, manifest_path
    )
    result = classifier.classify_all()

    if args.write:
        output_dir.mkdir(parents=True, exist_ok=True)

        # Write inventory
        inventory_path = output_dir / "unresolved-link-inventory.json"
        with open(inventory_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
            f.write("\n")

        # Write summary
        summary_lines = [
            "# Unresolved Link Classification Summary",
            "",
            f"Total unresolved: {result['total_unresolved']}",
            "",
            "## Category Counts",
            "",
        ]
        for cat, count in sorted(result["category_counts"].items()):
            if count > 0:
                summary_lines.append(f"- {cat}: {count}")
        summary_lines.append("")

        if result["repair_batches"]:
            summary_lines.append("## Repair Batches")
            summary_lines.append("")
            for batch in result["repair_batches"]:
                summary_lines.append(f"### {batch['batch_id']}")
                summary_lines.append(
                    f"- Source pages: {len(batch['source_pages'])}"
                )
                summary_lines.append(f"- Edits: {len(batch['edits'])}")
                summary_lines.append("")

        summary_path = output_dir / "unresolved-link-summary.md"
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("\n".join(summary_lines))

        print(
            f"OK: wrote inventory ({result['total_unresolved']} entries) to {output_dir}"
        )

    elif args.check:
        # Verify matches
        inventory_path = output_dir / "unresolved-link-inventory.json"
        if not inventory_path.exists():
            print("DRIFT: inventory not found")
            sys.exit(1)

        existing = json.loads(inventory_path.read_text(encoding="utf-8"))
        required_fields = (
            "schema",
            "authority",
            "source_fingerprint",
            "total_unresolved",
            "category_counts",
            "entries",
            "repair_batches",
        )
        for field in required_fields:
            if field not in existing:
                print(f"DRIFT: missing field {field}")
                sys.exit(1)
            if existing[field] != result[field]:
                print(f"DRIFT: {field} mismatch")
                sys.exit(1)

        print("CHECK PASSED: classification matches")


if __name__ == "__main__":
    main()
