#!/usr/bin/env python3
"""Select pytest targets for changed files.

This is Nexus JIT Tests v0: it reads the existing documentation-backed impact
map and prints a stable, conservative list of pytest targets. It does not run
pytest and does not write reports.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IMPACT_MAP = ROOT / "docs" / "testing" / "test_impact_map.md"
DEFAULT_FALLBACK_TARGETS = ("tests/core", "tests/services/test_policy_gate.py")


@dataclass(frozen=True)
class ImpactRule:
    code_path: str
    targets: tuple[str, ...]
    status: str


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
    row_pattern = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = row_pattern.match(line)
        if not match:
            continue
        code_path, targets, status = [part.strip() for part in match.groups()]
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
                )
            )
    return rules


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
            matched_rules = [rule for rule in matching_rules if len(rule.code_path) == most_specific_len]
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
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of shell-friendly targets.",
    )
    parser.add_argument(
        "--fallback",
        default=",".join(DEFAULT_FALLBACK_TARGETS),
        help="Comma-separated pytest targets used when no rule matches.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv or sys.argv[1:]))
    rules = load_impact_rules(Path(args.impact_map))
    fallback = _split_targets(args.fallback)
    targets, reasons = select_targets(args.paths, rules, fallback or DEFAULT_FALLBACK_TARGETS)

    if args.json:
        print(
            json.dumps(
                {
                    "changed_paths": [_normalize_path(path) for path in args.paths],
                    "targets": targets,
                    "reasons": reasons,
                    "impact_map": str(Path(args.impact_map)),
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
