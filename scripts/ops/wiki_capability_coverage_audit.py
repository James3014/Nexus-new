#!/usr/bin/env python3
import os
import re
import json
import argparse
import datetime
import yaml
from pathlib import Path

# 🛡️ Nexus Wiki Capability Coverage Audit v1.1
# Purpose: Verify that critical system capabilities are documented with evidence, owner, and freshness.

REPO_ROOT = Path(str(__import__("pathlib").Path(__file__).resolve().parents[2]))
VAULT_ROOT = REPO_ROOT / "nexus_wiki_vault"
REPORT_PATH = REPO_ROOT / ".nexus" / "reports" / "wiki_capability_coverage_report.json"

CAPABILITY_DOMAINS = {
    "pxdrac_runtime": {
        "required_pages": ["Flow - PXDRAC Runtime", "Module - Core Orchestrator Deep Dive"],
        "required_labels": ["[code: nexus_cli.py]", "[source: Spec v22]"],
        "risk_weight": 1.0
    },
    "release_governance": {
        "required_pages": ["Ops - Acceptance and Release", "Ops - Wiki Page Type Contracts"],
        "required_labels": ["[code: ci_gate.py]", "[source: Release Discipline]"],
        "risk_weight": 0.8
    },
    "truth_claims": {
        "required_pages": ["Ops - Truth Claims Register", "Ops - Truth Claims Command Policy"],
        "required_labels": ["[code: wiki_truth_claims_check.py]"],
        "risk_weight": 0.9
    },
    "incident_response": {
        "required_pages": ["Ops - CI Failure Playbook", "Module - Dual Phase Diagnosis"],
        "required_labels": ["[code: incident_rca_adapter.py]"],
        "risk_weight": 0.7
    },
    "command_surface": {
        "required_pages": ["Protocol - CLI Surface", "Agent Onboarding - Command Pack"],
        "required_labels": ["[code: nexus_cli.py]", "[source: Protocol - CLI Surface]"],
        "risk_weight": 0.6
    }
}

# PROVENANCE_TAG_PATTERN from wiki_linter.py
PROVENANCE_TAG_PATTERN = re.compile(r"\[(source|code):\s*(.*?)\]|\((source|code):\s*(.*?)\)", re.I)

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
            found = False
            for p in all_pages:
                if p.stem == req_page:
                    found = True
                    domain_status["pages_found"].append(req_page)
                    aging_breakdown[domain]["total"] += 1
                    
                    content = p.read_text()
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
                        except:
                            last_compiled = None
                    
                    if isinstance(last_compiled, datetime.date):
                        delta = (today - last_compiled).days
                        if delta > stale_days:
                            domain_status["stale_pages"].append({"page": req_page, "days": delta})
                            stale_count += 1
                            aging_breakdown[domain]["stale"] += 1
                    else:
                        # If no date, consider it stale
                        domain_status["stale_pages"].append({"page": req_page, "days": -1})
                        stale_count += 1
                        aging_breakdown[domain]["stale"] += 1

                    # Scan for labels in found page
                    matches = PROVENANCE_TAG_PATTERN.findall(content)
                    found_in_page = []
                    for m in matches:
                        # m is (type1, val1, type2, val2)
                        label_type = (m[0] or m[2]).lower()
                        label_val = (m[1] or m[3]).strip().lower()
                        found_in_page.append(f"[{label_type}: {label_val}]")
                    
                    for req_label in config["required_labels"]:
                        # req_label is like "[code: nexus_cli.py]"
                        rl_match = re.match(r"\[(source|code):\s*(.*?)\]", req_label, re.I)
                        if rl_match:
                            rl_type = rl_match.group(1).lower()
                            rl_val = rl_match.group(2).strip().lower()
                            canonical_req = f"[{rl_type}: {rl_val}]"
                            if canonical_req in found_in_page:
                                if req_label not in domain_status["labels_found"]:
                                    domain_status["labels_found"].append(req_label)
                    break
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
        "aging_breakdown": aging_breakdown
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
                "aging_breakdown": audit_data["aging_breakdown"]
            },
            "details": report
        }, f, indent=2)
    print(f"Report saved to: {output_path}")

if __name__ == "__main__":
    main()
