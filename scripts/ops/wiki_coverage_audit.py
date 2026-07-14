#!/usr/bin/env python3
import ast
from functools import lru_cache
import os
import re
import json
from pathlib import Path
import yaml

# 🛡️ Nexus Wiki Coverage Audit (Agent G - WS-A Hardened v2.1)
# Purpose: Quantify true governance coverage for mandatory domains and enforce 100% Key Path.

REPO_ROOT = Path(str(__import__("pathlib").Path(__file__).resolve().parents[2]))
VAULT_ROOT = REPO_ROOT / "nexus_wiki_vault"
REPORT_PATH = REPO_ROOT / ".nexus" / "reports" / "wiki_coverage_report.json"
KEYPATH_REPORT_PATH = REPO_ROOT / ".nexus" / "reports" / "wiki_keypath_coverage_report.json"

TARGET_DIRS = [
    "nexus/core", "nexus/engine", "nexus/services", "scripts/ops", "scripts/engine"
]
SYMBOL_SCAN_DIRS = [*TARGET_DIRS, "tests"]

KEY_PATHS = [
    "scripts/ops/ci_gate.py",
    "scripts/ops/wiki_linter.py",
    "scripts/ops/wiki_drift_audit.py",
    "scripts/ops/wiki_coverage_audit.py",
    "scripts/engine/nexus_cli.py",
    "nexus/core/orchestrator.py",
    "nexus/core/state_repository.py",
    "nexus/core/policy_manager.py",
    "nexus/core/memory/ingest.py",
    "nexus/services/memory.py",
    "nexus/services/memory_indexer.py",
    "nexus-desk/src-tauri/src/main.rs"
]

EXCLUDED_PATTERNS = [
    r"__pycache__",
    r"\.pytest_cache",
    r"\.git",
    r"\.nexus",
    r"tests/",
    r"docs/",
    r".*\.bak$",
    r".*~",
    r"setup\.py",
    r"__init__\.py",
    r"\.DS_Store"
]

COVERAGE_THRESHOLD = 0.85
COVERAGE_TAXONOMY = (
    "must_document",
    "should_document",
    "allowed_exclusion",
    "generated",
    "test_only",
    "internal_helper",
    "deprecated",
    "legacy",
)
VALID_AUTHORITY_CLASSIFICATIONS = {"current", "active"}
REQUIRED_MAPPING_FIELDS = (
    "code_path",
    "symbol",
    "authority_page",
    "authority_classification",
    "source_evidence",
)
GENERATED_PATH_MARKERS = ("generated/", ".nexus/", "__pycache__/")
LEGACY_PATH_MARKERS = ("90_sources/archive/", "90_sources/legacy_wiki/", "/legacy/")
DEPRECATED_PATH_MARKERS = ("/deprecated/", ".deprecated")

# Patterns to find code references in Wiki body
PROVENANCE_PATTERN = re.compile(
    r"\[source:\s*(.*?)\]|\(source:\s*(.*?)\)|\[code:\s*(.*?)\]|\(code:\s*(.*?)\)|\[Source:\s*(.*?)\]", 
    re.I
)
# Pattern for Frontmatter
FM_SOT_PATTERN = re.compile(r"^source_of_truth:\s*(.*?)$", re.M)

def is_excluded(path_str):
    for pattern in EXCLUDED_PATTERNS:
        if re.search(pattern, path_str):
            return True
    return False


def coverage_policy() -> dict:
    """Return the explicit Phase 2 coverage policy contract."""
    return {
        "schema": "nexus.wiki.coverage-policy.v1",
        "threshold": COVERAGE_THRESHOLD,
        "taxonomy": list(COVERAGE_TAXONOMY),
        "required_mapping_fields": list(REQUIRED_MAPPING_FIELDS),
        "valid_authority_classifications": sorted(VALID_AUTHORITY_CLASSIFICATIONS),
        "matching": "exact_code_path_and_symbol_only",
        "fuzzy_basename_matches_are_not_coverage": True,
        "generated_or_legacy_authority_is_rejected": True,
        "formal_mapping_manifest_key": "code_symbol_mapping_rules",
        "formal_mapping_wave_thresholds": {
            "1": 1.0,
            "2": 1.0,
            "3": 1.0,
            "4": COVERAGE_THRESHOLD,
        },
    }


