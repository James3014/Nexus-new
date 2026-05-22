#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Mapping


DEFAULT_OUTPUT = Path("docs/reports/NEXUS_SIGNAL_COLLECTOR_SPLIT_PREGATE_2026-05-22.json")


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def _relative(path: Path, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _python_files(repo_root: Path) -> list[Path]:
    roots = [repo_root / "nexus", repo_root / "tests"]
    files: list[Path] = []
    for root in roots:
        if root.exists():
            files.extend(sorted(root.rglob("*.py")))
    return [path for path in files if "__pycache__" not in path.parts]


def _reference_rows(repo_root: Path, needle: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in _python_files(repo_root):
        text = _read_text(path)
        if needle not in text:
            continue
        rows.append(
            {
                "path": _relative(path, repo_root),
                "reference_count": text.count(needle),
                "defines_symbol": bool(re.search(rf"^\s*def\s+{re.escape(needle)}\b", text, re.MULTILINE)),
                "monkeypatch_or_patch_sensitive": bool(re.search(r"(monkeypatch|patch\()", text)),
            }
        )
    return rows


def build_signal_collector_split_pregate(*, repo_root: Path = Path(".")) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    route_decider = repo_root / "nexus/research/flow/route_decider.py"
    signal_collector = repo_root / "nexus/research/flow/signal_collector.py"
    route_tests = repo_root / "tests/app/test_research_flow_service.py"
    route_decider_text = _read_text(route_decider)
    signal_collector_text = _read_text(signal_collector)
    route_tests_text = _read_text(route_tests)
    reference_rows = _reference_rows(repo_root, "collect_route_signals")
    definitions = [row for row in reference_rows if row["defines_symbol"]]
    caller_rows = [row for row in reference_rows if not row["defines_symbol"]]
    monkeypatch_sensitive = [row for row in reference_rows if row["monkeypatch_or_patch_sensitive"]]
    deletion_test_present = "test_route_decider_reexports_split_signal_collector_contracts" in route_tests_text
    split_module_present = "def collect_route_signals" in signal_collector_text
    facade_reexport_present = "from nexus.research.flow.signal_collector import" in route_decider_text

    blockers: list[str] = []
    if not route_decider.exists():
        blockers.append("route_decider_missing")
    if len(definitions) != 1:
        blockers.append("collect_route_signals_definition_count_not_one")
    if not signal_collector.exists() or not split_module_present:
        blockers.append("signal_collector_module_missing")
    if not facade_reexport_present:
        blockers.append("route_decider_reexport_missing")
    if not deletion_test_present:
        blockers.append("deletion_test_missing")

    decision = "APPROVED" if not blockers else "DEFERRED"
    return {
        "schema": "nexus.signal_collector_split_pregate.v1",
        "status": "PASS",
        "decision": decision,
        "implementation_allowed": decision == "APPROVED",
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
        "zero_trust_v2_modification_allowed": False,
        "summary": {
            "reference_file_count": len(reference_rows),
            "definition_count": len(definitions),
            "caller_file_count": len(caller_rows),
            "monkeypatch_sensitive_file_count": len(monkeypatch_sensitive),
            "deletion_test_present": deletion_test_present,
            "split_module_present": split_module_present,
            "facade_reexport_present": facade_reexport_present,
        },
        "caller_import_map": reference_rows,
        "monkeypatch_sensitive_files": monkeypatch_sensitive,
        "blockers": sorted(set(blockers)),
        "required_evidence": [
            "duplicated signal-construction block that can be deleted",
            "deletion test proving the split removes real duplication or improves injection",
            "route-decider compatibility rollback path",
        ],
        "next_action": (
            "Do not split yet; collect_route_signals currently has one implementation and no deletion test proves value."
            if decision != "APPROVED"
            else "Signal collector split is approved; keep route_decider as compatibility facade."
        ),
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Signal Collector split pregate.")
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = build_signal_collector_split_pregate(repo_root=args.repo_root)
    _write_json(args.output, report)
    print(json.dumps({"output": args.output.as_posix(), **report["summary"], "decision": report["decision"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
