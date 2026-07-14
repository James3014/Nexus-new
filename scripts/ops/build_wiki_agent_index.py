#!/usr/bin/env python3
"""Deterministic wiki agent retrieval index compiler.

Reads WIKI_AUTHORITY_MANIFEST.yaml and wiki markdown files to produce:
- agent-index.json
- llms.txt
- wikilink-graph.json

CLI:
    --write   atomically write all three outputs
    --check   compare expected outputs against existing files, exit 0 if match, 1 if drift
    --vault-root PATH
    --authority-manifest PATH
    --output-dir PATH
"""
from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import sys
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_INDEX = "nexus.wiki.agent-index.v1"
SCHEMA_GRAPH = "nexus.wiki.wikilink-graph.v1"
AUTHORITY = "derived_non_authoritative"
MANIFEST_REL = "99_Schema/WIKI_AUTHORITY_MANIFEST.yaml"

EXCLUDE_DIRS = {
    ".nexus",
    ".obsidian",
}
EXCLUDE_PATH_PREFIXES = [
    "90_Sources/Archive/",
    "90_Sources/Legacy_Wiki/",
    "99_Schema/generated/",
]

LIFECYCLE_TO_CLASSIFICATION: dict[str, str] = {
    "current": "current",
    "active": "active",
    "superseded": "superseded",
    "historical": "historical",
    "draft": "draft",
    "mixed_needs_review": "mixed_needs_review",
    "archive": "archive",
}

STATUS_TO_CLASSIFICATION: dict[str, str] = {
    "current": "current",
    "active": "active",
    "superseded": "superseded",
    "historical": "historical",
    "draft": "draft",
    "mixed_needs_review": "mixed_needs_review",
    "archive": "archive",
}

SUMMARY_SECTION_RE = re.compile(
    r"^## One-sentence summary\s*$", re.MULTILINE | re.IGNORECASE
)
H1_RE = re.compile(r"^#\s+.+$", re.MULTILINE)
WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# Frontmatter verification keys to preserve
VERIFICATION_KEYS = [
    "content_verified_against_commit",
    "document_updated_in_commit",
    "verified_at",
    "last_verified",
    "last_audit",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_path(p: str) -> str:
    """Normalize a vault-relative path using POSIX lexical normalization.

    Folds '..', '.', double slashes, and strips leading './'.
    Returns empty string if path escapes vault root.
    """
    p = p.replace("\\", "/")
    p = posixpath.normpath(p)
    # Remove leading ./ or ../
    while p.startswith("./"):
        p = p[2:]
    if p == ".":
        p = ""
    return p


def resolve_relative_path(source_dir: str, target: str) -> str:
    """Resolve a relative link target against source directory, returning
    vault-relative normalized path. Returns empty string if escapes vault."""
    # Strip fragment
    target_no_frag = target.split("#")[0]
    # Strip optional .md extension for matching
    # But keep it for path resolution

    if source_dir == "" or source_dir == ".":
        base = ""
    else:
        base = source_dir

    if base:
        resolved = posixpath.normpath(posixpath.join(base, target_no_frag))
    else:
        resolved = posixpath.normpath(target_no_frag)

    # Normalize
    resolved = resolved.replace("\\", "/")

    # Check vault escape
    if resolved.startswith("..") or resolved.startswith("/"):
        return ""

    # Remove leading ./
    while resolved.startswith("./"):
        resolved = resolved[2:]

    return resolved


def is_excluded(rel_path: str) -> bool:
    parts = Path(rel_path).parts
    for d in EXCLUDE_DIRS:
        if d in parts:
            return True
    for prefix in EXCLUDE_PATH_PREFIXES:
        if rel_path.startswith(prefix):
            return True
    return False


def parse_frontmatter(content: str) -> dict:
    m = FRONTMATTER_RE.match(content)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}


def extract_verification_metadata(fm: dict) -> dict[str, str]:
    """Extract verification metadata from frontmatter. Returns dict with
    only keys that exist in frontmatter."""
    result: dict[str, str] = {}
    for key in VERIFICATION_KEYS:
        val = fm.get(key, "")
        if val:
            result[key] = str(val)
    return result