def classify_coverage_item(
    code_path: str,
    symbol: str = "",
    *,
    allowed_exclusion: bool = False,
) -> str:
    """Classify a code item without treating classification as coverage."""
    normalized = code_path.replace("\\", "/").lower()
    if allowed_exclusion:
        return "allowed_exclusion"
    if any(marker in normalized for marker in GENERATED_PATH_MARKERS):
        return "generated"
    if normalized.startswith("tests/") or "/tests/" in normalized:
        return "test_only"
    if any(marker in normalized for marker in LEGACY_PATH_MARKERS):
        return "legacy"
    if any(marker in normalized for marker in DEPRECATED_PATH_MARKERS):
        return "deprecated"
    symbol_name = symbol.rsplit(".", 1)[-1] if symbol else ""
    if symbol and symbol != "__module__" and symbol_name.startswith("_"):
        return "internal_helper"
    if code_path in KEY_PATHS:
        return "must_document"
    return "should_document"


@lru_cache(maxsize=None)
def _python_symbols(path: Path) -> tuple[list[str], bool]:
    """Return deterministic module and qualified Python symbols for one file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return ["__module__"], True

    symbols = ["__module__"]

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.scope: list[str] = []

        def _qualified(self, name: str) -> str:
            return ".".join([*self.scope, name])

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            symbols.append(self._qualified(node.name))
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            symbols.append(self._qualified(node.name))
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            symbols.append(self._qualified(node.name))
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

    Visitor().visit(tree)
    return sorted(set(symbols)), False


def get_symbol_inventory() -> list[dict]:
    """Build the Phase 2 denominator without inferring Wiki mappings."""
    inventory: list[dict] = []
    paths: set[str] = set()
    for directory in SYMBOL_SCAN_DIRS:
        abs_dir = REPO_ROOT / directory
        if not abs_dir.exists():
            continue
        for path in abs_dir.glob("**/*.py"):
            if not path.is_file():
                continue
            relative = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
            if relative in paths or is_excluded(relative) and not relative.startswith("tests/"):
                continue
            paths.add(relative)
            symbols, parse_error = _python_symbols(path)
            for symbol in symbols:
                inventory.append(
                    {
                        "code_path": relative,
                        "symbol": symbol,
                        "classification": classify_coverage_item(relative, symbol),
                        "parse_error": parse_error,
                    }
                )
    return sorted(inventory, key=lambda item: (item["code_path"], item["symbol"]))


def _authority_page_classification(
    authority_page: str,
    authority_pages: dict | None,
) -> str:
    normalized = authority_page.replace("\\", "/").lower()
    if any(marker in normalized for marker in GENERATED_PATH_MARKERS):
        return "generated"
    if any(marker in normalized for marker in LEGACY_PATH_MARKERS):
        return "legacy"
    if authority_pages is not None:
        metadata = authority_pages.get(authority_page)
        if metadata is None:
            return "missing"
        return str(metadata.get("classification", "")).strip().lower()
    return "current"


def validate_mapping(
    mapping: dict,
    repo_root: Path,
    vault_root: Path,
    authority_pages: dict | None = None,
) -> list[str]:
    """Validate one formal code-symbol-to-current-authority mapping."""
    errors: list[str] = []
    for field in REQUIRED_MAPPING_FIELDS:
        if not mapping.get(field):
            errors.append(f"missing_{field}")

    code_path = str(mapping.get("code_path", "")).replace("\\", "/")
    symbol = str(mapping.get("symbol", "")).strip()
    authority_page = str(mapping.get("authority_page", "")).replace("\\", "/")
    if code_path and not (repo_root / code_path).is_file():
        errors.append("missing_code_path")
    if symbol and (symbol == Path(code_path).name or symbol.endswith(".py")):
        errors.append("symbol_is_filename_only")
    if (
        code_path
        and symbol
        and not errors
        and code_path.lower().endswith(".py")
    ):
        symbols, parse_error = _python_symbols(repo_root / code_path)
        if parse_error or symbol not in symbols:
            errors.append("missing_symbol")

    if authority_page:
        page_path = vault_root / authority_page
        if authority_pages is None and not page_path.is_file():
            errors.append("missing_authority_page")
        page_classification = _authority_page_classification(
            authority_page, authority_pages
        )
        if page_classification == "missing":
            errors.append("missing_authority_page")
        elif page_classification not in VALID_AUTHORITY_CLASSIFICATIONS:
            errors.append(f"invalid_authority_classification:{page_classification}")

    authority_classification = str(
        mapping.get("authority_classification", "")
    ).strip().lower()
    if authority_classification not in VALID_AUTHORITY_CLASSIFICATIONS:
        errors.append("invalid_mapping_authority_classification")

    evidence = mapping.get("source_evidence")
    if not isinstance(evidence, dict) or not evidence.get("source_path"):
        errors.append("missing_source_evidence")
    elif str(evidence.get("source_path")).replace("\\", "/") != code_path:
        errors.append("source_evidence_path_mismatch")

    return sorted(set(errors))


def validate_mappings(
    mappings: list[dict],
    repo_root: Path,
    vault_root: Path,
    authority_pages: dict | None = None,
) -> dict:
    """Validate formal mappings and reject duplicate code-symbol keys."""
    errors: list[dict] = []
    seen: set[tuple[str, str]] = set()
    valid: list[dict] = []
    for index, mapping in enumerate(mappings):
        key = (
            str(mapping.get("code_path", "")),
            str(mapping.get("symbol", "")),
        )
        mapping_errors = validate_mapping(
            mapping, repo_root, vault_root, authority_pages=authority_pages
        )
        if key in seen:
            mapping_errors.append("duplicate_code_symbol_mapping")
        seen.add(key)
        if mapping_errors:
            errors.append({"index": index, "errors": sorted(set(mapping_errors))})
        else:
            valid.append(mapping)
    return {
        "valid": valid,
        "errors": errors,
        "valid_count": len(valid),
        "error_count": len(errors),
    }


def load_authority_manifest() -> dict:
    path = VAULT_ROOT / "99_Schema" / "WIKI_AUTHORITY_MANIFEST.yaml"
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return {}


def _frontmatter(content: str) -> dict:
    if not content.startswith("---"):
        return {}
    end = content.find("---", 3)
    if end == -1:
        return {}
    try:
        return yaml.safe_load(content[3:end]) or {}
    except yaml.YAMLError:
        return {}


def get_authority_pages(manifest: dict | None = None) -> dict:
    """Return exact vault paths and their live classification."""
    manifest = manifest or load_authority_manifest()
    legacy = {
        str(entry.get("path", "")).replace("\\", "/"): str(
            entry.get("classification", "legacy")
        ).strip().lower()
        for entry in manifest.get("known_legacy_entries", [])
        if isinstance(entry, dict)
    }
    pages: dict[str, dict] = {}
    for path in VAULT_ROOT.glob("**/*.md"):
        relative = str(path.relative_to(VAULT_ROOT)).replace("\\", "/")
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        frontmatter = _frontmatter(content)
        lifecycle = str(frontmatter.get("lifecycle", "")).strip().lower()
        status = str(frontmatter.get("status", "")).strip().lower()
        classification = lifecycle or status or "unclassified"
        if relative in legacy:
            classification = legacy[relative]
        if any(marker in relative.lower() for marker in GENERATED_PATH_MARKERS):
            classification = "generated"
        if any(marker in relative.lower() for marker in LEGACY_PATH_MARKERS):
            classification = "legacy"
        pages[relative] = {
            "classification": classification,
            "owner": frontmatter.get("owner", ""),
            "content": content,
        }
    return pages


def _mapping_rule_matches(rule: dict, code_path: str) -> bool:
    normalized = code_path.replace("\\", "/")
    exact_paths = {
        str(path).replace("\\", "/") for path in rule.get("code_paths", [])
    }
    if normalized in exact_paths:
        return True
    return any(
        normalized.startswith(str(prefix).replace("\\", "/"))
        for prefix in rule.get("code_path_prefixes", [])
    )


def expand_formal_mappings(
    symbol_inventory: list[dict] | None = None,
    manifest: dict | None = None,
) -> tuple[list[dict], list[str]]:
    """Expand explicit path rules into exact code-path/symbol mappings."""
    manifest = manifest or load_authority_manifest()
    rules = manifest.get("code_symbol_mapping_rules", [])
    if not isinstance(rules, list):
        return [], ["code_symbol_mapping_rules_not_a_list"]

    inventory = symbol_inventory if symbol_inventory is not None else get_symbol_inventory()
    mappings: list[dict] = []
    errors: list[str] = []
    for item in inventory:
        if item["classification"] not in {"must_document", "should_document"}:
            continue
        exact_matches = [
            rule
            for rule in rules
            if isinstance(rule, dict)
            and item["code_path"] in {
                str(path).replace("\\", "/")
                for path in rule.get("code_paths", [])
            }
        ]
        matches = exact_matches or [
            rule
            for rule in rules
            if isinstance(rule, dict) and _mapping_rule_matches(rule, item["code_path"])
        ]
        if len(matches) != 1:
            errors.append(
                f"{item['code_path']}::{item['symbol']}:mapping_rule_count={len(matches)}"
            )
            continue
        rule = matches[0]
        mappings.append(
            {
                "code_path": item["code_path"],
                "symbol": item["symbol"],
                "authority_page": str(rule.get("authority_page", "")).replace("\\", "/"),
                "authority_classification": rule.get("authority_classification", ""),
                "source_evidence": {
                    "kind": rule.get("source_evidence_kind", "code_backed"),
                    "source_path": item["code_path"],
                    "symbol": item["symbol"],
                },
                "mapping_rule_id": rule.get("id", ""),
                "wave": rule.get("wave", "unassigned"),
            }
        )
    return mappings, sorted(errors)


def formal_mapping_report(
    symbol_inventory: list[dict],
    manifest: dict,
) -> dict:
    eligible = [
        item
        for item in symbol_inventory
        if item["classification"] in {"must_document", "should_document"}
    ]
    mappings, expansion_errors = expand_formal_mappings(symbol_inventory, manifest)
    authority_pages = get_authority_pages(manifest)
    validation = validate_mappings(
        mappings,
        REPO_ROOT,
        VAULT_ROOT,
        authority_pages=authority_pages,
    )
    valid_keys = {
        (mapping["code_path"], mapping["symbol"])
        for mapping in validation["valid"]
    }
    mappings_by_key = {
        (mapping["code_path"], mapping["symbol"]): mapping
        for mapping in mappings
    }

    wave_stats: dict[str, dict] = {}
    for item in eligible:
        mapping = mappings_by_key.get((item["code_path"], item["symbol"]))
        wave = str(mapping.get("wave", "unassigned")) if mapping else "unassigned"
        stats = wave_stats.setdefault(wave, {"eligible": 0, "mapped": 0})
        stats["eligible"] += 1
        if (item["code_path"], item["symbol"]) in valid_keys:
            stats["mapped"] += 1
    for wave, stats in wave_stats.items():
        stats["ratio"] = stats["mapped"] / stats["eligible"] if stats["eligible"] else 0.0
        threshold = 0.85
        if wave in {"1", "2", "3"}:
            threshold = 1.0
        stats["threshold"] = threshold
        stats["status"] = "PASS" if stats["ratio"] >= threshold else "FAIL"

    priority_scopes = {
        "core_runtime": ("nexus/core/", "nexus/engine/", "scripts/engine/"),
        "critical_services": ("nexus/services/",),
        "operator_flows": ("scripts/ops/",),
    }
    priority_scope_stats: dict[str, dict] = {}
    for scope, prefixes in priority_scopes.items():
        scope_items = [
            item
            for item in eligible
            if item["code_path"].startswith(prefixes)
        ]
        mapped = sum(
            (item["code_path"], item["symbol"]) in valid_keys
            for item in scope_items
        )
        ratio = mapped / len(scope_items) if scope_items else 0.0
        priority_scope_stats[scope] = {
            "eligible": len(scope_items),
            "mapped": mapped,
            "ratio": ratio,
            "threshold": 1.0,
            "status": "PASS" if ratio >= 1.0 else "FAIL",
        }

    ratio = validation["valid_count"] / len(eligible) if eligible else 0.0
    return {
        "status": "PASS"
        if (
            not expansion_errors
            and not validation["errors"]
            and ratio >= COVERAGE_THRESHOLD
            and all(
                stat["status"] == "PASS"
                for stat in wave_stats.values()
                if stat["eligible"]
            )
            and all(stat["status"] == "PASS" for stat in priority_scope_stats.values())
        )
        else "FAIL",
        "eligible_symbols": len(eligible),
        "mapped_symbols": validation["valid_count"],
        "unmapped_symbols": len(eligible) - validation["valid_count"],
        "coverage_ratio_float": ratio,
        "coverage_ratio": f"{ratio:.2%}",
        "threshold": COVERAGE_THRESHOLD,
        "wave_stats": wave_stats,
        "priority_scope_stats": priority_scope_stats,
        "expansion_error_count": len(expansion_errors),
        "validation_error_count": validation["error_count"],
        "expansion_errors": expansion_errors[:20],
        "validation_errors": validation["errors"][:20],
        "mapping_rule_count": len(manifest.get("code_symbol_mapping_rules", [])),
        "required_mapping_fields": list(REQUIRED_MAPPING_FIELDS),
    }

def get_code_files():
    files = set()
    for d in TARGET_DIRS:
        abs_dir = REPO_ROOT / d
        if not abs_dir.exists(): continue
        for p in abs_dir.glob("**/*"):
            if p.is_file():
                rel_p = str(p.relative_to(REPO_ROOT))
                if not is_excluded(rel_p):
                    files.add(rel_p)
    # 確保 KEY_PATHS 中的檔案也被納入 (即使不在 TARGET_DIRS)
    for kp in KEY_PATHS:
        if (REPO_ROOT / kp).exists():
            files.add(kp)
    return sorted(list(files))

def get_covered_files_from_wiki():
    covered = set()
    for md in VAULT_ROOT.glob("**/*.md"):
        if "99_Schema" in str(md): continue
        try:
            content = md.read_text(encoding="utf-8")
            
            # 1. 萃取 Frontmatter 中的 source_of_truth
            fm_match = FM_SOT_PATTERN.search(content)
            if fm_match:
                sot = fm_match.group(1).strip()
                if sot: covered.add(sot)
            
            # 2. 萃取本文中的 [Source: path] 或 [Code: path]
            matches = PROVENANCE_PATTERN.findall(content)
            for match in matches:
                path_str = next((g for g in match if g), "").strip()
                path_str = path_str.replace("`", "").replace("'", "").replace("\"", "")
                path_str = re.sub(r"\s+Part\s+.*$", "", path_str, flags=re.I)
                path_str = re.sub(r"\s+L\d+.*$", "", path_str, flags=re.I)
                path_str = re.sub(r"#.*$", "", path_str).strip()
                if path_str: covered.add(path_str.replace("\\ ", " "))
        except Exception:
            continue
    return covered

def run_audit():
    print("🛡️ WS-A: Executing Hardened Wiki Coverage Audit v2.1...")
    all_code_files = get_code_files()
    symbol_inventory = get_symbol_inventory()
    authority_manifest = load_authority_manifest()
    formal_mapping = formal_mapping_report(symbol_inventory, authority_manifest)
    wiki_mentions = get_covered_files_from_wiki()
    
    covered_files = []
    uncovered_files = []

    for f in all_code_files:
        # Phase 2 policy: only exact repository-relative paths count as a
        # file-level reference. Basenames and suffix/substring matches are
        # retained as unverified mentions, never as coverage evidence.
        if f in wiki_mentions:
            covered_files.append(f)
        else:
            uncovered_files.append(f)
            
    coverage_ratio = len(covered_files) / len(all_code_files) if all_code_files else 0
    taxonomy_counts = {
        category: sum(
            classify_coverage_item(path) == category for path in all_code_files
        )
        for category in COVERAGE_TAXONOMY
    }
    symbol_taxonomy_counts = {
        category: sum(
            item["classification"] == category for item in symbol_inventory
        )
        for category in COVERAGE_TAXONOMY
    }
    eligible_categories = {"must_document", "should_document"}
    eligible_symbols = sum(
        symbol_taxonomy_counts[category] for category in eligible_categories
    )
    
    # 關鍵路徑查驗
    # Missing optional products are reported separately. They must not make
    # existing key-path coverage fail, otherwise removed/non-runtime products
    # keep reopening the closure gate.
    existing_key_paths = [f for f in KEY_PATHS if (REPO_ROOT / f).exists()]
    missing_key_paths = [f for f in KEY_PATHS if f not in existing_key_paths]
    keypath_covered = [f for f in covered_files if f in existing_key_paths]
    keypath_uncovered = [f for f in existing_key_paths if f not in covered_files]
    keypath_ratio = len(keypath_covered) / len(existing_key_paths) if existing_key_paths else 1.0
    
    # 指標狀態
    global_status = "PASS" if coverage_ratio >= COVERAGE_THRESHOLD else "FAIL"
    keypath_status = "PASS" if keypath_ratio >= 1.0 else "FAIL"

    # 計算 Domain 覆蓋率
    domain_stats = {}
    for d in TARGET_DIRS:
        d_all = [f for f in all_code_files if f.startswith(d)]
        d_cov = [f for f in covered_files if f.startswith(d)]
        domain_stats[d] = f"{len(d_cov)}/{len(d_all)} ({len(d_cov)/len(d_all):.1%})" if d_all else "N/A"

    report = {
        "summary": {
            "total_files": len(all_code_files),
            "covered_files": len(covered_files),
            "uncovered_files": len(uncovered_files),
            "coverage_ratio_float": formal_mapping["coverage_ratio_float"],
            "coverage_ratio": formal_mapping["coverage_ratio"],
            "file_coverage_ratio_float": coverage_ratio,
            "file_coverage_ratio": f"{coverage_ratio:.2%}",
            "keypath_coverage_ratio": f"{keypath_ratio:.2%}",
            "global_status": formal_mapping["status"],
            "file_global_status": global_status,
            "keypath_status": keypath_status,
            "domain_stats": domain_stats,
            "taxonomy_counts": taxonomy_counts,
            "eligible_categories": sorted(eligible_categories),
            "excluded_categories": sorted(
                set(COVERAGE_TAXONOMY) - eligible_categories
            ),
            "symbol_inventory": {
                "status": "collected_ast_baseline_phase2",
                "total_symbols": len(symbol_inventory),
                "eligible_symbols": eligible_symbols,
                "excluded_symbols": len(symbol_inventory) - eligible_symbols,
                "runtime_critical_symbols": symbol_taxonomy_counts["must_document"],
                "internal_helper_symbols": symbol_taxonomy_counts["internal_helper"],
                "test_only_symbols": symbol_taxonomy_counts["test_only"],
                "generated_symbols": symbol_taxonomy_counts["generated"],
                "deprecated_symbols": symbol_taxonomy_counts["deprecated"],
                "legacy_symbols": symbol_taxonomy_counts["legacy"],
                "allowed_exclusion_symbols": symbol_taxonomy_counts["allowed_exclusion"],
                "parse_error_files": sorted(
                    {
                        item["code_path"]
                        for item in symbol_inventory
                        if item["parse_error"]
                    }
                ),
                "taxonomy_counts": symbol_taxonomy_counts,
            },
            "formal_symbol_mapping": {
                **formal_mapping,
            },
        },
        "policy": coverage_policy(),
        "top_uncovered_paths": uncovered_files[:30],
    }
    
    keypath_report = {
        "keypath_coverage_ratio": f"{keypath_ratio:.2%}",
        "keypath_status": keypath_status,
        "keypath_uncovered": keypath_uncovered,
        "keypath_covered": keypath_covered,
        "keypath_missing": missing_key_paths
    }
    
    os.makedirs(REPORT_PATH.parent, exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)
    with open(KEYPATH_REPORT_PATH, "w") as f:
        json.dump(keypath_report, f, indent=2)
        
    print(f"📊 Global Formal Result: {formal_mapping['coverage_ratio']} ({formal_mapping['status']})")
    print(f"🗂️ File Baseline Result: {coverage_ratio:.2%} ({global_status})")
    print(f"🎯 Key Path Result: {report['summary']['keypath_coverage_ratio']} ({keypath_status})")
    print(f"📁 Domain Analysis:")
    for d, stat in domain_stats.items():
        print(f"  - {d}: {stat}")
    
    if keypath_ratio < 1.0:
        print(f"❌ Critical Error: Key Path coverage is NOT 100%. Missing: {', '.join(keypath_uncovered)}")
    if missing_key_paths:
        print(f"ℹ️ Key Path products not present in this checkout: {', '.join(missing_key_paths)}")
    
    if coverage_ratio < COVERAGE_THRESHOLD:
        print(f"ℹ️ File baseline gap: {len(uncovered_files)} files remain outside formal symbol coverage.")
    if formal_mapping["status"] != "PASS":
        print(
            f"⚠️ Formal mapping gap: {formal_mapping['unmapped_symbols']} eligible symbols remain."
        )
    return 0 if formal_mapping["status"] == "PASS" and keypath_status == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(run_audit())
