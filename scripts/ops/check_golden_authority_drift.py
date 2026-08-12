#!/usr/bin/env python3
"""Fail-closed, read-only Golden authority drift checker."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = "tests/golden_behavior/corpus.py"
DISPOSITIONS_SCHEMA = "nexus.golden_authority_dispositions.v1"
REPORT_SCHEMA = "nexus.golden_authority_drift.v1"
DISPOSITIONS = {"MAPPING_UPDATED", "FINDING_UPDATED", "NO_GOLDEN_IMPACT"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class CaseSnapshot:
    case_id: str
    status: str
    authority_sources: tuple[str, ...]
    automated_tests: tuple[str, ...]
    finding_probe: str | None
    finding_id: str | None


@dataclass(frozen=True)
class CorpusSnapshot:
    cases: dict[str, CaseSnapshot]
    findings: dict[str, str]


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)


def _resolve_ref(root: Path, ref: str) -> str:
    result = _git(root, "rev-parse", "--verify", f"{ref}^{{commit}}")
    value = result.stdout.strip()
    return value if result.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", value) else ""


def _git_bytes(root: Path, revision: str, path: str) -> bytes | None:
    result = subprocess.run(
        ["git", "show", f"{revision}:{path}"], cwd=root, capture_output=True, check=False
    )
    return result.stdout if result.returncode == 0 else None


def _literal(node: ast.AST, names: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.Tuple, ast.List)):
        return tuple(_literal(item, names) for item in node.elts)
    if isinstance(node, ast.Dict):
        return {
            _literal(key, names): _literal(value, names)
            for key, value in zip(node.keys, node.values, strict=True)
        }
    if isinstance(node, ast.Name) and node.id in names:
        return names[node.id]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _literal(node.left, names)
        right = _literal(node.right, names)
        if isinstance(left, tuple) and isinstance(right, tuple):
            return left + right
    raise ValueError("corpus_contains_dynamic_expression")


def _load_corpus(root: Path, revision: str) -> CorpusSnapshot:
    """Parse the repository-owned literal corpus without executing it."""
    source = _git_bytes(root, revision, CORPUS_PATH)
    if source is None:
        raise ValueError("corpus_unavailable")
    try:
        tree = ast.parse(source.decode("utf-8"), filename=CORPUS_PATH)
    except (SyntaxError, UnicodeDecodeError) as exc:
        raise ValueError("corpus_unavailable_or_malformed") from exc
    names: dict[str, Any] = {}
    case_nodes: list[ast.Call] = []
    findings: dict[str, str] = {}
    for statement in tree.body:
        target: ast.AST | None = None
        value: ast.AST | None = None
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target, value = statement.targets[0], statement.value
        elif isinstance(statement, ast.AnnAssign):
            target, value = statement.target, statement.value
        if not isinstance(target, ast.Name) or value is None:
            continue
        if target.id == "CASES" and isinstance(value, ast.Tuple):
            if not all(isinstance(item, ast.Call) for item in value.elts):
                raise ValueError("corpus_cases_not_literal_calls")
            case_nodes = list(value.elts)
        elif target.id == "FINDINGS":
            parsed = _literal(value, names)
            if not isinstance(parsed, dict):
                raise ValueError("corpus_findings_invalid")
            findings = parsed
        else:
            try:
                names[target.id] = _literal(value, names)
            except ValueError:
                continue
    cases: dict[str, CaseSnapshot] = {}
    for call in case_nodes:
        if not isinstance(call.func, ast.Name) or call.func.id != "_c" or len(call.args) < 6:
            raise ValueError("corpus_case_call_invalid")
        args = [_literal(arg, names) for arg in call.args]
        kwargs = {item.arg: _literal(item.value, names) for item in call.keywords if item.arg}
        case_id = args[0]
        if not isinstance(case_id, str):
            raise ValueError("corpus_case_id_invalid")
        if case_id in cases:
            raise ValueError(f"duplicate_case_id:{case_id}")
        cases[case_id] = CaseSnapshot(
            case_id=case_id,
            status=kwargs.get("status", "covered"),
            authority_sources=tuple(args[5]),
            automated_tests=tuple(args[6]) if len(args) > 6 else (),
            finding_probe=kwargs.get("finding_probe"),
            finding_id=kwargs.get("finding_id"),
        )
    if not cases:
        raise ValueError("corpus_cases_unavailable")
    return CorpusSnapshot(cases=cases, findings=findings)


def _local_source(source: str) -> str | None:
    if source.startswith(("https://", "http://")):
        return None
    if "://" in source:
        raise ValueError(f"unsupported_authority_url:{source}")
    raw = source.split("#", 1)[0]
    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or ".." in path.parts or "\\" in raw:
        raise ValueError(f"unsafe_authority_path:{source}")
    return path.as_posix()


def _fingerprint(root: Path, revision: str, case: CaseSnapshot) -> str:
    rows: list[dict[str, str]] = []
    for source in sorted(case.authority_sources):
        local = _local_source(source)
        if local is None:
            rows.append({"source": source, "kind": "external", "sha256": ""})
            continue
        content = _git_bytes(root, revision, local)
        if content is None:
            raise ValueError(f"missing_authority_path:{source}")
        rows.append({
            "source": source,
            "kind": "local",
            "sha256": hashlib.sha256(content).hexdigest(),
        })
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def _changed_paths(root: Path, base: str, head: str) -> list[str]:
    result = _git(root, "diff", "--name-only", "--diff-filter=ACMRT", f"{base}..{head}")
    if result.returncode != 0:
        raise ValueError("changed_paths_unavailable")
    return sorted({line for line in result.stdout.splitlines() if line})


def _load_dispositions(path: Path) -> dict[str, Any]:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate_json_key:{key}")
            value[key] = item
        return value

    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("duplicate_json_key:"):
            raise
        raise ValueError("dispositions_unavailable_or_malformed") from exc
    if not isinstance(value, dict) or value.get("schema") != DISPOSITIONS_SCHEMA:
        raise ValueError("dispositions_schema_invalid")
    if not isinstance(value.get("cases"), dict):
        raise ValueError("dispositions_cases_invalid")
    return value


def check_golden_authority_drift(
    *,
    base_ref: str,
    head_ref: str,
    dispositions_path: Path,
    root: Path = ROOT,
) -> dict[str, Any]:
    errors: list[str] = []
    base = _resolve_ref(root, base_ref)
    head = _resolve_ref(root, head_ref)
    if not base:
        errors.append("base_revision_unavailable")
    if not head:
        errors.append("head_revision_unavailable")
    try:
        dispositions = _load_dispositions(dispositions_path)
    except ValueError as exc:
        dispositions = {"cases": {}}
        errors.append(str(exc))
    if base and dispositions.get("base_revision") != base:
        errors.append("base_revision_mismatch")
    if head and dispositions.get("head_revision") != head:
        errors.append("head_revision_mismatch")

    paths: list[str] = []
    corpus = CorpusSnapshot(cases={}, findings={})
    current_fingerprints: dict[str, str] = {}
    affected: list[str] = []
    if head:
        try:
            corpus = _load_corpus(root, head)
            paths = _changed_paths(root, base, head)
            local_by_case: dict[str, set[str]] = {}
            for case_id, case in corpus.cases.items():
                if case.status == "finding" and (
                    not case.finding_id or case.finding_id not in corpus.findings
                ):
                    errors.append(f"{case_id}:finding_identity_unbound")
                if case.status == "covered" and case.finding_id:
                    errors.append(f"{case_id}:covered_case_has_finding_identity")
                local_by_case[case_id] = set()
                for source in case.authority_sources:
                    try:
                        local = _local_source(source)
                    except ValueError as exc:
                        errors.append(f"{case_id}:{exc}")
                        continue
                    if local:
                        local_by_case[case_id].add(local)
                try:
                    current_fingerprints[case_id] = _fingerprint(root, head, case)
                except ValueError as exc:
                    errors.append(f"{case_id}:{exc}")
            affected = sorted(
                case_id for case_id, sources in local_by_case.items() if sources.intersection(paths)
            )
        except ValueError as exc:
            errors.append(str(exc))

    supplied = dispositions.get("cases", {})
    extra = sorted(set(supplied) - set(affected))
    errors.extend(f"{case_id}:unexpected_disposition" for case_id in extra)
    for case_id in affected:
        row = supplied.get(case_id)
        if not isinstance(row, dict):
            errors.append(f"{case_id}:missing_disposition")
            continue
        disposition = row.get("disposition")
        if disposition not in DISPOSITIONS:
            errors.append(f"{case_id}:invalid_disposition")
        fingerprint = row.get("source_fingerprint")
        if not isinstance(fingerprint, str) or not HEX64.fullmatch(fingerprint):
            errors.append(f"{case_id}:invalid_source_fingerprint")
        elif fingerprint != current_fingerprints.get(case_id):
            errors.append(f"{case_id}:stale_source_fingerprint")
        if disposition == "NO_GOLDEN_IMPACT":
            rationale = row.get("rationale")
            if not isinstance(rationale, str) or len(rationale.strip()) < 24:
                errors.append(f"{case_id}:invalid_no_golden_impact_rationale")
        case = corpus.cases.get(case_id)
        if disposition == "MAPPING_UPDATED" and case and case.status == "finding":
            errors.append(f"{case_id}:mapping_cannot_promote_finding")
        if disposition == "FINDING_UPDATED" and case and case.status != "finding":
            errors.append(f"{case_id}:finding_disposition_for_covered_case")
        if disposition == "FINDING_UPDATED" and case:
            if row.get("finding_id") != case.finding_id:
                errors.append(f"{case_id}:finding_identity_mismatch")

    return {
        "schema": REPORT_SCHEMA,
        "status": "FAIL_CLOSED" if errors else "PASS",
        "base_revision": base or None,
        "head_revision": head or None,
        "changed_paths": paths,
        "affected_cases": affected,
        "current_case_fingerprints": dict(sorted(current_fingerprints.items())),
        "errors": sorted(set(errors)),
        "claim_ceiling": "AUTHORITY_DRIFT_DETECTED_ONLY",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--head-ref", default="HEAD")
    parser.add_argument("--dispositions", required=True, type=Path)
    args = parser.parse_args()
    result = check_golden_authority_drift(
        base_ref=args.base_ref,
        head_ref=args.head_ref,
        dispositions_path=args.dispositions,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