def extract_one_sentence_summary(content: str) -> str:
    """Extract the first meaningful paragraph after '## One-sentence summary'."""
    m = SUMMARY_SECTION_RE.search(content)
    if m:
        rest = content[m.end():]
        # Find first non-empty, non-header line
        for line in rest.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("## ") or stripped.startswith("---"):
                break
            # Skip bullet markers for cleaner extraction
            clean = re.sub(r"^[-*]\s*", "", stripped)
            if clean:
                return clean
        return ""

    # Fallback: paragraph after H1
    h1_match = H1_RE.search(content)
    if h1_match:
        rest = content[h1_match.end():]
        for line in rest.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                break
            return stripped
    return ""


def strip_wikilink(raw: str) -> tuple[str, str]:
    """Strip alias and anchor from wikilink. Returns (stem, alias)."""
    # Remove alias
    stem = raw.split("|")[0].strip()
    # Remove anchor
    anchor = ""
    if "#" in stem:
        stem, anchor = stem.split("#", 1)
    return stem, anchor


def resolve_wikilink_target(
    stem: str,
    pages_by_rel: dict[str, str],
    pages_by_stem: dict[str, list[str]],
    pages_by_casefold: dict[str, list[str]],
) -> str | None:
    """Resolve a wikilink stem to a page ID or None.

    Resolution order:
    1. Exact vault-relative path match (with or without .md)
    2. Case-folded vault-relative path match
    3. Unique stem match
    4. Unique case-folded stem match
    """
    # 1. Exact path match
    if stem in pages_by_rel:
        return pages_by_rel[stem]
    # With .md
    if stem + ".md" in pages_by_rel:
        return pages_by_rel[stem + ".md"]

    # 2. Case-folded path match
    cf = stem.lower()
    if cf in pages_by_casefold:
        candidates = pages_by_casefold[cf]
        if len(candidates) == 1:
            return f"page:{candidates[0]}"
        return None  # ambiguous

    # 3. Unique stem match (normalized)
    norm_stem = stem.lower().replace(" ", "_")
    candidates = pages_by_stem.get(norm_stem, [])
    if len(candidates) == 1:
        return f"page:{candidates[0]}"
    if len(candidates) > 1:
        return None  # ambiguous

    # 4. Case-folded stem
    cf_stem = stem.lower().replace(" ", "_")
    cf_candidates = pages_by_stem.get(cf_stem, [])
    if len(cf_candidates) == 1:
        return f"page:{cf_candidates[0]}"

    return None


# ---------------------------------------------------------------------------
# Core compiler
# ---------------------------------------------------------------------------

