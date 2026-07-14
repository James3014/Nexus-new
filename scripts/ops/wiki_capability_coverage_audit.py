#!/usr/bin/env python3
import os
import re
import json
import argparse
import datetime
import sys
import yaml
from pathlib import Path

# 🛡️ Nexus Wiki Capability Coverage Audit v1.1
# Purpose: Verify that critical system capabilities are documented with evidence, owner, and freshness.

REPO_ROOT = Path(str(__import__("pathlib").Path(__file__).resolve().parents[2]))
VAULT_ROOT = REPO_ROOT / "nexus_wiki_vault"
REPORT_PATH = REPO_ROOT / ".nexus" / "reports" / "wiki_capability_coverage_report.json"
AUTHORITY_MANIFEST_PATH = VAULT_ROOT / "99_Schema" / "WIKI_AUTHORITY_MANIFEST.yaml"

CURRENT_AUTHORITY_CLASSIFICATIONS = {"current", "active"}
LEGACY_PAGE_PREFIXES = (
    "90_Sources/Archive/",
    "90_Sources/Legacy_Wiki/",
    "99_Schema/generated/",
)

CAPABILITY_DOMAINS = {
    "pxdrac_runtime": {
        "required_pages": [
            "03_Flows/Flow - PXDRAC Runtime.md",
            "02_Modules/Module - Core Orchestrator Deep Dive.md",
        ],
        "required_labels": [
            "[code: scripts/engine/nexus_cli.py]",
            "[source: Spec v22]",
        ],
        "risk_weight": 1.0
    },
    "release_governance": {
        "required_pages": [
            "06_Ops/Ops - Acceptance and Release.md",
            "06_Ops/Ops - Wiki Page Type Contracts.md",
        ],
        "required_labels": [
            "[code: scripts/ops/ci_gate.py]",
            "[source: Release Discipline]",
        ],
        "risk_weight": 0.8
    },
    "truth_claims": {
        "required_pages": [
            "06_Ops/Ops - Truth Claims Register.md",
            "06_Ops/Ops - Truth Claims Command Policy.md",
        ],
        "required_labels": [
            "[code: scripts/ops/wiki_truth_claims_check.py]",
        ],
        "risk_weight": 0.9
    },
    "incident_response": {
        "required_pages": [
            "06_Ops/Ops - CI Failure Playbook.md",
            "02_Modules/Module - Dual Phase Diagnosis.md",
        ],
        "required_labels": [
            "[code: scripts/ops/incident_rca_adapter.py]",
        ],
        "risk_weight": 0.7
    },
    "command_surface": {
        "required_pages": [
            "05_Protocols/Protocol - CLI Surface.md",
            "00_Home/Agent Boot Sequence.md",
        ],
        "required_labels": [
            "[code: scripts/engine/nexus_cli.py]",
            "[source: Protocol - CLI Surface]",
        ],
        "risk_weight": 0.6
    }
}

# PROVENANCE_TAG_PATTERN from wiki_linter.py
PROVENANCE_TAG_PATTERN = re.compile(r"\[(source|code):\s*(.*?)\]|\((source|code):\s*(.*?)\)", re.I)
LABEL_PATTERN = re.compile(r"\[(source|code):\s*(.*?)\]", re.I)


def normalize_label(label):
    match = LABEL_PATTERN.fullmatch(str(label).strip())
    if not match:
        return ""
    return f"[{match.group(1).lower()}: {match.group(2).strip().lower()}]"


def _page_classification(rel_path, frontmatter, manifest):
    normalized = rel_path.replace("\\", "/")
    if any(normalized.startswith(prefix) for prefix in LEGACY_PAGE_PREFIXES):
        return "legacy"

    for entry in manifest.get("known_legacy_entries", []):
        if str(entry.get("path", "")).replace("\\", "/") == normalized:
            return str(entry.get("classification", "legacy")).strip().lower()

    lifecycle = str(frontmatter.get("lifecycle", "")).strip().lower()
    status = str(frontmatter.get("status", "")).strip().lower()
    if lifecycle in {"current", "active", "superseded", "historical", "draft", "mixed_needs_review", "archive"}:
        return lifecycle
    if status in {"current", "active", "superseded", "historical", "draft", "mixed_needs_review", "archive"}:
        return status
    return "unclassified"


