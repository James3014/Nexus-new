#!/usr/bin/env python3
import os
import re
import json
import argparse
from pathlib import Path

# 🛡️ Nexus Wiki Capability Coverage Audit v1.0
# Purpose: Verify that critical system capabilities are documented with evidence.

REPO_ROOT = Path("/Users/jameschen/Workspace/nexus")
VAULT_ROOT = REPO_ROOT / "nexus_wiki_vault"
REPORT_PATH = REPO_ROOT / ".nexus" / "reports" / "wiki_capability_coverage_report.json"

CAPABILITY_DOMAINS = {
    "pxdrac_runtime": {
        "required_pages": ["Flow - PXDRAC Runtime", "Module - Core Orchestrator Deep Dive"],
        "required_labels": ["[code: nexus_cli.py]", "[source: Spec v22]"]
    },
    "release_governance": {
        "required_pages": ["Ops - Acceptance and Release", "Ops - Wiki Page Type Contracts"],
        "required_labels": ["[code: ci_gate.py]", "[source: Release Discipline]"]
    },
    "truth_claims": {
        "required_pages": ["Ops - Truth Claims Register", "Ops - Truth Claims Command Policy"],
        "required_labels": ["[code: wiki_truth_claims_check.py]"]
    },
    "incident_response": {
        "required_pages": ["Ops - CI Failure Playbook", "Module - Dual Phase Diagnosis"],
        "required_labels": ["[code: incident_rca_adapter.py]"]
    },
    "command_surface": {
        "required_pages": ["Protocol - CLI Surface", "Agent Onboarding - Command Pack"],
        "required_labels": ["[code: nexus_cli.py]", "[source: Protocol - CLI Surface]"]
    }
}

# PROVENANCE_TAG_PATTERN from wiki_linter.py
PROVENANCE_TAG_PATTERN = re.compile(r"\[(source|code):\s*(.*?)\]|\((source|code):\s*(.*?)\)", re.I)

def audit_capabilities():
    results = {}
    all_pages = list(VAULT_ROOT.glob("**/*.md"))
    
    for domain, config in CAPABILITY_DOMAINS.items():
        domain_status = {
            "pages_found": [],
            "pages_missing": [],
            "labels_found": [],
            "labels_missing": [],
            "score": 0.0
        }
        
        # Check Pages
        for req_page in config["required_pages"]:
            found = False
            for p in all_pages:
                if p.stem == req_page:
                    found = True
                    domain_status["pages_found"].append(req_page)
                    
                    # Scan for labels in found page
                    content = p.read_text()
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
    
    return results

def main():
    parser = argparse.ArgumentParser(description="🛡️ Nexus Wiki Capability Coverage Audit")
    parser.add_argument("--output", type=str, default=str(REPORT_PATH), help="Path to save report")
    args = parser.parse_args()
    
    print("🛡️ Starting Nexus Wiki Capability Coverage Audit...")
    report = audit_capabilities()
    
    # Summary
    avg_score = sum(d["score"] for d in report.values()) / len(report)
    print(f"📈 Capability Coverage Score: {avg_score:.2%}")
    
    for domain, data in report.items():
        status = "✅" if data["score"] == 1.0 else "⚠️" if data["score"] > 0.5 else "❌"
        print(f"{status} {domain}: {data['score']:.0%}")
        if data["pages_missing"]:
            print(f"  - Missing Pages: {data['pages_missing']}")
        if data["labels_missing"]:
            print(f"  - Missing Labels: {data['labels_missing']}")
            
    # Save Report
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({"summary": {"average_score": avg_score}, "details": report}, f, indent=2)
    print(f"Report saved to: {output_path}")

if __name__ == "__main__":
    main()
