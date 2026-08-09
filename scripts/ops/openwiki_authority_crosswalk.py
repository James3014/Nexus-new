#!/usr/bin/env python3
"""Compile OpenWiki source metadata into a deterministic governed-Wiki crosswalk.

The compiler never infers authority. Destinations come only from exact path or
path-prefix rules declared by WIKI_AUTHORITY_MANIFEST.yaml.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OPENWIKI_ROOT = REPO_ROOT / "openwiki"
DEFAULT_MANIFEST = REPO_ROOT / "nexus_wiki_vault/99_Schema/WIKI_AUTHORITY_MANIFEST.yaml"
SCHEMA = "nexus.openwiki_wiki_crosswalk.v1"
AUTHORITY = "derived_non_authoritative"
MANIFEST_SCHEMA = "nexus.wiki.authority.v1"


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: _UniqueKeySafeLoader,
    node: yaml.nodes.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalise_path(value: str) -> str:
    path = str(value or "").strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    if not path or path.startswith("/") or ".." in Path(path).parts:
        raise ValueError(f"invalid repository-relative path: {value!r}")
    return path


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        value = (
            yaml.load(
                path.read_text(encoding="utf-8"),
                Loader=_UniqueKeySafeLoader,
            )
            or {}
        )
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"unable to load YAML mapping {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return value


def _frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    marker = text.find("\n---\n", 4)
    if marker < 0:
        raise ValueError(f"unterminated frontmatter: {path}")
    try:
        value = yaml.load(text[4:marker], Loader=_UniqueKeySafeLoader) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid frontmatter {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"frontmatter root must be a mapping: {path}")
    return value


def load_mapping_rules(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    raw_rules = manifest.get("code_symbol_mapping_rules")
    if not isinstance(raw_rules, list):
        raise ValueError("manifest code_symbol_mapping_rules must be a list")

    rules: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_rules):
        if not isinstance(raw, dict):
            raise ValueError(f"mapping rule {index} must be a mapping")
        identity_fields = {
            field: raw.get(field) for field in ("id", "authority_page", "authority_classification")
        }
        if not all(isinstance(value, str) for value in identity_fields.values()):
            raise ValueError(f"mapping rule {index} identity/authority fields must be strings")
        rule_id = identity_fields["id"].strip()
        authority_page = identity_fields["authority_page"].strip()
        classification = identity_fields["authority_classification"].strip()
        if not rule_id or not authority_page or not classification:
            raise ValueError(f"mapping rule {index} lacks identity or authority fields")
        if rule_id in seen_ids:
            raise ValueError(f"duplicate mapping rule id: {rule_id}")
        seen_ids.add(rule_id)

        selectors: dict[str, list[str]] = {}
        for field in ("code_paths", "code_path_prefixes"):
            values = raw.get(field, [])
            if values is None:
                values = []
            if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
                raise ValueError(f"mapping rule {rule_id} {field} must be a string list")
            selectors[field] = sorted({_normalise_path(item) for item in values})
        exact = selectors["code_paths"]
        prefixes = selectors["code_path_prefixes"]
        if not exact and not prefixes:
            raise ValueError(f"mapping rule {rule_id} has no deterministic path selector")
        rules.append({
            "id": rule_id,
            "authority_page": authority_page,
            "authority_classification": classification,
            "code_paths": exact,
            "code_path_prefixes": prefixes,
        })
    return sorted(rules, key=lambda row: row["id"])


def _candidate(rule: dict[str, Any], matched_value: str) -> dict[str, str]:
    return {
        "rule_id": rule["id"],
        "authority_page": rule["authority_page"],
        "authority_classification": rule["authority_classification"],
        "matched_value": matched_value,
    }


def resolve_implementation_key(
    implementation_key: str,
    rules: list[dict[str, Any]],
) -> dict[str, Any]:
    key = _normalise_path(implementation_key)
    exact = [_candidate(rule, key) for rule in rules if key in rule["code_paths"]]
    status = "EXACT_PATH_MATCH"
    candidates = exact

    if not candidates:
        prefix_candidates = [
            _candidate(rule, prefix)
            for rule in rules
            for prefix in rule["code_path_prefixes"]
            if key.startswith(prefix)
        ]
        if prefix_candidates:
            longest = max(len(row["matched_value"]) for row in prefix_candidates)
            candidates = [row for row in prefix_candidates if len(row["matched_value"]) == longest]
            status = "EXACT_PREFIX_MATCH"

    if not candidates:
        return {
            "implementation_key": key,
            "mapping_status": "UNMAPPED",
            "authority_page": None,
            "authority_classification": None,
            "mapping_basis": {"kind": "NONE", "rule_ids": [], "matched_values": []},
            "candidates": [],
        }

    candidates = sorted(
        candidates,
        key=lambda row: (
            row["authority_page"],
            row["authority_classification"],
            row["rule_id"],
            row["matched_value"],
        ),
    )
    targets = {(row["authority_page"], row["authority_classification"]) for row in candidates}
    if len(targets) != 1:
        return {
            "implementation_key": key,
            "mapping_status": "AMBIGUOUS",
            "authority_page": None,
            "authority_classification": None,
            "mapping_basis": {
                "kind": status,
                "rule_ids": sorted({row["rule_id"] for row in candidates}),
                "matched_values": sorted({row["matched_value"] for row in candidates}),
            },
            "candidates": candidates,
        }

    authority_page, classification = next(iter(targets))
    return {
        "implementation_key": key,
        "mapping_status": status,
        "authority_page": authority_page,
        "authority_classification": classification,
        "mapping_basis": {
            "kind": status,
            "rule_ids": sorted({row["rule_id"] for row in candidates}),
            "matched_values": sorted({row["matched_value"] for row in candidates}),
        },
        "candidates": [],
    }


def compile_crosswalk(openwiki_root: Path, manifest_path: Path) -> dict[str, Any]:
    openwiki_root = openwiki_root.resolve()
    manifest_path = manifest_path.resolve()
    if not openwiki_root.is_dir():
        raise ValueError(f"OpenWiki root is not a directory: {openwiki_root}")
    if not manifest_path.is_file():
        raise ValueError(f"authority manifest is not a file: {manifest_path}")
    manifest = _load_yaml_mapping(manifest_path)
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"manifest schema must equal {MANIFEST_SCHEMA}")
    rules = load_mapping_rules(manifest)
    records: list[dict[str, Any]] = []
    input_parts = [manifest_path.read_bytes()]

    for page_path in sorted(openwiki_root.rglob("*.md")):
        relative_page = page_path.relative_to(openwiki_root).as_posix()
        input_parts.extend((relative_page.encode("utf-8"), page_path.read_bytes()))
        metadata = _frontmatter(page_path).get("openwiki", {})
        if not isinstance(metadata, dict):
            raise ValueError(f"openwiki metadata must be a mapping: {relative_page}")
        source_paths = metadata.get("source_paths", [])
        symbols = metadata.get("symbols", [])
        if source_paths is None:
            source_paths = []
        if symbols is None:
            symbols = []
        if not isinstance(source_paths, list) or not all(
            isinstance(item, str) for item in source_paths
        ):
            raise ValueError(f"source_paths must be a string list: {relative_page}")
        if not isinstance(symbols, list) or not all(isinstance(item, str) for item in symbols):
            raise ValueError(f"symbols must be a string list: {relative_page}")

        declared_symbols = sorted({item.strip() for item in symbols if item.strip()})
        for source_path in sorted({_normalise_path(item) for item in source_paths}):
            record = resolve_implementation_key(source_path, rules)
            record.update({
                "openwiki_page": relative_page,
                "declared_symbols": declared_symbols,
                "symbol_mapping_status": "UNPAIRED_METADATA_NOT_USED_FOR_AUTHORITY",
            })
            records.append(record)

    records.sort(key=lambda row: (row["openwiki_page"], row["implementation_key"]))
    counts: dict[str, int] = {}
    for record in records:
        status = record["mapping_status"]
        counts[status] = counts.get(status, 0) + 1
    return {
        "schema": SCHEMA,
        "authority": AUTHORITY,
        "authority_ceiling": (
            "Current source decides implementation truth; WIKI_AUTHORITY_MANIFEST.yaml "
            "alone declares governed-Wiki authority."
        ),
        "manifest": manifest_path.name,
        "manifest_schema": manifest.get("schema"),
        "input_sha256": _sha256(b"\0".join(input_parts)),
        "record_count": len(records),
        "status_counts": dict(sorted(counts.items())),
        "records": records,
    }


def render_crosswalk(report: dict[str, Any]) -> bytes:
    return (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openwiki-root", type=Path, default=DEFAULT_OPENWIKI_ROOT)
    parser.add_argument("--authority-manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, help="Write the generated JSON artifact here.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail unless --output already equals the deterministic artifact.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.check and args.output is None:
        print("ERROR: --check requires --output", file=sys.stderr)
        return 2
    try:
        rendered = render_crosswalk(compile_crosswalk(args.openwiki_root, args.authority_manifest))
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.output is None:
        sys.stdout.buffer.write(rendered)
        return 0
    if args.check:
        try:
            current = args.output.read_bytes()
        except OSError as exc:
            print(f"ERROR: unable to read {args.output}: {exc}", file=sys.stderr)
            return 1
        if current != rendered:
            print(f"ERROR: stale crosswalk artifact: {args.output}", file=sys.stderr)
            return 1
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
