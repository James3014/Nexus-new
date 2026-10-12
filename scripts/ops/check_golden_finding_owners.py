#!/usr/bin/env python3
"""Read-only freshness report for Golden finding owner Issues.

Each ``status="finding"`` case in the Golden corpus names its owner GitHub
Issues through issue URLs in ``authority_sources`` and through issue URLs or
``#N`` references in its ``FINDINGS`` text.  This script parses the corpus as
literal AST (it never imports or executes it), observes each owner Issue's
state through an injectable fetcher, and flags findings whose owner Issues are
all closed so they can be re-adjudicated.  It never edits the corpus, never
promotes a finding, and never mutates GitHub.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = "tests/golden_behavior/corpus.py"
REPORT_SCHEMA = "nexus.golden_finding_owners.v1"
REPOSITORY = "James3014/Nexus-new"
FLAG_OWNER_CLOSED = "OWNER_CLOSED_FINDING_OPEN"
FLAG_OWNER_UNKNOWN = "OWNER_STATE_UNKNOWN"
ISSUE_URL = re.compile(r"https://github\.com/James3014/Nexus-new/issues/(\d+)\b")
ISSUE_REF = re.compile(r"(?<![\w/&])#(\d+)\b")

Fetcher = Callable[[int], Mapping[str, Any]]


def _literal(node: ast.AST, names: Mapping[str, Any]) -> Any:
    if isinstance(node, ast.Name):
        if node.id in names:
            return names[node.id]
        raise ValueError(f"corpus_unresolved_name:{node.id}")
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _literal(node.left, names) + _literal(node.right, names)
    if isinstance(node, (ast.Tuple, ast.List)):
        return tuple(_literal(item, names) for item in node.elts)
    return ast.literal_eval(node)


def load_findings(corpus_path: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Return finding cases and the FINDINGS map from the literal corpus."""
    tree = ast.parse(corpus_path.read_text(encoding="utf-8"), filename=str(corpus_path))
    names: dict[str, Any] = {}
    case_nodes: list[ast.AST] = []
    findings: dict[str, str] = {}
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target, value = statement.targets[0], statement.value
        elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
            target, value = statement.target, statement.value
        else:
            continue
        if not isinstance(target, ast.Name):
            continue
        if target.id == "CASES" and isinstance(value, ast.Tuple):
            case_nodes = list(value.elts)
        elif target.id == "FINDINGS":
            parsed = _literal(value, names)
            if not isinstance(parsed, dict) or not all(
                isinstance(key, str) and isinstance(item, str) for key, item in parsed.items()
            ):
                raise ValueError("corpus_findings_invalid")
            findings = parsed
        else:
            try:
                names[target.id] = _literal(value, names)
            except (ValueError, TypeError, SyntaxError):
                continue
    cases: list[dict[str, Any]] = []
    for node in case_nodes:
        if (
            not isinstance(node, ast.Call)
            or not isinstance(node.func, ast.Name)
            or node.func.id != "_c"
            or len(node.args) < 6
        ):
            raise ValueError("corpus_case_call_invalid")
        kwargs = {item.arg: _literal(item.value, names) for item in node.keywords if item.arg}
        if kwargs.get("status", "covered") != "finding":
            continue
        cases.append({
            "case_id": _literal(node.args[0], names),
            "finding_id": kwargs.get("finding_id"),
            "authority_sources": tuple(_literal(node.args[5], names)),
        })
    if not case_nodes:
        raise ValueError("corpus_cases_unavailable")
    return cases, findings


def owner_issues(case: Mapping[str, Any], findings: Mapping[str, str]) -> list[int]:
    numbers: set[int] = set()
    for source in case["authority_sources"]:
        numbers.update(int(match) for match in ISSUE_URL.findall(source))
    text = findings.get(str(case.get("finding_id")), "")
    numbers.update(int(match) for match in ISSUE_URL.findall(text))
    numbers.update(int(match) for match in ISSUE_REF.findall(text))
    return sorted(numbers)


def gh_fetcher(number: int) -> Mapping[str, Any]:
    completed = subprocess.run(
        [
            "gh",
            "issue",
            "view",
            str(number),
            "-R",
            REPOSITORY,
            "--json",
            "state,stateReason,closedAt",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip()[-400:] or "gh issue view failed")
    return json.loads(completed.stdout)


def _observe(number: int, fetcher: Fetcher) -> dict[str, Any]:
    try:
        raw = fetcher(number)
    except Exception as exc:  # noqa: BLE001 - any observer failure is UNKNOWN
        return {"number": number, "state": "UNKNOWN", "error": str(exc) or type(exc).__name__}
    state = str(raw.get("state") or "").upper()
    if state not in {"OPEN", "CLOSED"}:
        return {"number": number, "state": "UNKNOWN", "error": "unrecognized_state"}
    return {
        "number": number,
        "state": state,
        "stateReason": raw.get("stateReason") or None,
        "closedAt": raw.get("closedAt") or None,
    }


def build_report(corpus_path: Path, fetcher: Fetcher = gh_fetcher) -> dict[str, Any]:
    cases, findings = load_findings(corpus_path)
    cache: dict[int, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    for case in cases:
        issues = []
        for number in owner_issues(case, findings):
            if number not in cache:
                cache[number] = _observe(number, fetcher)
            issues.append(cache[number])
        flags: list[str] = []
        if any(issue["state"] == "UNKNOWN" for issue in issues):
            flags.append(FLAG_OWNER_UNKNOWN)
        elif issues and all(issue["state"] == "CLOSED" for issue in issues):
            flags.append(FLAG_OWNER_CLOSED)
        rows.append({
            "case_id": case["case_id"],
            "finding_id": case["finding_id"],
            "owner_issues": issues,
            "flags": flags,
        })
    return {
        "schema": REPORT_SCHEMA,
        "repository": REPOSITORY,
        "corpus_path": CORPUS_PATH,
        "findings": rows,
        "flagged": [row["case_id"] for row in rows if row["flags"]],
        "claim_ceiling": "OWNER_STATE_OBSERVATION_ONLY",
    }


def main(argv: list[str] | None = None, *, fetcher: Fetcher = gh_fetcher) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, default=ROOT / CORPUS_PATH)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 when any finding is flagged (owner closed or owner state unknown)",
    )
    args = parser.parse_args(argv)
    try:
        report = build_report(args.corpus, fetcher)
    except (OSError, ValueError, SyntaxError) as exc:
        print(json.dumps({"schema": REPORT_SCHEMA, "error": str(exc)}, sort_keys=True))
        return 1 if args.strict else 0
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if args.strict and report["flagged"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
