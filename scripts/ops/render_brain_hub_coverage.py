#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from scripts.ops.brain_hub_audit import scan_brain_hub


def _classify_doc(doc: Any, failures: list[dict[str, Any]]) -> str:
    doc_failures = [item for item in failures if item.get("path") == doc.path]
    if any(item.get("reason") == "production_status_without_runtime_reference" for item in doc_failures):
        return "contradicted"
    if str(doc.manifest_status).lower() in {"reference", "north-star", "north_star"}:
        return "reference"
    if doc.runtime_refs and doc.test_refs and not doc_failures:
        return "implemented"
    return "partial"


def build_coverage(repo_root: Path, *, manifest: Path) -> dict[str, Any]:
    audit = scan_brain_hub(repo_root, [], manifest_path=manifest)
    docs = []
    for doc in audit.documents:
        docs.append({**asdict(doc), "coverage_status": _classify_doc(doc, audit.failures)})
    counts: dict[str, int] = {}
    for doc in docs:
        counts[doc["coverage_status"]] = counts.get(doc["coverage_status"], 0) + 1
    return {
        "schema_version": "nexus_brain_hub_coverage.v1",
        "audit_passed": audit.passed,
        "document_count": len(docs),
        "status_counts": counts,
        "documents": docs,
        "failures": audit.failures,
    }


def validate_coverage_gate(payload: dict[str, Any]) -> dict[str, Any]:
    counts = payload.get("status_counts", {}) if isinstance(payload.get("status_counts"), dict) else {}
    failures: list[str] = []
    if int(counts.get("implemented", 0)) <= 0:
        failures.append("implemented_coverage_missing")
    if int(counts.get("contradicted", 0)) > 0:
        failures.append("contradicted_coverage_present")
    if not payload.get("audit_passed"):
        failures.append("brain_hub_audit_failed")
    return {
        "schema_version": "nexus_brain_hub_coverage_gate.v1",
        "passed": not failures,
        "status_counts": counts,
        "failures": failures,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Brain Hub Code-Reality Coverage",
        "",
        f"- schema: `{payload['schema_version']}`",
        f"- audit_passed: `{str(payload['audit_passed']).lower()}`",
        f"- document_count: `{payload['document_count']}`",
        "",
        "## Status Counts",
        "",
    ]
    for status, count in sorted(payload["status_counts"].items()):
        lines.append(f"- `{status}`: {count}")
    lines.extend(["", "## Documents", ""])
    for doc in payload["documents"]:
        refs = ", ".join(doc.get("runtime_refs", [])[:3]) or "none"
        lines.append(f"- `{doc['coverage_status']}` `{doc['path']}` runtime_refs: {refs}")
    if payload["failures"]:
        lines.extend(["", "## Failures", ""])
        for failure in payload["failures"]:
            lines.append(f"- `{failure.get('reason')}` {failure.get('path', '')}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render Brain Hub code-reality coverage report.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--manifest", default="docs/ops/brain_hub_manifest.json")
    parser.add_argument("--output", default=".nexus/reports/brain_hub_coverage.md")
    parser.add_argument("--output-json", action="store_true", help="Compatibility flag; this command always emits JSON.")
    args = parser.parse_args(argv)
    root = Path(args.repo_root).resolve()
    payload = build_coverage(root, manifest=root / args.manifest)
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown(payload), encoding="utf-8")
    gate = validate_coverage_gate(payload)
    print(json.dumps({"passed": gate["passed"], "output": str(output), "status_counts": payload["status_counts"], "failures": gate["failures"]}, indent=2))
    return 0 if gate["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
