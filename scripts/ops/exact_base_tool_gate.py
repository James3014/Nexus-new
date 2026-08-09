#!/usr/bin/env python3
"""Normalize exact-base tool output and classify head findings fail-closed."""

from __future__ import annotations

import argparse
import json
import os
import posixpath
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

Classification = str


@dataclass(frozen=True)
class Finding:
    """A tool-independent finding with a stable comparison identity."""

    tool: str
    rule_id: str
    path: str
    line: int
    column: int
    severity: str
    message: str

    @property
    def identity(self) -> tuple[str, str, str, str, str]:
        """Stable signature; source coordinates are display-only."""
        return (
            self.tool,
            self.rule_id,
            self.path,
            self.severity,
            " ".join(self.message.split()),
        )


@dataclass(frozen=True)
class FindingClassification:
    classification: Classification
    blocking: bool
    base_findings: list[Finding]
    head_findings: list[Finding]
    new_findings: list[Finding]
    resolved_findings: list[Finding]


def _payload(value: Any) -> Any:
    if isinstance(value, Path):
        value = value.read_text(encoding="utf-8")
    if isinstance(value, str):
        return json.loads(value)
    return value


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _number(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _repo_path(value: Any, root: Path | None) -> str:
    path = (_text(value) or "<unknown>").replace("\\", "/")
    if path == "<unknown>":
        return path
    if root is None:
        normalized = posixpath.normpath(path)
        if normalized == ".." or normalized.startswith("../"):
            raise ValueError(f"finding path escapes evidence root: {path}")
        return normalized
    normalized_root = root.resolve()
    normalized_path = (
        Path(path).resolve() if os.path.isabs(path) else (normalized_root / path).resolve()
    )
    try:
        return normalized_path.relative_to(normalized_root).as_posix()
    except ValueError as exc:
        raise ValueError(f"finding path escapes evidence root: {path}") from exc


def _finding(
    tool: str,
    *,
    rule_id: Any,
    path: Any,
    line: Any = 0,
    column: Any = 0,
    severity: Any = "error",
    message: Any = "",
    root: Path | None = None,
) -> Finding:
    return Finding(
        tool=tool,
        rule_id=_text(rule_id) or "UNKNOWN",
        path=_repo_path(path, root),
        line=_number(line),
        column=_number(column),
        severity=_text(severity).lower() or "unknown",
        message=_text(message),
    )


def _sorted(findings: Iterable[Finding]) -> list[Finding]:
    return sorted(
        findings,
        key=lambda item: (item.tool, item.path, item.line, item.column, item.rule_id, item.message),
    )


def _dict_entries(value: Any, *, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{label} must be a list of objects")
    return value


def parse_ruff_json(value: Any, *, root: Path | None = None) -> list[Finding]:
    """Parse Ruff's JSON list emitted by ``ruff check --output-format json``."""
    payload = _payload(value)
    entries = _dict_entries(payload, label="Ruff JSON")
    for item in entries:
        if not isinstance(item.get("code"), str) or not isinstance(item.get("filename"), str):
            raise ValueError("Ruff finding is missing code or filename")
        if item.get("severity") is not None and not isinstance(item.get("severity"), str):
            raise ValueError("Ruff finding severity must be a string")
        if item.get("message") is not None and not isinstance(item.get("message"), str):
            raise ValueError("Ruff finding message must be a string or null")
        if not isinstance(item.get("location"), dict):
            raise ValueError("Ruff finding is missing location")
        location = item["location"]
        if type(location.get("row")) is not int or type(location.get("column")) is not int:
            raise ValueError("Ruff finding location must contain integer row and column")
    return _sorted(
        _finding(
            "ruff",
            rule_id=item.get("code"),
            path=item.get("filename"),
            line=(item.get("location") or {}).get("row", 0),
            column=(item.get("location") or {}).get("column", 0),
            severity=item.get("severity", "error"),
            message=item.get("message"),
            root=root,
        )
        for item in entries
    )


def parse_pyright_json(value: Any, *, root: Path | None = None) -> list[Finding]:
    """Parse Pyright's JSON ``generalDiagnostics`` payload."""
    payload = _payload(value)
    if not isinstance(payload, dict):
        raise ValueError("Pyright JSON must contain generalDiagnostics")
    entries = _dict_entries(payload.get("generalDiagnostics"), label="Pyright generalDiagnostics")
    for item in entries:
        if not isinstance(item.get("file"), str) or not isinstance(item.get("severity"), str):
            raise ValueError("Pyright finding is missing file or severity")
        if item.get("rule") is not None and not isinstance(item.get("rule"), str):
            raise ValueError("Pyright finding rule must be a string or null")
        if item.get("message") is not None and not isinstance(item.get("message"), str):
            raise ValueError("Pyright finding message must be a string or null")
        location = item.get("range")
        start = location.get("start") if isinstance(location, dict) else None
        if (
            not isinstance(start, dict)
            or type(start.get("line")) is not int
            or type(start.get("character")) is not int
        ):
            raise ValueError("Pyright finding range must contain integer start coordinates")
    return _sorted(
        _finding(
            "pyright",
            rule_id=item.get("rule") or item.get("ruleId"),
            path=item.get("file"),
            line=_number((item.get("range") or {}).get("start", {}).get("line")) + 1,
            column=_number((item.get("range") or {}).get("start", {}).get("character")) + 1,
            severity=item.get("severity"),
            message=item.get("message"),
            root=root,
        )
        for item in entries
    )


def parse_bandit_json(value: Any, *, root: Path | None = None) -> list[Finding]:
    """Parse Bandit's JSON ``results`` payload."""
    payload = _payload(value)
    if not isinstance(payload, dict):
        raise ValueError("Bandit JSON must contain results")
    entries = _dict_entries(payload.get("results"), label="Bandit results")
    for item in entries:
        if not isinstance(item.get("filename"), str) or not isinstance(
            item.get("test_id") or item.get("test_name"), str
        ):
            raise ValueError("Bandit finding is missing filename or test id")
        if type(item.get("line_number")) is not int or not isinstance(
            item.get("issue_severity"), str
        ):
            raise ValueError("Bandit finding must contain integer line and string severity")
        if item.get("issue_text") is not None and not isinstance(item.get("issue_text"), str):
            raise ValueError("Bandit finding message must be a string or null")
    return _sorted(
        _finding(
            "bandit",
            rule_id=item.get("test_id") or item.get("test_name"),
            path=item.get("filename"),
            line=item.get("line_number"),
            severity=item.get("issue_severity"),
            message=item.get("issue_text"),
            root=root,
        )
        for item in entries
    )


def parse_wiki_governance_receipt(value: Any, *, root: Path | None = None) -> list[Finding]:
    """Parse governance receipt findings and failed check/violation entries."""
    payload = _payload(value)
    if not isinstance(payload, dict):
        raise ValueError("Wiki governance receipt must be an object")
    status = _text(payload.get("status") or payload.get("gate_verdict")).upper()
    if status not in {"PASS", "BLOCK"}:
        raise ValueError("Wiki governance receipt must declare PASS or BLOCK")
    if not isinstance(payload.get("critical_gates"), list):
        raise ValueError("Wiki governance receipt must contain critical_gates")
    raw_findings: list[dict[str, Any]] = []
    for key in ("findings", "violations", "errors", "warnings"):
        entries = payload.get(key, [])
        raw_findings.extend(_dict_entries(entries, label=f"Wiki {key}"))
    checks = _dict_entries(payload.get("checks", []), label="Wiki checks")
    raw_findings.extend(
        entry
        for entry in checks
        if _text(entry.get("status")).lower() not in {"", "pass", "passed", "ok"}
    )
    critical_gates = _dict_entries(payload.get("critical_gates"), label="Wiki critical_gates")
    raw_findings.extend(
        entry
        for entry in critical_gates
        if _text(entry.get("status")).lower() not in {"", "pass", "passed", "ok"}
    )
    missing_reasons = payload.get("missing_evidence_reasons", [])
    if not isinstance(missing_reasons, list) or any(
        not isinstance(reason, str) for reason in missing_reasons
    ):
        raise ValueError("Wiki missing_evidence_reasons must be a list of strings")
    raw_findings.extend(
        {
            "rule_id": "missing_evidence",
            "message": reason,
            "severity": "error",
            "path": "<receipt>",
        }
        for reason in missing_reasons
        if reason.strip()
    )
    if status not in {"", "PASS", "PASSED", "OK"} and not raw_findings:
        raw_findings.append(
            {
                "rule_id": "receipt_status",
                "path": "<receipt>",
                "severity": "error",
                "message": status,
            }
        )
    return _sorted(
        _finding(
            "wiki-governance",
            rule_id=item.get("rule_id") or item.get("rule") or item.get("id") or item.get("name"),
            path=item.get("path") or item.get("file") or item.get("filename") or "<receipt>",
            line=item.get("line") or item.get("line_number"),
            column=item.get("column"),
            severity=item.get("severity") or item.get("level") or "error",
            message=item.get("message") or item.get("detail") or item.get("reason"),
            root=root,
        )
        for item in raw_findings
        if isinstance(item, dict)
    )


def classify_findings(
    base_findings: Iterable[Finding],
    head_findings: Iterable[Finding],
    *,
    base_valid: bool = True,
    head_valid: bool = True,
) -> FindingClassification:
    """Compare exact-base and exact-head findings; any new identity blocks."""
    ordered_base = _sorted(base_findings)
    ordered_head = _sorted(head_findings)
    base_counts = Counter(finding.identity for finding in ordered_base)
    head_counts = Counter(finding.identity for finding in ordered_head)
    new_counts = head_counts - base_counts
    resolved_counts = base_counts - head_counts
    new = []
    resolved = []
    for finding in ordered_head:
        if new_counts[finding.identity] > 0:
            new.append(finding)
            new_counts[finding.identity] -= 1
    for finding in ordered_base:
        if resolved_counts[finding.identity] > 0:
            resolved.append(finding)
            resolved_counts[finding.identity] -= 1
    if not base_valid or not head_valid:
        classification, blocking = "IMPACT_UNKNOWN", True
    elif new:
        classification, blocking = "NEW_REGRESSION", True
    elif ordered_base or ordered_head:
        classification, blocking = "EXACT_BASELINE_DEBT", False
    else:
        classification, blocking = "PASS", False
    return FindingClassification(
        classification, blocking, ordered_base, ordered_head, new, resolved
    )


def parse_tool_json(tool: str, value: Any, *, root: Path | None = None) -> list[Finding]:
    parsers = {
        "ruff": parse_ruff_json,
        "pyright": parse_pyright_json,
        "bandit": parse_bandit_json,
        "wiki-governance": parse_wiki_governance_receipt,
    }
    try:
        parser = parsers[tool]
    except KeyError as exc:
        raise ValueError(f"unsupported tool: {tool}") from exc
    return parser(value, root=root)


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tool", required=True, choices=("ruff", "pyright", "bandit", "wiki-governance")
    )
    parser.add_argument("--base", "--base-json", dest="base", required=True, type=Path)
    parser.add_argument("--head", "--head-json", dest="head", required=True, type=Path)
    parser.add_argument("--output", "--output-json", dest="output", required=True, type=Path)
    parser.add_argument("--root", type=Path, help="common root for both worktree outputs")
    parser.add_argument("--base-root", type=Path)
    parser.add_argument("--head-root", type=Path)
    parser.add_argument("--base-exit-code", type=int, default=0)
    parser.add_argument("--head-exit-code", type=int, default=0)
    base_valid = parser.add_mutually_exclusive_group()
    base_valid.add_argument("--base-valid", dest="base_valid", action="store_true")
    base_valid.add_argument("--base-invalid", dest="base_valid", action="store_false")
    head_valid = parser.add_mutually_exclusive_group()
    head_valid.add_argument("--head-valid", dest="head_valid", action="store_true")
    head_valid.add_argument("--head-invalid", dest="head_valid", action="store_false")
    parser.set_defaults(base_valid=True, head_valid=True)
    args = parser.parse_args()
    base_root = args.base_root or args.root
    head_root = args.head_root or args.root
    report: dict[str, Any]
    try:
        if args.base_exit_code not in {0, 1} or args.head_exit_code not in {0, 1}:
            raise RuntimeError("tool execution failed before producing comparable findings")
        base = parse_tool_json(args.tool, args.base, root=base_root)
        head = parse_tool_json(args.tool, args.head, root=head_root)
        result = classify_findings(
            base,
            head,
            base_valid=args.base_valid and (args.base_exit_code == 0 or bool(base)),
            head_valid=args.head_valid and (args.head_exit_code == 0 or bool(head)),
        )
        report = {
            "classification": result.classification,
            "blocking": result.blocking,
            "base_findings": [finding.__dict__ for finding in result.base_findings],
            "head_findings": [finding.__dict__ for finding in result.head_findings],
            "new_findings": [finding.__dict__ for finding in result.new_findings],
            "resolved_findings": [finding.__dict__ for finding in result.resolved_findings],
            "base_exit_code": args.base_exit_code,
            "head_exit_code": args.head_exit_code,
        }
    except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        report = {
            "classification": "CI_BOOTSTRAP_DEFECT",
            "blocking": True,
            "error": f"{type(exc).__name__}: {exc}",
            "base_exit_code": args.base_exit_code,
            "head_exit_code": args.head_exit_code,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 1 if report["classification"] == "NEW_REGRESSION" else 2 if report["blocking"] else 0


if __name__ == "__main__":
    raise SystemExit(_cli())


__all__ = [
    "Finding",
    "FindingClassification",
    "classify_findings",
    "parse_bandit_json",
    "parse_pyright_json",
    "parse_ruff_json",
    "parse_wiki_governance_receipt",
]
