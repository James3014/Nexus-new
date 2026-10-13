#!/usr/bin/env python3
"""Select pytest targets for changed files.

JIT Tests v0 reads the documentation-backed impact map and prints a stable,
conservative list of pytest targets. It does not run pytest or write reports.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IMPACT_MAP = ROOT / "docs" / "testing" / "test_impact_map.md"
DEFAULT_IMPACT_INDEX = ROOT / ".nexus" / "test_impact_index.json"
DEFAULT_IMPACT_STATS = ROOT / ".nexus" / "test_impact_stats.json"
DEFAULT_TEST_HISTORY = ROOT / ".nexus" / "reports" / "test_history.jsonl"
DEFAULT_FALLBACK_TARGETS = ("tests/core", "tests/services/test_policy_gate.py")
HIGH_RISK_TARGETS = ("tests/services/test_policy_gate.py",)

# Catch-all rows whose directory-wide test set is narrowed per file by derivation
# (naming convention + import/path references).  The row stays the fail-closed
# fallback whenever derivation finds nothing or cannot prove the file is only
# consumed by scripts/ops itself.
DERIVED_CATCHALL_PREFIX = "scripts/ops"
DERIVED_TESTS_DIR = "tests/ops"
_SOURCE_SCAN_DIRS = ("nexus", "scripts", "product")
_SKIP_DIR_PARTS = {"__pycache__", ".venv", "venv", "node_modules", ".git"}


@dataclass(frozen=True)
class ImpactRule:
    code_path: str
    targets: tuple[str, ...]
    status: str
    risk: str = "medium"
    risk_reason: str = ""


@dataclass(frozen=True)
class SelectionDetails:
    targets: list[str]
    reasons: list[str]
    confidence: float
    risk: str
    sources: list[str]
    history: dict[str, dict]
    unmatched_paths: list[str]
    fallback_used: bool
    high_risk_escalated: bool
    risk_reasons: list[str]
    retry_recommended: list[str]
    target_scores: dict[str, dict]


def _normalize_path(value: str) -> str:
    return value.strip().replace("\\", "/").strip("/")


def _split_targets(value: str) -> tuple[str, ...]:
    targets = []
    for part in value.split(","):
        target = _normalize_path(part.strip().strip("`"))
        if target:
            targets.append(target)
    return tuple(targets)


def _expand_existing_targets(targets: list[str]) -> list[str]:
    expanded: list[str] = []
    for target in targets:
        if any(char in target for char in "*?["):
            matches = sorted(ROOT.glob(target))
            for match in matches:
                rel = str(match.relative_to(ROOT))
                if rel not in expanded:
                    expanded.append(rel)
            continue
        if target not in expanded:
            expanded.append(target)
    return expanded


def load_impact_rules(path: Path = DEFAULT_IMPACT_MAP) -> list[ImpactRule]:
    """Load active mapping rows from docs/testing/test_impact_map.md."""
    if not path.exists():
        return []

    rules: list[ImpactRule] = []
    row_pattern = re.compile(
        r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*(?:\|\s*([^|]+?)\s*)?(?:\|\s*([^|]+?)\s*)?\|$"
    )
    for line in path.read_text(encoding="utf-8").splitlines():
        match = row_pattern.match(line)
        if not match:
            continue
        parts = [(part or "").strip() for part in match.groups()]
        code_path, targets, status = parts[:3]
        risk = parts[3].lower() if len(parts) > 3 else "medium"
        risk_reason = _normalize_path(parts[4].lower()) if len(parts) > 4 else ""
        if code_path in {"程式碼路徑", ":---"}:
            continue
        if status.lower() != "active":
            continue
        normalized_code_path = _normalize_path(code_path.strip("`"))
        split_targets = _split_targets(targets)
        if normalized_code_path and split_targets:
            rules.append(
                ImpactRule(
                    code_path=normalized_code_path,
                    targets=split_targets,
                    status=status,
                    risk=risk if risk in {"low", "medium", "high"} else "medium",
                    risk_reason=risk_reason,
                )
            )
    return rules


def load_impact_index(path: Path = DEFAULT_IMPACT_INDEX) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    mappings = payload.get("mappings", {}) if isinstance(payload, dict) else {}
    if not isinstance(mappings, dict):
        return {}
    out: dict[str, list[str]] = {}
    for key, value in mappings.items():
        if isinstance(key, str) and isinstance(value, list):
            out[_normalize_path(key)] = [
                _normalize_path(str(item)) for item in value if str(item).strip()
            ]
    return out


def load_test_history(path: Path = DEFAULT_TEST_HISTORY) -> dict[str, dict]:
    if not path.exists():
        return {}

    buckets: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        targets = [
            _normalize_path(str(target)) for target in row.get("targets", []) if str(target).strip()
        ]
        target_durations = row.get("target_durations", {})
        if not isinstance(target_durations, dict):
            target_durations = {}
        success = bool(row.get("success", False))
        row_duration = row.get("duration_sec")
        for target in targets:
            bucket = buckets.setdefault(
                target,
                {"runs": 0, "failures": 0, "duration_total_sec": 0.0, "duration_samples": 0},
            )
            bucket["runs"] += 1
            if not success:
                bucket["failures"] += 1
            duration = target_durations.get(target, row_duration)
            try:
                duration_float = float(duration)
            except (TypeError, ValueError):
                duration_float = 0.0
            if duration_float > 0:
                bucket["duration_total_sec"] += duration_float
                bucket["duration_samples"] += 1

    stats: dict[str, dict] = {}
    for target, bucket in buckets.items():
        runs = int(bucket["runs"])
        failures = int(bucket["failures"])
        samples = int(bucket["duration_samples"])
        avg_duration = round(float(bucket["duration_total_sec"]) / samples, 4) if samples else 0.0
        stats[target] = {
            "runs": runs,
            "failures": failures,
            "failure_rate": round(failures / runs, 4) if runs else 0.0,
            "avg_duration_sec": avg_duration,
            "flaky": 0 < failures < runs,
        }
    return stats


def load_impact_stats(path: Path = DEFAULT_IMPACT_STATS) -> dict[str, dict[str, dict]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    mappings = payload.get("mappings", {}) if isinstance(payload, dict) else {}
    return mappings if isinstance(mappings, dict) else {}


def _sort_targets_by_history(targets: list[str], history: dict[str, dict]) -> list[str]:
    def key(item: tuple[int, str]) -> tuple[int, int, float, float, int]:
        index, target = item
        meta = history.get(target, {})
        if not meta:
            return (1, 1, 0.0, 0.0, index)
        flaky_rank = 0 if bool(meta.get("flaky", False)) else 1
        failure_rate = -float(meta.get("failure_rate", 0.0) or 0.0)
        avg_duration = float(meta.get("avg_duration_sec", 0.0) or 0.0)
        return (0, flaky_rank, failure_rate, avg_duration, index)

    return [target for _, target in sorted(enumerate(targets), key=key)]


def _predictive_scores(
    changed_paths: list[str], targets: list[str], impact_stats: dict[str, dict[str, dict]]
) -> dict[str, dict]:
    scores: dict[str, dict] = {}
    for target in targets:
        score = 0.0
        reasons: list[str] = []
        for path in changed_paths:
            meta = impact_stats.get(path, {}).get(target, {})
            if not isinstance(meta, dict):
                continue
            score += float(meta.get("score", 0.0) or 0.0)
            reason_meta = meta.get("score_reasons", {})
            if isinstance(reason_meta, dict):
                for key, value in reason_meta.items():
                    if value:
                        reasons.append(f"{path}:{key}={value}")
        scores[target] = {"score": round(score, 4), "score_reasons": reasons}
    return scores


def _py_files(root: Path, rel_dirs: tuple[str, ...]) -> list[Path]:
    out: list[Path] = []
    for rel in rel_dirs:
        base = root / rel
        if base.is_dir():
            out.extend(
                p for p in sorted(base.rglob("*.py")) if not (set(p.parts) & _SKIP_DIR_PARTS)
            )
    return out


def _refs_module(text: str, name: str, stem: str, *, inside_ops: bool) -> bool:
    """True if ``text`` imports or path-references scripts/ops/<name>."""
    if re.search(rf"scripts[./]ops[./]{re.escape(stem)}\b", text):
        return True
    if not stem.isidentifier() and re.search(rf"(?<![\w-]){re.escape(stem)}(?![\w-])", text):
        return True  # hyphenated/extensionless executable referenced by bare name
    if name != stem and re.search(rf"scripts[./]ops[./]{re.escape(name)}(?![\w.])", text):
        return True
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        # Unparseable file that mentions the stem: be conservative.
        return re.search(rf"\b{re.escape(stem)}\b", text) is not None
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "scripts.ops" and any(a.name == stem for a in node.names):
                return True
            if mod == stem or mod.startswith(f"{stem}."):
                if inside_ops:
                    return True
            if inside_ops and node.level and not mod and any(a.name == stem for a in node.names):
                return True
            if inside_ops and node.level and mod == stem:
                return True
        elif isinstance(node, ast.Import) and inside_ops:
            if any(a.name == stem or a.name.startswith(f"{stem}.") for a in node.names):
                return True
    return False


def derive_ops_targets(changed_path: str, base_sha: str = "") -> list[str]:
    """Derive tests for one direct ``scripts/ops/<file>`` without a specific row.

    Selected: ``tests/ops/test_<stem>*.py`` plus every test file referencing the
    module (import or ``scripts/ops/<file>`` path), closed transitively over
    importers inside scripts/ops.  Returns ``[]`` (caller keeps the whole-directory
    fallback) when nothing is found or when any importer outside scripts/ops and
    tests exists, since its tests cannot be derived here.
    """
    path = _normalize_path(changed_path)
    parent, _, filename = path.rpartition("/")
    stem, dot, ext = filename.rpartition(".")
    if not dot:  # extensionless executable, e.g. scripts/ops/nexus-agy-dispatch
        stem, ext = filename, ""
    if parent != DERIVED_CATCHALL_PREFIX or ext not in {"py", "sh", ""}:
        return []
    if filename.startswith("__init__") or not re.fullmatch(r"[\w-]+", stem):
        return []
    # Added/deleted/renamed files change repository inventories (source-inventory,
    # openwiki, gitlink tests...) that no per-file derivation can see: keep the
    # whole-directory fallback unless the file exists at head and, when the base
    # is known, already existed at base (i.e. a pure modification).
    if not (ROOT / path).is_file():
        return []
    if base_sha:
        probe = subprocess.run(
            ["git", "-C", str(ROOT), "cat-file", "-e", f"{base_sha}:{path}"],
            capture_output=True,
            check=False,
        )
        if probe.returncode != 0:
            return []

    ops_files = {
        p: p.read_text(encoding="utf-8", errors="replace")
        for p in _py_files(ROOT, (DERIVED_CATCHALL_PREFIX,))
    }
    outside = {
        p: p.read_text(encoding="utf-8", errors="replace")
        for p in _py_files(ROOT, _SOURCE_SCAN_DIRS)
        if p not in ops_files
    }
    closure = {(stem, filename)}
    frontier = [(stem, filename)]
    while frontier:
        cur_stem, cur_name = frontier.pop()
        for p, text in outside.items():
            if cur_stem in text and _refs_module(text, cur_name, cur_stem, inside_ops=False):
                return []  # non-ops production importer: fail closed
        for p, text in ops_files.items():
            if p.stem == cur_stem or cur_stem not in text:
                continue
            if _refs_module(text, cur_name, cur_stem, inside_ops=True):
                key = (p.stem, p.name)
                if key not in closure:
                    closure.add(key)
                    frontier.append(key)

    tests_root = ROOT / DERIVED_TESTS_DIR
    selected: set[str] = set()
    for cur_stem, cur_name in closure:
        if tests_root.is_dir():
            for match in tests_root.glob(f"test_{cur_stem.replace('-', '_')}*.py"):
                selected.add(str(match.relative_to(ROOT)))
    for p in _py_files(ROOT, ("tests",)):
        text = p.read_text(encoding="utf-8", errors="replace")
        for cur_stem, cur_name in closure:
            if cur_stem in text and _refs_module(text, cur_name, cur_stem, inside_ops=False):
                selected.add(str(p.relative_to(ROOT)))
                break
    return sorted(selected)


def select_targets(
    changed_paths: list[str],
    rules: list[ImpactRule],
    fallback_targets: tuple[str, ...] = DEFAULT_FALLBACK_TARGETS,
) -> tuple[list[str], list[str]]:
    """Return pytest targets and selection reasons for changed paths."""
    selected: list[str] = []
    reasons: list[str] = []
    needs_fallback = False

    normalized_paths = [_normalize_path(path) for path in changed_paths if path.strip()]
    for changed_path in normalized_paths:
        matching_rules = [
            rule
            for rule in rules
            if changed_path == rule.code_path or changed_path.startswith(f"{rule.code_path}/")
        ]
        if matching_rules:
            most_specific_len = max(len(rule.code_path) for rule in matching_rules)
            matched_rules = [
                rule for rule in matching_rules if len(rule.code_path) == most_specific_len
            ]
        else:
            matched_rules = []

        matched = bool(matched_rules)
        for rule in matched_rules:
            for target in rule.targets:
                if target not in selected:
                    selected.append(target)
            reasons.append(f"{changed_path}: matched {rule.code_path}")
        if not matched:
            needs_fallback = True
            reasons.append(f"{changed_path}: fallback")

    if needs_fallback or not selected:
        for target in fallback_targets:
            if target not in selected:
                selected.append(target)

    return _expand_existing_targets(selected), reasons


def select_target_details(
    changed_paths: list[str],
    rules: list[ImpactRule],
    fallback_targets: tuple[str, ...] = DEFAULT_FALLBACK_TARGETS,
    *,
    index_path: Path = DEFAULT_IMPACT_INDEX,
    stats_path: Path = DEFAULT_IMPACT_STATS,
    history_path: Path = DEFAULT_TEST_HISTORY,
    ranking: str = "static",
    base_sha: str = "",
) -> SelectionDetails:
    selected: list[str] = []
    reasons: list[str] = []
    sources: list[str] = []
    index = load_impact_index(index_path)
    impact_stats = load_impact_stats(stats_path)
    history = load_test_history(history_path)

    normalized_paths = [_normalize_path(path) for path in changed_paths if path.strip()]
    unmatched_paths: list[str] = []
    high_risk = False
    risk_reasons: list[str] = []
    for changed_path in normalized_paths:
        path_matched = False
        path_high_risk = False
        index_targets = index.get(changed_path, [])
        if index_targets:
            for target in index_targets:
                if target not in selected:
                    selected.append(target)
            reasons.append(f"{changed_path}: import-index")
            if "import_index" not in sources:
                sources.append("import_index")
            path_matched = True

        matching_rules = [
            rule
            for rule in rules
            if changed_path == rule.code_path or changed_path.startswith(f"{rule.code_path}/")
        ]
        if matching_rules:
            most_specific_len = max(len(rule.code_path) for rule in matching_rules)
            matched_rules = [
                rule for rule in matching_rules if len(rule.code_path) == most_specific_len
            ]
            path_high_risk = any(rule.risk == "high" for rule in matched_rules)
            for rule in matched_rules:
                if (
                    rule.risk == "high"
                    and rule.risk_reason
                    and rule.risk_reason not in risk_reasons
                ):
                    risk_reasons.append(rule.risk_reason)
        mapped_targets, mapped_reasons = select_targets([changed_path], rules, ())
        if (
            mapped_targets
            and matching_rules
            and all(rule.code_path == DERIVED_CATCHALL_PREFIX for rule in matched_rules)
        ):
            derived = derive_ops_targets(changed_path, base_sha)
            if derived:
                mapped_targets = derived
                mapped_reasons = [f"{changed_path}: derived scripts/ops tests"]
        for target in mapped_targets:
            if target not in selected:
                selected.append(target)
        if mapped_targets:
            if "impact_map" not in sources:
                sources.append("impact_map")
            reasons.extend(mapped_reasons)
            path_matched = True
            if path_high_risk:
                high_risk = True
        elif not path_matched:
            unmatched_paths.append(changed_path)
            reasons.extend(mapped_reasons or [f"{changed_path}: fallback"])

    needs_fallback = not selected or any(reason.endswith(": fallback") for reason in reasons)
    if needs_fallback:
        for target in fallback_targets:
            if target not in selected:
                selected.append(target)
        if "fallback" not in sources:
            sources.append("fallback")
        if not reasons:
            reasons.extend(f"{path}: fallback" for path in normalized_paths)

    if high_risk:
        for target in HIGH_RISK_TARGETS:
            if target not in selected:
                selected.append(target)
        if "high_risk" not in sources:
            sources.append("high_risk")
        reasons.append("high-risk escalation")

    expanded = _sort_targets_by_history(_expand_existing_targets(selected), history)
    target_scores = _predictive_scores(normalized_paths, expanded, impact_stats)
    if ranking == "predictive" and any(meta["score"] for meta in target_scores.values()):
        expanded = sorted(
            expanded,
            key=lambda target: (
                -float(target_scores.get(target, {}).get("score", 0.0)),
                expanded.index(target),
            ),
        )
    retry_recommended = [
        target for target in expanded if bool(history.get(target, {}).get("flaky", False))
    ]
    if "fallback" in sources:
        confidence = 0.4
        risk = "high"
        if "fallback" not in risk_reasons:
            risk_reasons.append("fallback")
    elif high_risk:
        confidence = 0.85
        risk = "high"
    elif "import_index" in sources:
        confidence = 0.9
        risk = "low"
    else:
        confidence = 0.7
        risk = "medium"
    return SelectionDetails(
        targets=expanded,
        reasons=reasons,
        confidence=confidence,
        risk=risk,
        sources=sources,
        history=history,
        unmatched_paths=unmatched_paths,
        fallback_used=needs_fallback,
        high_risk_escalated=high_risk,
        risk_reasons=risk_reasons,
        retry_recommended=retry_recommended,
        target_scores={
            target: target_scores.get(target, {"score": 0.0, "score_reasons": []})
            for target in expanded
        },
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Select pytest targets for changed Nexus files without running pytest."
    )
    parser.add_argument("paths", nargs="*", help="Changed file or directory paths.")
    parser.add_argument(
        "--impact-map",
        default=str(DEFAULT_IMPACT_MAP),
        help="Markdown impact map path.",
    )
    parser.add_argument(
        "--impact-index",
        default=str(DEFAULT_IMPACT_INDEX),
        help="JSON import impact index path.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of shell-friendly targets.",
    )
    parser.add_argument(
        "--fallback",
        default=",".join(DEFAULT_FALLBACK_TARGETS),
        help="Comma-separated pytest targets used when no rule matches.",
    )
    parser.add_argument(
        "--test-history",
        default=str(DEFAULT_TEST_HISTORY),
        help="JSONL test history path used for duration/flaky ranking.",
    )
    parser.add_argument(
        "--impact-stats",
        default=str(DEFAULT_IMPACT_STATS),
        help="JSON impact stats path used for predictive ranking.",
    )
    parser.add_argument(
        "--ranking",
        choices=("static", "predictive"),
        default="static",
        help="Ranking strategy. Default remains static.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv or sys.argv[1:]))
    rules = load_impact_rules(Path(args.impact_map))
    fallback = _split_targets(args.fallback)
    details = select_target_details(
        args.paths,
        rules,
        fallback or DEFAULT_FALLBACK_TARGETS,
        index_path=Path(args.impact_index),
        stats_path=Path(args.impact_stats),
        history_path=Path(args.test_history),
        ranking=args.ranking,
    )
    targets, reasons = details.targets, details.reasons

    if args.json:
        print(
            json.dumps(
                {
                    "changed_paths": [_normalize_path(path) for path in args.paths],
                    "targets": targets,
                    "reasons": reasons,
                    "confidence": details.confidence,
                    "risk": details.risk,
                    "sources": details.sources,
                    "history": {target: details.history.get(target, {}) for target in targets},
                    "selected_count": len(targets),
                    "fallback_used": details.fallback_used,
                    "high_risk_escalated": details.high_risk_escalated,
                    "risk_reasons": details.risk_reasons,
                    "unmatched_paths": details.unmatched_paths,
                    "retry_recommended": details.retry_recommended,
                    "ranking": args.ranking,
                    "target_scores": details.target_scores,
                    "impact_map": str(Path(args.impact_map)),
                    "impact_index": str(Path(args.impact_index)),
                    "impact_stats": str(Path(args.impact_stats)),
                    "test_history": str(Path(args.test_history)),
                    "rules_loaded": len(rules),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(" ".join(targets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