class WikiIndexCompiler:
    def __init__(
        self,
        vault_root: Path,
        authority_manifest: Path,
        output_dir: Path,
    ):
        self.vault_root = vault_root
        self.authority_manifest = authority_manifest
        self.output_dir = output_dir

        # Load manifest
        self.manifest = self._load_manifest()
        self.canonical = self.manifest.get("canonical", {})
        self.known_legacy = self.manifest.get("known_legacy_entries", [])

        # Scan
        self.all_md: list[Path] = []
        self.included: list[Path] = []
        self.excluded_count = 0
        self._scan()

        # Indexes
        self.pages_by_rel: dict[str, str] = {}  # rel_path -> page_id
        self.pages_by_stem: dict[str, list[str]] = {}  # normalized_stem -> [rel_paths]
        self.pages_by_casefold: dict[str, list[str]] = {}  # lower(path) -> [rel_paths]
        self.rel_to_final_id: dict[str, str] = {}  # rel_path -> final page_id

    def _load_manifest(self) -> dict:
        if not self.authority_manifest.exists():
            print(f"ERROR: Authority manifest not found: {self.authority_manifest}", file=sys.stderr)
            sys.exit(1)
        try:
            with open(self.authority_manifest, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(f"ERROR: Invalid YAML in authority manifest: {e}", file=sys.stderr)
            sys.exit(1)
        if not isinstance(data, dict):
            print("ERROR: Authority manifest is not a mapping", file=sys.stderr)
            sys.exit(1)
        if "canonical" not in data or not isinstance(data["canonical"], dict):
            print("ERROR: Authority manifest missing 'canonical' section", file=sys.stderr)
            sys.exit(1)
        return data

    def _scan(self) -> None:
        self.all_md = sorted(self.vault_root.rglob("*.md"))
        for p in self.all_md:
            rel = normalize_path(str(p.relative_to(self.vault_root)))
            if is_excluded(rel):
                self.excluded_count += 1
                continue
            self.included.append(p)

    def _check_canonical_paths(self) -> None:
        """Fail closed if any canonical path is missing or duplicated."""
        seen_paths: dict[str, str] = {}
        for key, entry in self.canonical.items():
            path = entry.get("path", "")
            if not path:
                print(f"ERROR: Canonical key '{key}' has empty path", file=sys.stderr)
                sys.exit(1)
            full = self.vault_root / path
            if not full.exists():
                print(f"ERROR: Canonical path missing: {path} (key={key})", file=sys.stderr)
                sys.exit(1)
            norm = normalize_path(path)
            if norm in seen_paths:
                print(
                    f"ERROR: Duplicate canonical path '{norm}' in keys "
                    f"'{seen_paths[norm]}' and '{key}'",
                    file=sys.stderr,
                )
                sys.exit(1)
            seen_paths[norm] = key

    def _classify_page(
        self, rel_path: str, fm: dict
    ) -> tuple[str, str, str]:
        """Return (classification, lifecycle, status)."""
        # 1. known_legacy_entries
        for entry in self.known_legacy:
            if normalize_path(entry.get("path", "")) == rel_path:
                return (
                    entry.get("classification", "unclassified"),
                    entry.get("lifecycle", "unclassified"),
                    fm.get("status", "unclassified"),
                )

        lifecycle = fm.get("lifecycle", "unclassified")
        status = fm.get("status", "unclassified")

        # 2. lifecycle
        if lifecycle in LIFECYCLE_TO_CLASSIFICATION:
            classification = LIFECYCLE_TO_CLASSIFICATION[lifecycle]
        # 3. status
        elif status in STATUS_TO_CLASSIFICATION:
            classification = STATUS_TO_CLASSIFICATION[status]
        else:
            classification = "unclassified"

        return classification, lifecycle, status

    def _build_page(
        self, path: Path, canonical_map: dict[str, dict]
    ) -> dict:
        rel = normalize_path(str(path.relative_to(self.vault_root)))
        content = path.read_text(encoding="utf-8")
        content_hash = sha256_bytes(content.encode("utf-8"))
        fm = parse_frontmatter(content)

        classification, lifecycle, status = self._classify_page(rel, fm)
        one_sentence = extract_one_sentence_summary(content)
        verification = extract_verification_metadata(fm)

        # Canonical check
        is_canonical = rel in canonical_map
        canonical_key = canonical_map[rel]["key"] if is_canonical else ""
        authority_val = canonical_map[rel]["authority"] if is_canonical else ""

        # Build page ID: canonical pages use canonical:<key>, others use page:<path>
        if is_canonical:
            page_id = f"canonical:{canonical_key}"
        else:
            page_id = f"page:{rel}"

        # Store mapping
        self.rel_to_final_id[rel] = page_id

        # Outgoing links
        outgoing, unresolved = self._extract_links(content, rel)

        result: dict[str, Any] = {
            "id": page_id,
            "path": rel,
            "title": fm.get("title", path.stem),
            "type": fm.get("type", "unclassified"),
            "status": status,
            "lifecycle": lifecycle,
            "classification": classification,
            "authority": authority_val if is_canonical else fm.get("authority", ""),
            "owner": fm.get("owner", ""),
            "confidence": fm.get("confidence", ""),
            "source_of_truth": fm.get("source_of_truth", ""),
            "aliases": fm.get("aliases", []) if isinstance(fm.get("aliases"), list) else [],
            "tags": fm.get("tags", []) if isinstance(fm.get("tags"), list) else [],
            "is_canonical": is_canonical,
            "canonical_key": canonical_key,
            "one_sentence_summary": one_sentence,
            "content_sha256": content_hash,
            "outgoing_links": outgoing,
            "unresolved_links": unresolved,
        }

        # Add verification metadata
        for key in VERIFICATION_KEYS:
            result[key] = verification.get(key, "")

        return result

    def _extract_links(
        self, content: str, source_rel: str
    ) -> tuple[list[tuple[str, str]], list[dict]]:
        outgoing: list[tuple[str, str]] = []  # (target_id, syntax)
        unresolved: list[dict] = []

        source_dir = str(Path(source_rel).parent)
        if source_dir == ".":
            source_dir = ""

        # Skip code blocks
        no_code = re.sub(r"```.*?```", "", content, flags=re.DOTALL)

        # Wikilinks
        for m in WIKILINK_RE.finditer(no_code):
            raw_link = m.group(1).strip()
            stem, anchor = strip_wikilink(raw_link)

            target_id = resolve_wikilink_target(
                stem, self.pages_by_rel, self.pages_by_stem, self.pages_by_casefold
            )
            if target_id:
                outgoing.append((target_id, "wikilink"))
            else:
                # Determine reason: ambiguous vs missing vs outside_vault
                reason = "missing"
                resolved = resolve_relative_path(source_dir, stem)
                if resolved == "" and stem.startswith(".."):
                    reason = "outside_vault"
                else:
                    # Check if stem matches multiple pages (ambiguous)
                    norm_stem = stem.lower().replace(" ", "_")
                    stem_candidates = self.pages_by_stem.get(norm_stem, [])
                    if len(stem_candidates) > 1:
                        reason = "ambiguous"
                unresolved.append({
                    "source": f"page:{source_rel}",
                    "source_path": source_rel,
                    "raw_target": raw_link,
                    "syntax": "wikilink",
                    "reason": reason,
                })

        # Markdown links (relative only, skip external)
        for m in MARKDOWN_LINK_RE.finditer(no_code):
            target = m.group(2).strip()
            if any(target.startswith(s) for s in ("http://", "https://", "mailto:")):
                continue
            if target.startswith("#"):
                continue
            # Skip image links
            if m.group(1) == "" and any(
                target.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")
            ):
                continue

            # Strip fragment
            target_no_frag = target.split("#")[0]
            if not target_no_frag:
                continue

            # Resolve relative path
            resolved = resolve_relative_path(source_dir, target)

            if resolved == "":
                # Escapes vault
                unresolved.append({
                    "source": f"page:{source_rel}",
                    "source_path": source_rel,
                    "raw_target": target,
                    "syntax": "markdown",
                    "reason": "outside_vault",
                })
                continue

            # Try exact match
            if resolved in self.pages_by_rel:
                outgoing.append((self.pages_by_rel[resolved], "markdown"))
                continue
            # With .md extension
            if resolved + ".md" in self.pages_by_rel:
                outgoing.append((self.pages_by_rel[resolved + ".md"], "markdown"))
                continue

            unresolved.append({
                "source": f"page:{source_rel}",
                "source_path": source_rel,
                "raw_target": target,
                "syntax": "markdown",
                "reason": "missing",
            })

        return outgoing, unresolved

    def _build_graph(self, pages: list[dict]) -> tuple[dict, list[dict]]:
        """Build graph and collect all unresolved links."""
        nodes = []
        for p in pages:
            nodes.append(
                {
                    "id": p["id"],
                    "path": p["path"],
                    "title": p["title"],
                    "classification": p["classification"],
                    "is_canonical": p["is_canonical"],
                    "authority": p["authority"],
                }
            )

        edges: list[dict] = []
        all_unresolved: list[dict] = []
        seen_edges: set[tuple[str, str, str]] = set()
        for p in pages:
            for target_id, syntax in p["outgoing_links"]:
                key = (p["id"], target_id, syntax)
                if key not in seen_edges:
                    edges.append(
                        {
                            "source": p["id"],
                            "target": target_id,
                            "type": "explicit_link",
                            "syntax": syntax,
                        }
                    )
                    seen_edges.add(key)
            # Collect unresolved links
            for u in p["unresolved_links"]:
                all_unresolved.append(u)

        # Validate no dangling edges
        node_ids = {n["id"] for n in nodes}
        for e in edges:
            assert e["source"] in node_ids, f"Dangling source: {e['source']}"
            assert e["target"] in node_ids, f"Dangling target: {e['target']}"

        graph = {
            "schema": SCHEMA_GRAPH,
            "authority": AUTHORITY,
            "source_fingerprint": "",
            "nodes": nodes,
            "edges": edges,
            "unresolved_links": all_unresolved,
        }
        return graph, all_unresolved

    def _build_llms_txt(
        self, pages: list[dict], canonical_ordered: list[dict]
    ) -> str:
        lines = [
            "# Nexus Wiki Agent Retrieval Entry",
            "Authority source:",
            f"- {MANIFEST_REL}",
            "Rules:",
            "- Generated files are derived and non-authoritative.",
            "- Current truth must be verified against canonical pages and repository evidence.",
            "- Version numbers and words such as FINAL or SEALED do not establish authority.",
            "- Do not perform full-corpus reading when targeted retrieval is sufficient.",
            "",
            "## Canonical Pages",
            "",
        ]

        for p in canonical_ordered:
            lines.append(f"- canonical_key: {p['canonical_key']}")
            lines.append(f"  title: {p['title']}")
            lines.append(f"  path: {p['path']}")
            lines.append(f"  authority: {p['authority']}")
            lines.append(f"  classification: {p['classification']}")
            if p["one_sentence_summary"]:
                lines.append(f"  summary: {p['one_sentence_summary']}")
            lines.append("")

        lines.append("## Generated Artifacts")
        lines.append("- 99_Schema/generated/agent-index.json")
        lines.append("- 99_Schema/generated/llms.txt")
        lines.append("- 99_Schema/generated/wikilink-graph.json")
        lines.append("")
        lines.append("## Warning")
        lines.append(
            "Generated artifacts are derived and non-authoritative. "
            "They do not establish architectural truth."
        )
        lines.append("")
        return "\n".join(lines)

    def _compute_fingerprint(self, pages: list[dict]) -> str:
        """Compute source fingerprint from manifest + all included markdown content."""
        parts: list[bytes] = []

        # Manifest bytes
        if self.authority_manifest.exists():
            parts.append(self.authority_manifest.read_bytes())

        # Sorted relative paths + content bytes
        for p in sorted(self.included):
            rel = normalize_path(str(p.relative_to(self.vault_root)))
            parts.append(rel.encode("utf-8"))
            parts.append(p.read_bytes())

        combined = b"\x00".join(parts)
        return sha256_bytes(combined)

    def build(self) -> tuple[dict, dict, str]:
        self._check_canonical_paths()

        # Build canonical map: rel_path -> {key, authority}
        canonical_map: dict[str, dict] = {}
        for key, entry in self.canonical.items():
            rel = normalize_path(entry["path"])
            canonical_map[rel] = {"key": key, "authority": entry.get("authority", "")}

        # Build page indexes for link resolution
        for p in self.included:
            rel = normalize_path(str(p.relative_to(self.vault_root)))
            stem = p.stem.lower().replace(" ", "_")
            self.pages_by_rel[rel] = f"page:{rel}"
            self.pages_by_stem.setdefault(stem, []).append(rel)
            # Case-folded index for exact case matching
            cf = rel.lower()
            self.pages_by_casefold.setdefault(cf, []).append(rel)

        # Build all pages
        pages: list[dict] = []
        for p in self.included:
            rel = normalize_path(str(p.relative_to(self.vault_root)))
            page = self._build_page(p, canonical_map)
            pages.append(page)

        # Fix canonical page IDs in outgoing links
        # If a link target was resolved as page:<path> but the target is canonical,
        # update to canonical:<key>
        canonical_rel_to_id = {
            rel: f"canonical:{canonical_map[rel]['key']}"
            for rel in canonical_map
        }
        for page in pages:
            new_outgoing = []
            for target_id, syntax in page["outgoing_links"]:
                # Check if target_id is page:<canonical_path>
                if target_id.startswith("page:"):
                    target_path = target_id[5:]
                    if target_path in canonical_rel_to_id:
                        target_id = canonical_rel_to_id[target_path]
                new_outgoing.append((target_id, syntax))
            page["outgoing_links"] = new_outgoing

        # Sort pages: canonical by manifest order, non-canonical by path
        canonical_order = {key: i for i, key in enumerate(self.canonical.keys())}
        pages.sort(
            key=lambda x: (
                0 if x["is_canonical"] else 1,
                canonical_order.get(x["canonical_key"], 999) if x["is_canonical"] else 0,
                x["path"] if not x["is_canonical"] else "",
            )
        )

        # Build graph
        graph, all_unresolved = self._build_graph(pages)

        # Compute fingerprint
        fingerprint = self._compute_fingerprint(pages)

        # Inject fingerprint into graph
        graph["source_fingerprint"] = fingerprint

        # Build agent index
        agent_index = {
            "schema": SCHEMA_INDEX,
            "authority": AUTHORITY,
            "authority_manifest": MANIFEST_REL,
            "source_fingerprint": fingerprint,
            "included_page_count": len(pages),
            "excluded_page_count": self.excluded_count,
            "canonical_page_count": sum(1 for p in pages if p["is_canonical"]),
            "unresolved_link_count": sum(len(p["unresolved_links"]) for p in pages),
            "exclusion_rules": [
                f"Dir: {d}" for d in sorted(EXCLUDE_DIRS)
            ] + [f"Prefix: {p}" for p in sorted(EXCLUDE_PATH_PREFIXES)],
            "pages": pages,
        }

        # Build canonical-ordered list for llms.txt
        canonical_ordered = [p for p in pages if p["is_canonical"]]
        # Preserve manifest order
        key_order = list(self.canonical.keys())
        canonical_ordered.sort(
            key=lambda p: key_order.index(p["canonical_key"])
            if p["canonical_key"] in key_order
            else 999
        )

        llms_txt = self._build_llms_txt(pages, canonical_ordered)

        return agent_index, graph, llms_txt

    def write(self) -> None:
        agent_index, graph, llms_txt = self.build()

        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Write atomically
        def _write(name: str, content: str | dict) -> None:
            path = self.output_dir / name
            tmp = path.with_suffix(".tmp")
            if isinstance(content, dict):
                tmp.write_text(
                    json.dumps(content, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
                    encoding="utf-8",
                )
            else:
                tmp.write_text(content, encoding="utf-8")
            tmp.replace(path)

        _write("agent-index.json", agent_index)
        _write("llms.txt", llms_txt)
        _write("wikilink-graph.json", graph)

        print(f"OK: wrote 3 files to {self.output_dir}")

    def check(self) -> None:
        agent_index, graph, llms_txt = self.build()

        self.output_dir.mkdir(parents=True, exist_ok=True)

        files = {
            "agent-index.json": json.dumps(
                agent_index, indent=2, ensure_ascii=False, sort_keys=False
            )
            + "\n",
            "llms.txt": llms_txt,
            "wikilink-graph.json": json.dumps(
                graph, indent=2, ensure_ascii=False, sort_keys=False
            )
            + "\n",
        }

        drift = False
        for name, expected in files.items():
            path = self.output_dir / name
            if not path.exists():
                print(f"DRIFT: missing {name}")
                drift = True
                continue
            actual = path.read_text(encoding="utf-8")
            if actual != expected:
                print(f"DRIFT: {name} content mismatch")
                drift = True

        if drift:
            print("CHECK FAILED: drift detected")
            sys.exit(1)
        else:
            print("CHECK PASSED: all outputs match")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deterministic wiki agent retrieval index compiler"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="Write output files")
    group.add_argument("--check", action="store_true", help="Check outputs match expected")
    parser.add_argument("--vault-root", type=str, help="Path to wiki vault root")
    parser.add_argument("--authority-manifest", type=str, help="Path to authority manifest")
    parser.add_argument("--output-dir", type=str, help="Path to output directory")
    args = parser.parse_args()

    # Defaults based on repo layout
    repo_root = Path(__file__).resolve().parents[2]
    vault_root = Path(args.vault_root) if args.vault_root else repo_root / "nexus_wiki_vault"
    manifest = Path(args.authority_manifest) if args.authority_manifest else vault_root / MANIFEST_REL
    output_dir = Path(args.output_dir) if args.output_dir else vault_root / "99_Schema" / "generated"

    compiler = WikiIndexCompiler(vault_root, manifest, output_dir)

    if args.write:
        compiler.write()
    elif args.check:
        compiler.check()


if __name__ == "__main__":
    main()