def audit_required_authorities(manifest=None):
    """Validate one explicit current authority for every required label."""
    manifest = manifest or {}
    configured = manifest.get("required_authorities", {})
    rows = []
    errors = []
    duplicate_labels = []

    if not isinstance(configured, dict):
        return {
            "status": "FAIL",
            "required_count": 0,
            "resolved_count": 0,
            "missing": ["required_authorities_not_a_mapping"],
            "duplicate_labels": [],
            "invalid": [],
        }

    for domain, entries in configured.items():
        if not isinstance(entries, list):
            errors.append(f"{domain}:entries_not_a_list")
            continue
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                errors.append(f"{domain}[{index}]:entry_not_a_mapping")
                continue
            row = dict(entry)
            row["domain"] = domain
            row["index"] = index
            rows.append(row)

    label_rows = {}
    for row in rows:
        label = normalize_label(row.get("label", ""))
        if not label:
            errors.append(f"{row['domain']}[{row['index']}]:invalid_label")
            continue
        label_rows.setdefault(label, []).append(row)

    for label, matching_rows in sorted(label_rows.items()):
        if len(matching_rows) > 1:
            duplicate_labels.append(label)

    pages = {}
    for path in VAULT_ROOT.glob("**/*.md"):
        rel = str(path.relative_to(VAULT_ROOT)).replace("\\", "/")
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        pages[rel] = (content, parse_frontmatter(content) or {})

    resolved_count = 0
    for row in rows:
        prefix = f"{row['domain']}[{row['index']}]"
        label = normalize_label(row.get("label", ""))
        authority_page = str(row.get("authority_page", "")).replace("\\", "/")
        classification = str(row.get("authority_classification", "")).strip().lower()
        evidence = row.get("source_evidence")

        if not label:
            continue
        if authority_page not in pages:
            errors.append(f"{prefix}:missing_authority_page:{authority_page}")
            continue
        content, frontmatter = pages[authority_page]
        actual_classification = _page_classification(
            authority_page, frontmatter, manifest
        )
        if authority_page.startswith(LEGACY_PAGE_PREFIXES):
            errors.append(f"{prefix}:legacy_or_generated_authority:{authority_page}")
        if classification not in CURRENT_AUTHORITY_CLASSIFICATIONS:
            errors.append(f"{prefix}:invalid_manifest_classification:{classification}")
        if actual_classification not in CURRENT_AUTHORITY_CLASSIFICATIONS:
            errors.append(
                f"{prefix}:page_not_current:{authority_page}:{actual_classification}"
            )
        page_labels = {normalize_label(match.group(0)) for match in LABEL_PATTERN.finditer(content)}
        if label not in page_labels:
            errors.append(f"{prefix}:label_missing_from_authority_page:{label}")

        if not isinstance(evidence, dict):
            errors.append(f"{prefix}:source_evidence_not_a_mapping")
        else:
            kind = str(evidence.get("kind", "")).strip().lower()
            source_path = str(evidence.get("source_path", "")).replace("\\", "/")
            if kind not in {"code_backed", "spec_backed"}:
                errors.append(f"{prefix}:invalid_source_evidence_kind:{kind}")
            if not source_path or not (REPO_ROOT / source_path).is_file():
                errors.append(f"{prefix}:missing_source_evidence:{source_path}")
            if source_path.startswith((".nexus/", "docs/reports/", "99_Schema/generated/")):
                errors.append(f"{prefix}:non_authoritative_source_evidence:{source_path}")
            if kind == "code_backed" and label.startswith("[code:"):
                label_path = label[len("[code: "):-1]
                if label_path != source_path.lower():
                    errors.append(f"{prefix}:code_label_source_mismatch")
        if not any(error.startswith(f"{prefix}:") for error in errors):
            resolved_count += 1

    missing_labels = []
    configured_labels = {
        normalize_label(label)
        for config in CAPABILITY_DOMAINS.values()
        for label in config["required_labels"]
    }
    for label in sorted(configured_labels - set(label_rows)):
        missing_labels.append(f"manifest_missing_required_label:{label}")
    errors.extend(missing_labels)

    return {
        "status": "PASS" if not errors and not duplicate_labels else "FAIL",
        "required_count": len(rows),
        "resolved_count": resolved_count,
        "missing": sorted(set(errors)),
        "duplicate_labels": sorted(duplicate_labels),
        "invalid": sorted(set(errors)),
    }

