#!/usr/bin/env python3
"""Fail-closed audit for Wiki content freshness and authority drift.

The audit is deliberately contract-driven.  It checks the exact authority
pages declared by the authority manifest, their live source paths, declared
symbols, safe CLI probes, successor metadata, and test-file evidence.  It
does not infer semantic truth from page titles or fuzzy path matches.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
VAULT_ROOT = REPO_ROOT / "nexus_wiki_vault"
MANIFEST_PATH = VAULT_ROOT / "99_Schema" / "WIKI_AUTHORITY_MANIFEST.yaml"
DEFAULT_OUTPUT = VAULT_ROOT / "99_Schema" / "generated" / "content-freshness-audit.json"
SCHEMA = "nexus.wiki.content-freshness.v1"
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
CURRENT_LIKE = {"current", "active", "hardened", "sealed"}
ALLOWED_CLASSIFICATIONS = {
    "current_verified",
    "current_needs_review",
    "historical",
    "superseded",
    "unsupported_claim",
}
NON_PATH_SOURCE_REFS = {
    "compiled-wiki",
    "compiled-governance",
    "compiled-index",
    "compiled-topology",
    "repo-root",
    "repository evidence and current runtime reports",
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalise(path: str) -> str:
    return str(path or "").replace("\\", "/").lstrip("./")


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return {}
    return value if isinstance(value, dict) else {}


def parse_frontmatter(content: str) -> dict[str, Any]:
    match = FRONTMATTER_RE.match(content)
    if not match:
        return {}
    try:
        value = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return {}
    return value if isinstance(value, dict) else {}


def _page_state(rel_path: str, content: str, manifest: dict[str, Any]) -> str:
    known = {
        _normalise(str(row.get("path", ""))): str(row.get("classification", ""))
        for row in manifest.get("known_legacy_entries", [])
        if isinstance(row, dict)
    }
    if rel_path in known and known[rel_path]:
        return known[rel_path].strip().lower()
    fm = parse_frontmatter(content)
    lifecycle = str(fm.get("lifecycle", "")).strip().lower()
    status = str(fm.get("status", "")).strip().lower()
    return lifecycle or status or "unclassified"


def _add_page(pages: dict[str, dict[str, Any]], path: Any, role: str) -> None:
    rel = _normalise(str(path or ""))
    if not rel:
        return
    pages.setdefault(rel, {"roles": set(), "source_paths": []})["roles"].add(role)


def _authority_pages(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    pages: dict[str, dict[str, Any]] = {}
    for entry in manifest.get("canonical", {}).values():
        if isinstance(entry, dict):
            _add_page(pages, entry.get("path"), "canonical")
    for entries in manifest.get("required_authorities", {}).values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict):
                page = _normalise(str(entry.get("authority_page", "")))
                _add_page(pages, page, "required_authority")
                evidence = entry.get("source_evidence")
                if isinstance(evidence, dict) and evidence.get("source_path"):
                    pages[page]["source_paths"].append(
                        _normalise(str(evidence["source_path"]))
                    )
    for entry in manifest.get("code_symbol_mapping_rules", []):
        if not isinstance(entry, dict):
            continue
        page = _normalise(str(entry.get("authority_page", "")))
        _add_page(pages, page, "code_symbol_mapping")
        for code_path in entry.get("code_paths", []) or []:
            pages[page]["source_paths"].append(_normalise(str(code_path)))
        for prefix in entry.get("code_path_prefixes", []) or []:
            pages[page]["source_paths"].append(_normalise(str(prefix)))

    freshness = manifest.get("content_freshness", {})
    overrides = freshness.get("page_overrides", {}) if isinstance(freshness, dict) else {}
    for raw_path, override in overrides.items():
        rel = _normalise(str(raw_path))
        _add_page(pages, rel, "freshness_contract")
        if isinstance(override, dict):
            pages[rel].update(
                {
                    key: value
                    for key, value in override.items()
                    if key in {"classification", "owner", "source_paths", "required_markers"}
                }
            )
    for value in pages.values():
        value["source_paths"] = sorted(
            {_normalise(str(path)) for path in value.get("source_paths", []) if path}
        )
    return dict(sorted(pages.items()))


def _source_ref_from_frontmatter(fm: dict[str, Any]) -> str:
    raw = str(fm.get("source_of_truth", "")).strip()
    if not raw or raw.lower() in NON_PATH_SOURCE_REFS:
        return ""
    if raw.startswith(("http://", "https://", "/")):
        return ""
    if any(token in raw for token in ("/", ".py", ".rs", ".md", ".sh")):
        return _normalise(raw)
    return ""


def _resolve_source(repo_root: Path, raw_path: str) -> Path:
    rel = _normalise(raw_path)
    if rel.startswith("nexus_wiki_vault/"):
        return repo_root / rel
    return repo_root / rel


def _git_last_commit(repo_root: Path, rel_path: str) -> str:
    result = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", rel_path],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    value = result.stdout.strip()
    return value or "unknown"


def _python_symbols(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return set()
    symbols = {"__module__"}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.add(node.name)
            if isinstance(node, ast.ClassDef):
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        symbols.add(f"{node.name}.{child.name}")
    return symbols


def _source_symbol_exists(path: Path, symbol: str) -> bool:
    if path.suffix == ".py":
        return symbol in _python_symbols(path)
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    if "::" in symbol:
        owner, method = symbol.split("::", 1)
        return bool(
            re.search(rf"\bimpl\s+{re.escape(owner)}\b", content)
            and re.search(rf"\bfn\s+{re.escape(method)}\b", content)
        )
    return bool(
        re.search(rf"\b(?:fn|struct|enum|trait)\s+{re.escape(symbol)}\b", content)
    )


def _symbol_checks(repo_root: Path, freshness: dict[str, Any]) -> tuple[list[dict], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    contracts = freshness.get("symbol_contracts", {})
    if not isinstance(contracts, dict):
        return [], ["symbol_contracts_not_a_mapping"]
    for raw_path, raw_symbols in sorted(contracts.items()):
        rel = _normalise(str(raw_path))
        path = _resolve_source(repo_root, rel)
        symbols = [str(symbol) for symbol in (raw_symbols or [])]
        if not path.is_file():
            error = f"missing_symbol_source:{rel}"
            errors.append(error)
            rows.append({"path": rel, "exists": False, "symbols": []})
            continue
        missing = [symbol for symbol in symbols if not _source_symbol_exists(path, symbol)]
        if missing:
            errors.extend(f"missing_symbol:{rel}:{symbol}" for symbol in missing)
        rows.append(
            {
                "path": rel,
                "exists": True,
                "source_commit": _git_last_commit(repo_root, rel),
                "symbols": [
                    {"name": symbol, "exists": symbol not in missing}
                    for symbol in symbols
                ],
            }
        )
    return rows, errors


def _run_verification_commands(
    repo_root: Path, freshness: dict[str, Any], *, enabled: bool
) -> tuple[list[dict], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    commands = freshness.get("verification_commands", [])
    if not isinstance(commands, list):
        return [], ["verification_commands_not_a_list"]
    for command in commands:
        argv = [str(item) for item in command] if isinstance(command, list) else []
        if not argv:
            errors.append("invalid_verification_command")
            continue
        if enabled:
            result = subprocess.run(
                argv,
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=120,
            )
            passed = result.returncode == 0
            exit_code = result.returncode
        else:
            passed = True
            exit_code = None
        rows.append({"command": argv, "passed": passed, "exit_code": exit_code})
        if enabled and not passed:
            errors.append("verification_command_failed:" + " ".join(argv))
    return rows, errors


def _source_evidence(
    repo_root: Path, source_paths: list[str]
) -> tuple[list[dict], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for rel in sorted(set(source_paths)):
        path = _resolve_source(repo_root, rel)
        exists = path.is_file() or path.is_dir()
        row = {"path": rel, "exists": exists, "kind": "directory" if path.is_dir() else "file"}
        if exists:
            row["source_commit"] = _git_last_commit(repo_root, rel)
            if path.is_file():
                row["sha256"] = _sha256(path.read_bytes())
        else:
            errors.append(f"missing_source_path:{rel}")
        rows.append(row)
    return rows, errors


def _lifecycle_checks(repo_root: Path, vault_root: Path, manifest: dict[str, Any]) -> tuple[list[dict], list[str]]:
    known = {
        _normalise(str(row.get("path", ""))): row
        for row in manifest.get("known_legacy_entries", [])
        if isinstance(row, dict) and row.get("path")
    }
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    candidates = set(known)
    for path in vault_root.rglob("*.md"):
        rel = _normalise(str(path.relative_to(vault_root)))
        try:
            fm = parse_frontmatter(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        state = str(fm.get("lifecycle") or fm.get("status") or "").strip().lower()
        if state == "superseded":
            candidates.add(rel)
    for rel in sorted(candidates):
        path = vault_root / rel
        row: dict[str, Any] = {"path": rel, "classification": ""}
        entry = known.get(rel, {})
        try:
            fm = parse_frontmatter(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            fm = {}
        classification = str(entry.get("classification") or fm.get("lifecycle") or fm.get("status") or "").strip().lower()
        row["classification"] = classification
        successor = _normalise(str(fm.get("superseded_by") or entry.get("superseded_by") or ""))
        if classification == "superseded":
            row["superseded_by"] = successor
            successor_path = vault_root / successor if successor else None
            if not successor or not successor_path.is_file():
                errors.append(f"missing_superseded_successor:{rel}:{successor}")
            else:
                successor_content = successor_path.read_text(encoding="utf-8")
                successor_state = _page_state(successor, successor_content, manifest)
                row["successor_classification"] = successor_state
                if successor_state not in CURRENT_LIKE:
                    errors.append(f"successor_not_current:{rel}:{successor}:{successor_state}")
        rows.append(row)
    return rows, errors


def build_report(
    repo_root: Path = REPO_ROOT,
    vault_root: Path = VAULT_ROOT,
    manifest: dict[str, Any] | None = None,
    *,
    run_commands: bool = True,
) -> dict[str, Any]:
    manifest = manifest or _load_yaml(vault_root / "99_Schema" / "WIKI_AUTHORITY_MANIFEST.yaml")
    freshness = manifest.get("content_freshness", {})
    pages = _authority_pages(manifest)
    page_rows: list[dict[str, Any]] = []
    errors: list[str] = []
    classification_counts: dict[str, int] = {}

    for rel, contract in pages.items():
        page_path = vault_root / rel
        exists = page_path.is_file()
        content = page_path.read_text(encoding="utf-8") if exists else ""
        fm = parse_frontmatter(content)
        override = freshness.get("page_overrides", {}).get(rel, {})
        classification = str(
            contract.get("classification")
            or (override.get("classification") if isinstance(override, dict) else "")
            or ("current_verified" if "required_authority" in contract["roles"] or "code_symbol_mapping" in contract["roles"] else "current_needs_review")
        ).strip().lower()
        owner = str(
            contract.get("owner")
            or (override.get("owner") if isinstance(override, dict) else "")
            or fm.get("owner", "")
        ).strip()
        source_paths = list(contract.get("source_paths", []))
        source_ref = _source_ref_from_frontmatter(fm)
        if source_ref:
            source_paths.append(source_ref)
        source_rows, source_errors = _source_evidence(repo_root, source_paths)
        page_errors = list(source_errors)
        if not exists:
            page_errors.append("missing_authority_page")
        if classification not in ALLOWED_CLASSIFICATIONS:
            page_errors.append("invalid_classification")
            classification = "unsupported_claim"
        if classification in {"current_verified", "current_needs_review"}:
            if not owner:
                page_errors.append("missing_owner")
            if not source_rows:
                page_errors.append("missing_source_evidence")
            if any(not row["exists"] for row in source_rows):
                page_errors.append("current_authority_missing_source_path")
            required_markers = contract.get("required_markers", [])
            if isinstance(required_markers, list):
                page_errors.extend(
                    f"missing_required_marker:{marker}"
                    for marker in required_markers
                    if str(marker) not in content
                )
            else:
                page_errors.append("required_markers_not_a_list")
        if classification == "unsupported_claim":
            page_errors.append("unsupported_claim_fail_closed")
        if str(fm.get("superseded_by", "")).strip() and classification.startswith("current"):
            page_errors.append("current_page_has_superseded_marker")
        classification_counts[classification] = classification_counts.get(classification, 0) + 1
        page_rows.append(
            {
                "path": rel,
                "roles": sorted(contract["roles"]),
                "classification": classification,
                "owner": owner,
                "exists": exists,
                "content_sha256": _sha256(content.encode("utf-8")) if exists else "",
                "source_of_truth": str(fm.get("source_of_truth", "")),
                "required_markers": [str(marker) for marker in contract.get("required_markers", [])],
                "source_paths": source_rows,
                "errors": sorted(set(page_errors)),
            }
        )
        errors.extend(f"{rel}:{error}" for error in page_errors)

    symbol_rows, symbol_errors = _symbol_checks(repo_root, freshness)
    command_rows, command_errors = _run_verification_commands(
        repo_root, freshness, enabled=run_commands
    )
    test_rows: list[dict[str, Any]] = []
    test_errors: list[str] = []
    for raw_test in freshness.get("verification_tests", []) or []:
        rel = _normalise(str(raw_test))
        exists = (repo_root / rel).is_file()
        test_rows.append({"path": rel, "exists": exists})
        if not exists:
            test_errors.append(f"missing_verification_test:{rel}")
    lifecycle_rows, lifecycle_errors = _lifecycle_checks(repo_root, vault_root, manifest)
    errors.extend(symbol_errors)
    errors.extend(command_errors)
    errors.extend(test_errors)
    errors.extend(lifecycle_errors)

    source_commits = sorted(
        {
            row["source_commit"]
            for page in page_rows
            for row in page["source_paths"]
            if row.get("source_commit") and row.get("source_commit") != "unknown"
        }
    )
    source_commit = _sha256("\n".join(source_commits).encode("utf-8"))
    status = "PASS" if not errors and classification_counts.get("unsupported_claim", 0) == 0 else "FAIL"
    report = {
        "schema": SCHEMA,
        "authority": "derived_non_authoritative",
        "status": status,
        "source_commit": source_commit,
        "source_commits": source_commits,
        "pages": page_rows,
        "symbols": symbol_rows,
        "verification_commands": command_rows,
        "verified_tests": test_rows,
        "lifecycle_checks": lifecycle_rows,
        "summary": {
            "page_count": len(page_rows),
            "classification_counts": dict(sorted(classification_counts.items())),
            "source_path_count": sum(len(page["source_paths"]) for page in page_rows),
            "missing_source_path_count": sum(
                1 for page in page_rows for row in page["source_paths"] if not row["exists"]
            ),
            "symbol_error_count": len(symbol_errors),
            "verification_command_failures": len(command_errors),
            "missing_verification_tests": len(test_errors),
            "lifecycle_error_count": len(lifecycle_errors),
            "error_count": len(sorted(set(errors))),
        },
    }
    identity = {
        "schema": report["schema"],
        "source_commit": report["source_commit"],
        "pages": report["pages"],
        "symbols": report["symbols"],
        "verified_tests": report["verified_tests"],
    }
    report["source_fingerprint"] = _sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return report


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Wiki content freshness and authority drift")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--vault-root")
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    vault_root = Path(args.vault_root).resolve() if args.vault_root else repo_root / "nexus_wiki_vault"
    output = Path(args.output).resolve() if args.output else vault_root / "99_Schema" / "generated" / "content-freshness-audit.json"
    report = build_report(repo_root, vault_root)
    if report["status"] != "PASS":
        print(f"FAIL: Wiki content freshness audit has {report['summary']['error_count']} errors")
        if args.write:
            _write_report(output, report)
        return 1
    if args.write:
        _write_report(output, report)
        print("WIKI_CONTENT_AUTHORITY_FRESHNESS_PASS")
        return 0
    if not output.is_file():
        print("DRIFT: content freshness artifact not found")
        return 1
    try:
        existing = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        print("DRIFT: content freshness artifact is invalid JSON")
        return 1
    if existing != report:
        print("DRIFT: content freshness artifact does not match current sources")
        return 1
    print("CHECK PASSED: content freshness and authority evidence match")
    print("WIKI_CONTENT_AUTHORITY_FRESHNESS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
