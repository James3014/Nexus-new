#!/usr/bin/env python3
import os
import re
import json
import argparse
from pathlib import Path

# 🛡️ Nexus Wiki Eval Regression v1.1
# Purpose: Execute automated regression testing of Wiki content via deterministic keyword checks.

REPO_ROOT = Path(str(__import__("pathlib").Path(__file__).resolve().parents[2]))
VAULT_ROOT = REPO_ROOT / "nexus_wiki_vault"
EVAL_FILE = VAULT_ROOT / "06_Ops" / "Ops - Wiki Regression Evals.md"
REPORT_PATH = REPO_ROOT / ".nexus" / "reports" / "wiki_eval_report.json"

# PROVENANCE_TAG_PATTERN from wiki_linter.py
PROVENANCE_TAG_PATTERN = re.compile(r"\[(source|code):\s*(.*?)\]|\((source|code):\s*(.*?)\)", re.I)

def parse_regression_suite():
    if not EVAL_FILE.exists():
        return []
    
    content = EVAL_FILE.read_text()
    # Regex to find table rows: | ID | Domain | Question | Target Page | Required Keywords |
    rows = re.findall(r"\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|", content)
    
    suite = []
    for row in rows[1:]: # Skip header
        cols = [c.strip() for c in row]
        if len(cols) != 5:
            continue
        case_id = cols[0].replace('`', '').replace('**', '')
        if not case_id or case_id.startswith('---') or case_id == 'ID' or not case_id.startswith('Q'):
            continue
            
        suite.append({
            "id": case_id,
            "domain": cols[1],
            "question": cols[2],
            "target": cols[3],
            "keywords": [k.strip().replace('"', '') for k in cols[4].split(",")]
        })
    return suite

def evaluate_page(target_name):
    # Search for target page (could be relative path or just stem)
    if target_name.endswith(".md") or "/" in target_name:
        target_path = REPO_ROOT / target_name
        if not target_path.exists():
             target_path = VAULT_ROOT / target_name
    else:
        # Search by stem
        found = list(VAULT_ROOT.glob(f"**/{target_name}.md"))
        if not found:
            # Maybe it's a code file?
            target_path = REPO_ROOT / target_name
        else:
            target_path = found[0]
            
    if not target_path.exists():
        return None, f"Target not found: {target_name}"
    
    try:
        content = target_path.read_text()
        return content, None
    except Exception as e:
        return None, str(e)

def run_regression(evidence_chain=False):
    suite = parse_regression_suite()
    print(f"🛡️ Running Wiki Eval Regression ({len(suite)} cases, evidence_chain={evidence_chain})...")
    
    results = []
    passed_count = 0
    evidence_passed_count = 0
    
    for case in suite:
        res = {
            "id": case["id"],
            "target": case["target"],
            "passed": False,
            "evidence_passed": False,
            "found_keywords": [],
            "missing_keywords": [],
            "has_provenance": False,
            "error": None,
            "failure_reason": None
        }
        
        content, err = evaluate_page(case["target"])
        if err:
            res["error"] = err
            res["failure_reason"] = "MISSING_PAGE"
        else:
            content_lower = content.lower()
            for kw in case["keywords"]:
                kw_norm = kw.lower()
                if kw_norm in content_lower:
                    res["found_keywords"].append(kw)
                else:
                    res["missing_keywords"].append(kw)
            
            # Check for provenance marker
            if PROVENANCE_TAG_PATTERN.search(content):
                res["has_provenance"] = True
            
            if not res["missing_keywords"]:
                res["passed"] = True
                passed_count += 1
                if res["has_provenance"]:
                    res["evidence_passed"] = True
                    evidence_passed_count += 1
                elif evidence_chain:
                    res["failure_reason"] = "MISSING_EVIDENCE"
            else:
                res["failure_reason"] = "MISSING_KEYWORDS"
        
        # If evidence_chain is strict, a case only passes if it has both keywords and evidence
        final_pass = res["passed"]
        if evidence_chain and not res["has_provenance"]:
            final_pass = False
            
        results.append(res)
        
    pass_rate = passed_count / len(suite) if suite else 1.0
    evidence_pass_rate = evidence_passed_count / len(suite) if suite else 1.0
    failed_cases = [r for r in results if (evidence_chain and not r["evidence_passed"]) or (not evidence_chain and not r["passed"])]
    
    return {
        "summary": {
            "total_cases": len(suite),
            "passed_cases": passed_count,
            "pass_rate": pass_rate,
            "evidence_passed_cases": evidence_passed_count,
            "evidence_pass_rate": evidence_pass_rate,
            "failed_count": len(failed_cases)
        },
        "failed_cases": failed_cases,
        "details": results
    }

def main():
    parser = argparse.ArgumentParser(description="🛡️ Nexus Wiki Eval Regression")
    parser.add_argument("--output", type=str, default=str(REPORT_PATH), help="Path to save report")
    parser.add_argument("--evidence-chain", action="store_true", help="Enforce evidence marker presence")
    args = parser.parse_args()
    
    report = run_regression(evidence_chain=args.evidence_chain)
    
    print(f"📈 Pass Rate: {report['summary']['pass_rate']:.2%}")
    print(f"🔗 Evidence Pass Rate: {report['summary']['evidence_pass_rate']:.2%}")
    if report['failed_cases']:
        print(f"❌ Failed Cases: {report['summary']['failed_count']}")
        for f in report['failed_cases']:
            print(f"  - {f['id']} ({f['target']}): {f['failure_reason']}")
            if f['missing_keywords']: print(f"    Missing keywords: {f['missing_keywords']}")
            if f['error']: print(f"    Error: {f['error']}")
    else:
        print("✅ All regression cases passed!")
        
    # Save Report
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Report saved to: {output_path}")

if __name__ == "__main__":
    main()