def parse_frontmatter(content):
    if content.startswith("---"):
        try:
            end = content.find("---", 3)
            if end != -1:
                return yaml.safe_load(content[3:end])
        except Exception:
            pass
    return {}

def audit_capabilities(stale_days=45):
    results = {}
    all_pages = list(VAULT_ROOT.glob("**/*.md"))
    try:
        manifest = yaml.safe_load(AUTHORITY_MANIFEST_PATH.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        manifest = {}
    authority_checks = audit_required_authorities(manifest)
    
    total_weighted_score = 0.0
    total_weight = 0.0
    
    ownership_missing_count = 0
    stale_count = 0
    aging_breakdown = {}
    
    today = datetime.date.today()
    
    for domain, config in CAPABILITY_DOMAINS.items():
        domain_status = {
            "pages_found": [],
            "pages_missing": [],
            "labels_found": [],
            "labels_missing": [],
            "score": 0.0,
            "risk_weight": config.get("risk_weight", 0.5),
            "ownership_missing": [],
            "stale_pages": []
        }
        
        aging_breakdown[domain] = {"total": 0, "stale": 0, "missing_owner": 0}
        
        # Check Pages
        for req_page in config["required_pages"]:
            p = VAULT_ROOT / req_page
            found = p.is_file()
            if found:
                domain_status["pages_found"].append(req_page)
                aging_breakdown[domain]["total"] += 1

                content = p.read_text(encoding="utf-8")
                frontmatter = parse_frontmatter(content) or {}
                    
                # Owner Check
                if not frontmatter.get("owner"):
                    domain_status["ownership_missing"].append(req_page)
                    ownership_missing_count += 1
                    aging_breakdown[domain]["missing_owner"] += 1

                # Stale Check
                last_compiled = frontmatter.get("last_compiled")
                if isinstance(last_compiled, str):
                    try:
                        last_compiled = datetime.datetime.strptime(last_compiled, "%Y-%m-%d").date()
                    except (TypeError, ValueError):
                        last_compiled = None

                if isinstance(last_compiled, datetime.date):
                    delta = (today - last_compiled).days
                    if delta > stale_days:
                        domain_status["stale_pages"].append({"page": req_page, "days": delta})
                        stale_count += 1
                        aging_breakdown[domain]["stale"] += 1
                else:
                    domain_status["stale_pages"].append({"page": req_page, "days": -1})
                    stale_count += 1
                    aging_breakdown[domain]["stale"] += 1

                found_in_page = {
                    normalize_label(match.group(0))
                    for match in LABEL_PATTERN.finditer(content)
                }
                for req_label in config["required_labels"]:
                    if normalize_label(req_label) in found_in_page:
                        if req_label not in domain_status["labels_found"]:
                            domain_status["labels_found"].append(req_label)
            if not found:
                domain_status["pages_missing"].append(req_page)
        
        for req_label in config["required_labels"]:
            if req_label not in domain_status["labels_found"]:
                domain_status["labels_missing"].append(req_label)
        
        # Calculate Score
        total_req = len(config["required_pages"]) + len(config["required_labels"])
        found_req = len(domain_status["pages_found"]) + len(domain_status["labels_found"])
        domain_status["score"] = found_req / total_req if total_req > 0 else 1.0
        
        results[domain] = domain_status
        
        total_weighted_score += domain_status["score"] * domain_status["risk_weight"]
        total_weight += domain_status["risk_weight"]
    
    weighted_avg = total_weighted_score / total_weight if total_weight > 0 else 0.0
    return {
        "results": results,
        "weighted_score": weighted_avg,
        "ownership_missing_count": ownership_missing_count,
        "stale_count": stale_count,
        "aging_breakdown": aging_breakdown,
        "authority_checks": authority_checks,
    }

def main():
    parser = argparse.ArgumentParser(description="🛡️ Nexus Wiki Capability Coverage Audit")
    parser.add_argument("--output", type=str, default=str(REPORT_PATH), help="Path to save report")
    parser.add_argument("--stale-days", type=int, default=45, help="Threshold for stale pages")
    args = parser.parse_args()
    
    print(f"🛡️ Starting Nexus Wiki Capability Coverage Audit (stale_days={args.stale_days})...")
    audit_data = audit_capabilities(stale_days=args.stale_days)
    report = audit_data["results"]
    weighted_score = audit_data["weighted_score"]
    
    # Summary
    avg_score = sum(d["score"] for d in report.values()) / len(report)
    print(f"📈 Capability Coverage Score (Avg): {avg_score:.2%}")
    print(f"⚖️ Weighted Capability Score: {weighted_score:.2%}")
    print(f"👤 Ownership Missing: {audit_data['ownership_missing_count']}")
    print(f"⏰ Stale Pages: {audit_data['stale_count']}")
    authority_checks = audit_data["authority_checks"]
    print(
        f"🔐 Required Authority Gate: {authority_checks['status']} "
        f"({authority_checks['resolved_count']}/{authority_checks['required_count']})"
    )
    if authority_checks["duplicate_labels"]:
        print(f"  - Duplicate Authorities: {authority_checks['duplicate_labels']}")
    if authority_checks["missing"]:
        print(f"  - Authority Errors: {authority_checks['missing']}")
    
    domain_risk_breakdown = {}
    for domain, data in report.items():
        status = "✅" if data["score"] == 1.0 else "⚠️" if data["score"] > 0.5 else "❌"
        print(f"{status} {domain} (weight: {data['risk_weight']}): {data['score']:.0%}")
        domain_risk_breakdown[domain] = {
            "score": data["score"],
            "risk_weight": data["risk_weight"]
        }
        if data["pages_missing"]:
            print(f"  - Missing Pages: {data['pages_missing']}")
        if data["labels_missing"]:
            print(f"  - Missing Labels: {data['labels_missing']}")
        if data["ownership_missing"]:
            print(f"  - Missing Owner: {data['ownership_missing']}")
        if data["stale_pages"]:
            print(f"  - Stale Pages: {[s['page'] for s in data['stale_pages']]}")
            
    # Save Report
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({
            "summary": {
                "average_score": avg_score,
                "weighted_score": weighted_score,
                "ownership_missing_count": audit_data["ownership_missing_count"],
                "stale_count": audit_data["stale_count"],
                "domain_risk_breakdown": domain_risk_breakdown,
                "aging_breakdown": audit_data["aging_breakdown"],
                "authority_checks": authority_checks,
            },
            "details": report
        }, f, indent=2)
    print(f"Report saved to: {output_path}")
    gate_passed = (
        authority_checks["status"] == "PASS"
        and all(
            not data["pages_missing"] and not data["labels_missing"]
            for data in report.values()
        )
    )
    return 0 if gate_passed else 1

if __name__ == "__main__":
    sys.exit(main())
