#!/usr/bin/env python3
"""Run the blocking Wiki CI/release gates and emit a commit-bound receipt.

The command is the single operator entrypoint for Phase 8.  It never treats a
warning debt item as a critical pass, and it writes a receipt even when a
critical gate blocks so CI has machine-readable failure evidence.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


SCHEMA = "nexus.wiki.ci-release-governance-receipt.v1"
EVIDENCE_SCHEMA = "nexus.wiki.ci-release-governance-evidence.v1"
CURRENT_CLASSES = {"current", "active", "current_verified", "current_needs_review"}
GENERATED_DIR = Path("nexus_wiki_vault/99_Schema/generated")
ARTIFACTS = (
    "agent-index.json",
    "wikilink-graph.json",
    "llms.txt",
    "unresolved-link-inventory.json",
    "content-freshness-audit.json",
    "governance-closure-receipt.json",
)
AUDIT_READ_ONLY_ENV = {
    "NEXUS_AUDIT_READ_ONLY": "1",
    "NEXUS_LEARN_CLOSURE_WRITEBACK": "0",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_command(repo_root: Path, argv: list[str], *, timeout: int = 180) -> dict[str, Any]:
    try:
        result = subprocess.run(
            argv,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "command": argv,
            "status": "BLOCK",
            "exit_code": 124,
            "stdout": str(exc.stdout or ""),
            "stderr": f"timeout after {timeout}s",
        }
    except OSError as exc:
        return {
            "command": argv,
            "status": "BLOCK",
            "exit_code": 127,
            "stdout": "",
            "stderr": str(exc),
        }
    return {
        "command": argv,
        "status": "PASS" if result.returncode == 0 else "BLOCK",
        "exit_code": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


def _gate_from_command(repo_root: Path, name: str, argv: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    evidence = _run_command(repo_root, argv)
    return {"name": name, "status": evidence["status"], "reason": "" if evidence["status"] == "PASS" else "command_failed"}, evidence


def _artifact_identity(repo_root: Path) -> tuple[dict[str, str], str, list[str]]:
    generated = repo_root / GENERATED_DIR
    hashes: dict[str, str] = {}
    missing: list[str] = []
    for name in ARTIFACTS:
        path = generated / name
        if path.is_file():
            hashes[name] = _sha256(path)
        else:
            missing.append(name)

    fingerprints: list[str] = []
    for name in ("agent-index.json", "wikilink-graph.json", "unresolved-link-inventory.json"):
        path = generated / name
        if not path.is_file():
            continue
        try:
            fingerprints.append(str(json.loads(path.read_text(encoding="utf-8")).get("source_fingerprint") or ""))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            fingerprints.append("")
    source_fingerprint = fingerprints[0] if fingerprints and fingerprints[0] else ""
    if not source_fingerprint or any(value != source_fingerprint for value in fingerprints):
        missing.append("source_fingerprint_identity")
    return hashes, source_fingerprint, sorted(set(missing))


def _coverage_metrics(repo_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    from scripts.ops import wiki_coverage_audit as coverage

    original_root, original_vault = coverage.REPO_ROOT, coverage.VAULT_ROOT
    coverage.REPO_ROOT = repo_root
    coverage.VAULT_ROOT = repo_root / "nexus_wiki_vault"
    try:
        report = coverage.formal_mapping_report(
            coverage.get_symbol_inventory(), coverage.load_authority_manifest()
        )
    finally:
        coverage.REPO_ROOT, coverage.VAULT_ROOT = original_root, original_vault
    gate = {
        "name": "wiki_coverage",
        "status": "PASS" if report.get("status") == "PASS" else "BLOCK",
        "reason": "" if report.get("status") == "PASS" else "coverage_policy_failed",
    }
    return gate, {
        "eligible_symbols": report.get("eligible_symbols", 0),
        "mapped_symbols": report.get("mapped_symbols", 0),
        "coverage_ratio": report.get("coverage_ratio", "0.00%"),
        "threshold": report.get("threshold", 0.85),
        "priority_scope_stats": report.get("priority_scope_stats", {}),
        "wave_stats": report.get("wave_stats", {}),
    }


def _authority_metrics(repo_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    from scripts.ops import wiki_capability_coverage_audit as authority

    original_root, original_vault, original_manifest = (
        authority.REPO_ROOT,
        authority.VAULT_ROOT,
        authority.AUTHORITY_MANIFEST_PATH,
    )
    authority.REPO_ROOT = repo_root
    authority.VAULT_ROOT = repo_root / "nexus_wiki_vault"
    authority.AUTHORITY_MANIFEST_PATH = authority.VAULT_ROOT / "99_Schema" / "WIKI_AUTHORITY_MANIFEST.yaml"
    try:
        report = authority.audit_capabilities(stale_days=45)
    finally:
        authority.REPO_ROOT, authority.VAULT_ROOT, authority.AUTHORITY_MANIFEST_PATH = original_root, original_vault, original_manifest
    checks = report.get("authority_checks", {})
    missing = list(checks.get("missing", [])) + list(checks.get("invalid", []))
    gate = {
        "name": "wiki_required_authority_labels",
        "status": "PASS" if checks.get("status") == "PASS" and not missing else "BLOCK",
        "reason": "" if checks.get("status") == "PASS" and not missing else "required_authority_missing_or_invalid",
    }
    return gate, {
        "required_count": checks.get("required_count", 0),
        "resolved_count": checks.get("resolved_count", 0),
        "missing": missing,
        "duplicate_labels": checks.get("duplicate_labels", []),
    }


def _freshness_metrics(repo_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    from scripts.ops import wiki_content_freshness_audit as freshness

    report = freshness.build_report(repo_root, repo_root / "nexus_wiki_vault", run_commands=True)
    source_path_errors: list[str] = []
    for page in report.get("pages", []):
        if page.get("classification") not in {"current_verified", "current_needs_review"}:
            continue
        for source in page.get("source_paths", []):
            if not source.get("exists"):
                source_path_errors.append(f"{page.get('path')}:{source.get('path')}")
    gate = {
        "name": "wiki_current_authority_source_paths",
        "status": "PASS" if report.get("status") == "PASS" and not source_path_errors else "BLOCK",
        "reason": "" if report.get("status") == "PASS" and not source_path_errors else "stale_or_missing_current_authority_source",
    }
    return gate, {
        "source_fingerprint": report.get("source_fingerprint", ""),
        "classification_counts": report.get("summary", {}).get("classification_counts", {}),
        "error_count": report.get("summary", {}).get("error_count", 0),
        "missing_source_paths": source_path_errors,
    }


def _current_link_metrics(repo_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    inventory_path = repo_root / GENERATED_DIR / "unresolved-link-inventory.json"
    try:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return (
            {"name": "wiki_current_authority_links", "status": "BLOCK", "reason": "unresolved_inventory_unreadable"},
            {"current_unresolved": 0, "unexplained": ["unresolved_inventory_unreadable"]},
        )

    current = [
        entry for entry in inventory.get("entries", [])
        if str(entry.get("source_classification", "")).lower() in CURRENT_CLASSES
    ]
    unexplained: list[str] = []
    for entry in current:
        governance = entry.get("governance") or {}
        if (
            governance.get("status") != "governed"
            or not governance.get("disposition")
            or not governance.get("owner")
            or not governance.get("policy")
            or entry.get("repairable")
            or entry.get("category") in {"ambiguous", "unsupported"}
        ):
            unexplained.append(f"{entry.get('source_path')}:{entry.get('raw_target')}")
    gate = {
        "name": "wiki_current_authority_links",
        "status": "PASS" if not unexplained else "BLOCK",
        "reason": "" if not unexplained else "unexplained_current_authority_link_debt",
    }
    return gate, {
        "current_unresolved": len(current),
        "unexplained": unexplained,
        "disposition_counts": inventory.get("governance_summary", {}).get("by_disposition", {}),
    }


def _runtime_metrics(repo_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    from nexus.services.wiki_knowledge_agent import verify_runtime_integration

    passed, blockers = verify_runtime_integration(repo_root)
    return (
        {"name": "knowledge_agent_runtime_integration", "status": "PASS" if passed else "BLOCK", "reason": ",".join(blockers)},
        {"status": "PASS" if passed else "RETURN", "blockers": blockers},
    )


def _audit_copy_ignore(directory: str, names: list[str]) -> set[str]:
    ignored = {".git", ".venv", "__pycache__", ".pytest_cache", ".antigravitycli"}
    ignored.update(name for name in names if (Path(directory) / name).is_symlink())
    return ignored.intersection(names)


def _truth_claims_metrics(repo_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    configured_report_path = os.environ.get("NEXUS_TRUTH_CLAIMS_REPORT_PATH", "").strip()
    report_path = Path(configured_report_path).resolve() if configured_report_path else repo_root / ".nexus" / "reports" / "wiki_truth_claims_report.json"
    report_runner = (
        "import pathlib, sys; "
        "from scripts.ops import wiki_truth_claims_check as checker; "
        "checker.REPO_ROOT = pathlib.Path(sys.argv[2]).resolve(); "
        "checker.VAULT_ROOT = checker.REPO_ROOT / 'nexus_wiki_vault'; "
        "checker.REPORT_PATH = pathlib.Path(sys.argv[1]).resolve(); "
        "_run = checker.subprocess.run; "
        "_isolated = pathlib.Path(sys.argv[3]).resolve(); "
        "checker.subprocess.run = lambda command, *args, **kwargs: _run(command, *args, **(dict(kwargs, cwd=_isolated) if isinstance(command, str) and command.startswith('uv run ') else kwargs)); "
        "summary = checker.run_checks(); "
        "raise SystemExit(0 if summary and summary.get('status') == 'PASS' else 1)"
    )
    with tempfile.TemporaryDirectory(prefix="nexus-wiki-truth-") as temp_dir:
        execution_root = Path(temp_dir) / "repo"
        shutil.copytree(repo_root, execution_root, ignore=_audit_copy_ignore)
        execution = _run_command(
            execution_root,
            [sys.executable, "-c", report_runner, str(report_path), str(repo_root), str(execution_root)],
        )
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        summary = report.get("summary") or {}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return (
            {"name": "wiki_truth_claims", "status": "BLOCK", "reason": "truth_claims_report_unreadable"},
            {"error": str(exc), "execution": execution},
        )

    mismatch_count = int(summary.get("mismatch_count", 0) or 0)
    infra_error_count = int(summary.get("infra_error_count", 0) or 0)
    policy_violation_count = int(summary.get("policy_violation_count", 0) or 0)
    passed = (
        execution.get("status") == "PASS"
        and summary.get("status") == "PASS"
        and mismatch_count == 0
        and infra_error_count == 0
        and policy_violation_count == 0
    )
    reason = "" if passed else "truth_claims_mismatch_or_environment_failure"
    return (
        {"name": "wiki_truth_claims", "status": "PASS" if passed else "BLOCK", "reason": reason},
        {
            "total_claims": summary.get("total_claims", 0),
            "mismatch_count": mismatch_count,
            "infra_error_count": infra_error_count,
            "policy_violation_count": policy_violation_count,
            "blocked_claim_ids": summary.get("blocked_claim_ids", []),
            "environment_claim_ids": summary.get("environment_claim_ids", []),
            "report_path": str(report_path.resolve()),
            "execution": execution,
        },
    )


def _safe_metric(name: str, function, repo_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        return function(repo_root)
    except Exception as exc:  # fail closed while preserving a machine receipt
        return (
            {"name": name, "status": "BLOCK", "reason": f"exception:{type(exc).__name__}"},
            {"error": str(exc)},
        )


@contextmanager
def _audit_read_only_environment(output_dir: Path):
    keys = {**AUDIT_READ_ONLY_ENV, "NEXUS_TRUTH_CLAIMS_REPORT_PATH": str(output_dir / "wiki_truth_claims_report.json")}
    previous = {key: os.environ.get(key) for key in keys}
    try:
        os.environ.update(keys)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def run_gate(repo_root: Path, output_dir: Path) -> dict[str, Any]:
    with _audit_read_only_environment(output_dir):
        return _run_gate_impl(repo_root, output_dir)


def _run_gate_impl(repo_root: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    python = sys.executable
    commands = [
        ("wiki_index_deterministic", [python, "scripts/ops/build_wiki_agent_index.py", "--check"]),
        ("wiki_classifier_full_identity", [python, "scripts/ops/classify_wiki_unresolved_links.py", "--check"]),
        ("wiki_governance_closure", [python, "scripts/ops/check_wiki_governance_closure.py", "--check"]),
        ("wiki_committed_tree_reproducibility", [python, "scripts/ops/check_wiki_committed_reproducibility.py", "--check", "--repo-root", str(repo_root), "--ref", "HEAD"]),
        ("wiki_content_freshness_artifact", [python, "scripts/ops/wiki_content_freshness_audit.py", "--check", "--repo-root", str(repo_root)]),
    ]
    gates: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    for name, argv in commands:
        gate, execution = _gate_from_command(repo_root, name, argv)
        gates.append(gate)
        evidence.append(execution)

    hashes, source_fingerprint, identity_errors = _artifact_identity(repo_root)
    gates.append({"name": "wiki_artifact_identity", "status": "PASS" if not identity_errors else "BLOCK", "reason": ",".join(identity_errors)})
    authority_gate, authority_metrics = _safe_metric("wiki_required_authority_labels", _authority_metrics, repo_root)
    coverage_gate, coverage_metrics = _safe_metric("wiki_coverage", _coverage_metrics, repo_root)
    freshness_gate, freshness_metrics = _safe_metric("wiki_current_authority_source_paths", _freshness_metrics, repo_root)
    links_gate, links_metrics = _safe_metric("wiki_current_authority_links", _current_link_metrics, repo_root)
    runtime_gate, runtime_metrics = _safe_metric("knowledge_agent_runtime_integration", _runtime_metrics, repo_root)
    truth_claims_gate, truth_claims_metrics = _safe_metric("wiki_truth_claims", _truth_claims_metrics, repo_root)
    gates.extend([authority_gate, coverage_gate, freshness_gate, links_gate, runtime_gate, truth_claims_gate])

    inventory_path = repo_root / GENERATED_DIR / "unresolved-link-inventory.json"
    try:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        disposition_counts = inventory.get("governance_summary", {}).get("by_disposition", {})
        category_counts = inventory.get("category_counts", {})
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        disposition_counts, category_counts = {}, {}

    warnings = [
        {"kind": "accepted_link_debt", "count": sum(disposition_counts.values()) if disposition_counts else 0},
        {"kind": "legacy_or_historical", "count": category_counts.get("legacy_or_historical", 0)},
        {"kind": "intentional_placeholder", "count": category_counts.get("placeholder_or_template", 0)},
    ]
    evidence_path = (output_dir / "wiki-ci-release-governance-evidence.json").resolve()
    receipt_path = (output_dir / "wiki-ci-release-governance-receipt.json").resolve()
    evidence_payload = {
        "schema": EVIDENCE_SCHEMA,
        "authority": "derived_non_authoritative",
        "owner": "wiki-governance",
        "commit_sha": _git_head(repo_root),
        "commands": evidence,
        "artifact_identity_errors": identity_errors,
        "gate_results": gates,
    }
    evidence_path.write_text(json.dumps(evidence_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    blockers = [f"{gate['name']}:{gate['reason']}" for gate in gates if gate["status"] != "PASS"]
    status = "PASS" if not blockers else "BLOCK"
    receipt = {
        "schema": SCHEMA,
        "purpose": "Phase 8 CI, release, and operational Wiki governance gate",
        "authority": "derived_non_authoritative",
        "owner": "wiki-governance",
        "status": status,
        "commit_sha": evidence_payload["commit_sha"],
        "artifact_hashes": hashes,
        "source_fingerprint": source_fingerprint,
        "coverage_metrics": coverage_metrics,
        "required_authority_metrics": authority_metrics,
        "current_authority_source_metrics": freshness_metrics,
        "current_authority_link_metrics": links_metrics,
        "unresolved_link_disposition_counts": disposition_counts,
        "unresolved_link_category_counts": category_counts,
        "runtime_integration": runtime_metrics,
        "truth_claims_metrics": truth_claims_metrics,
        "critical_gates": gates,
        "warnings": warnings,
        "gate_verdict": status,
        "missing_evidence_reasons": blockers,
        "acceptance_evidence_refs": [
            {"kind": "machine_evidence", "path": str(evidence_path)},
            {"kind": "gate_results", "count": len(gates)},
        ],
        "receipt_path": str(receipt_path),
        "evidence_path": str(evidence_path),
        "claim_boundary": "This is a committed-tree Wiki governance gate, not a production-readiness claim.",
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return receipt


def _git_head(repo_root: Path) -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="run blocking Wiki governance gates")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=Path(".nexus/reports/wiki-governance"))
    args = parser.parse_args(argv)
    if not args.check:
        parser.error("--check is required")
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir if args.output_dir.is_absolute() else repo_root / args.output_dir
    receipt = run_gate(repo_root, output_dir)
    print(f"WIKI_CI_RELEASE_GOVERNANCE_{receipt['gate_verdict']}")
    print(f"receipt_path={receipt['receipt_path']}")
    print(f"evidence_path={receipt['evidence_path']}")
    if receipt["missing_evidence_reasons"]:
        print("blockers=" + ";".join(receipt["missing_evidence_reasons"]))
    return 0 if receipt["gate_verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
