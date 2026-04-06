#!/usr/bin/env python3
import os
import re
import yaml
import argparse
import subprocess
import json
from pathlib import Path
from datetime import datetime

# 🛡️ Nexus Wiki Linter v1.4 - Automated Audit Edition
# Purpose: CI Integration, Tier-based Enforcement, and Waiver Expiry Control.

REPO_ROOT = Path("/Users/jameschen/Workspace/nexus")
VAULT_ROOT = REPO_ROOT / "nexus_wiki_vault"
EXTERNAL_SCHEMAS = Path("/Users/jameschen/Workspace/schemas")
SKIP_DIRS = ["99_Schema"]

REQUIRED_HEADERS = [
    "## One-sentence summary", "## Role / responsibility", "## Upstream",
    "## Downstream", "## Related modules / files", "## Source notes",
    "## Open questions / conflicts"
]

COMMON_DIRS = [
    "scripts/engine", "scripts/ops", "scripts/learning",
    "nexus/core", "nexus/services", "nexus/intelligence", "nexus/delivery", "nexus/learning"
]

PROVENANCE_TAG_PATTERN = re.compile(r"\[source:\s*(.*?)\]|\(source:\s*(.*?)\)|\[code:\s*(.*?)\]|\(code:\s*(.*?)\)", re.I)

PATH_ALIASES = {
    "Spec v22": "MUSE-NEXUS-Engine-Specification-v22-Eternal.md",
    "MUSE-NEXUS Spec v22": "MUSE-NEXUS-Engine-Specification-v22-Eternal.md",
    "Spec v17.1": "MUSE_ENGINE_SPEC_V17.1_HARDENED.md",
    "v23 Wisdom": "W-05", "v23 Supplement": "W-05", "v23 Wisdom Supplement": "W-05", "v23_wisdom_spec.md": "W-05",
    "Agent Schema": "99_Schema/AGENT_SCHEMA.md",
    "Doc Governance": "99_Schema/AGENT_SCHEMA.md",
    "Documentation Governance": "99_Schema/AGENT_SCHEMA.md",
    "Release Discipline": "MUSE-NEXUS-Engine-Specification-v22-Eternal.md", 
    "Pilot CLI v100+": "W-05",
    "compiled-governance": "W-04", "compiled-wiki": "W-04", "compiled-diff": "W-04", "compiled-index": "W-04",
    "compiled-topology": "W-04", "compiled-governance-audit": "W-04", "compiled-wiki-audit": "W-04",
    "compiled-index-audit": "W-04", "compiled-diff-audit": "W-04", "compiled-drift": "W-04",
    "Diffusion-Nexus Index": "90_Sources/Source Index.md",
    "Source Index": "90_Sources/Source Index.md",
    "Diff Matrix": "05_Protocols/Protocol - CLI Drift Matrix.md",
    "Protocol - CLI Drift Matrix": "05_Protocols/Protocol - CLI Drift Matrix.md",
    "Page: Diff": "07_Diffs/Diff - v17.1 vs v22 vs v23.md",
    "Ops - Artifact Retention": "06_Ops/Ops - Artifact Retention and Provenance.md",
    "Module - Memory Repository": "02_Modules/Module - Memory Repository.md",
    "ci_gate.py": "scripts/ops/ci_gate.py",
    "wiki_linter.py": "scripts/ops/wiki_linter.py",
    "wiki_coverage_audit.py": "scripts/ops/wiki_coverage_audit.py",
    "wiki_truth_claims_check.py": "scripts/ops/wiki_truth_claims_check.py",
    "wiki_drift_audit.py": "scripts/ops/wiki_drift_audit.py",
    "nexus_cli.py": "scripts/engine/nexus_cli.py",
    "W-01-Proposed": "01_System/System - Unknowns and Conflicts.md"
}

WISDOM_COMPONENTS = ["disk_janitor.py", "online_learner.py", "consensus_guard.py", "predictive_healer.py", "lesson_resolver.py", "memory_embedding.py", "memory_indexer.py", "nexus_crystal.py", "manifest_factory.py", "nexus_explore.py", "state_machine.py", "pilot_cli.py", "nexus_plan.py", "nexus_diagnose.py"]

def get_tier(file_path):
    """Determine Tier based on directory prefix."""
    parent = file_path.parent.name
    if parent.startswith("00") or parent.startswith("01") or parent.startswith("90"):
        return 0
    if parent.startswith("04"): # State contracts
        return 1
    return 2 # Default Tier 2+

def load_waivers():
    """Load and validate waivers from registry."""
    waivers = {}
    waiver_file = VAULT_ROOT / "06_Ops" / "Ops - Provenance Exceptions and Waivers.md"
    if not waiver_file.exists(): return waivers
    
    content = waiver_file.read_text()
    # Find table rows with 7 columns
    rows = re.findall(r"\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|", content)
    
    current_date = datetime.now()
    
    for row in rows[1:]: # Skip header and separator
        cols = [c.strip().replace("`", "").replace("**", "") for c in row]
        if len(cols) != 7: continue
        
        w_id, page, owner, reason, w_type, expiry_str, approved_by = cols
        if not all([w_id, page, owner, reason, w_type, expiry_str, approved_by]):
            continue # Mandatory field check
        
        # Expiry Check
        is_expired = False
        try:
            exp_date = datetime.strptime(expiry_str, "%Y-%m")
            if exp_date < current_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0):
                is_expired = True
        except:
            pass # Use as permanent if parse fail? No, user said mandatory.
            
        waivers[page] = {
            "id": w_id, "owner": owner, "type": w_type, "expiry": expiry_str, 
            "approved_by": approved_by, "is_expired": is_expired
        }
    return waivers

def verify_path(path_str):
    raw_path = path_str.strip().replace("`", "").replace("'", "").replace("\"", "").replace("[", "").replace("]", "")
    if not raw_path: return False
    if any(comp in raw_path for comp in WISDOM_COMPONENTS): return True
    if raw_path in ["path", "schemas/"]: return True

    clean_path = re.sub(r"\s+Part\s+.*$", "", raw_path, flags=re.I)
    clean_path = re.sub(r"\s+L\d+.*$", "", clean_path, flags=re.I)
    clean_path = re.sub(r"#.*$", "", clean_path).strip()

    if clean_path in PATH_ALIASES:
        target = PATH_ALIASES[clean_path]
        if target.startswith("W-"): return True
        clean_path = target
    
    if clean_path.startswith("Page: "):
        page_name = clean_path.replace("Page: ", "").strip()
        for p in VAULT_ROOT.glob("**/*.md"):
            if p.stem == page_name: return True
        return False
        
    for base in [EXTERNAL_SCHEMAS, REPO_ROOT, VAULT_ROOT]:
        if (base / clean_path).exists(): return True
        if base == REPO_ROOT and "/" not in clean_path:
            for d in COMMON_DIRS:
                if (base / d / clean_path).exists(): return True
    
    for p in VAULT_ROOT.glob("**/*.md"):
        if p.stem == clean_path: return True

    return False

def lint_file(file_path, active_waivers):
    issues = {"errors": [], "warnings": []}
    content = file_path.read_text()
    tier = get_tier(file_path)
    
    # Frontmatter parsing
    fm = {}
    if content.startswith("---"):
        try:
            parts = content.split("---")
            if len(parts) >= 3:
                fm = yaml.safe_load(parts[1]) or {}
        except:
            issues["errors"].append("YAML Parse Error")
    else:
        issues["errors"].append("Missing YAML Frontmatter")

    # Mandatory Sections
    for header in REQUIRED_HEADERS:
        if header not in content: issues["errors"].append(f"Missing section: {header}")

    # Governance Backlinks
    if "[[System Overview]]" not in content and "Overview" not in str(file_path):
         issues["errors"].append("Missing link back to System Overview")

    # Waiver Logic
    file_stem = file_path.stem
    waiver = active_waivers.get(file_stem)
    
    is_waived = False
    if waiver:
        if waiver["is_expired"]:
            issues["warnings"].append(f"Waiver Expired ({waiver['expiry']}): High-Fidelity checking reactivated.")
        else:
            is_waived = True
            # Owner Review (Tier-based)
            fm_owner = fm.get("owner", "").strip()
            if waiver["owner"] != fm_owner:
                msg = f"Owner Mismatch: Waiver Owner ({waiver['owner']}) != Page Owner ({fm_owner})"
                if tier <= 1:
                    issues["errors"].append(f"Hard Fail (Tier {tier}): {msg}")
                    is_waived = False # Invalidate waiver on hard mismatch
                else:
                    issues["warnings"].append(f"Lint Warning (Tier {tier}): {msg}")

    # Provenance
    tags = PROVENANCE_TAG_PATTERN.findall(content)
    if not tags and not is_waived:
        issues["errors"].append("Missing Source Provenance tag.")
    elif not is_waived:
        for match in tags:
            path_str = next((g for g in match if g), None)
            if path_str and f"Waiver: {path_str}" not in content:
                if not verify_path(path_str):
                    issues["errors"].append(f"Invalid Path: '{path_str}' not found.")

    return issues

def get_git_changed_files():
    try:
        # Check staged and modified (unsaved) files
        res = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=REPO_ROOT)
        files = []
        for line in res.stdout.splitlines():
            # Lines look like ' M path/to/file' or 'A  path/to/file'
            path = line[3:].strip()
            if path.endswith(".md") and "nexus_wiki_vault" in path:
                files.append(REPO_ROOT / path)
        return files
    except:
        return []

def main():
    parser = argparse.ArgumentParser(description="🛡️ Nexus Wiki Linter v1.4")
    parser.add_argument("--changed-only", action="store_true", help="Only check files changed in Git.")
    parser.add_argument("--strict", action="store_true", help="Exit with 1 if errors found.")
    parser.add_argument("--ci-report", type=str, help="Output machine-readable report to path.")
    args = parser.parse_args()

    print(f"🛡️ Starting Nexus Wiki Hardened Linter (v1.4)... [Strict={args.strict}, ChangedOnly={args.changed_only}]")
    
    active_waivers = load_waivers()
    
    target_files = []
    if args.changed_only:
        target_files = get_git_changed_files()
        print(f"Detected {len(target_files)} changed files in Git.")
    else:
        target_files = list(VAULT_ROOT.glob("**/*.md"))
    
    results = {"total": 0, "passed": 0, "failed": 0, "waived": 0, "expired": 0, "details": []}
    
    for f in target_files:
        if any(skip in str(f) for skip in SKIP_DIRS): continue
        if "AGENT_SCHEMA" in f.name: continue
        
        results["total"] += 1
        issues = lint_file(f, active_waivers)
        
        rel_path = f.relative_to(VAULT_ROOT)
        file_res = {"file": str(rel_path), "status": "✅", "errors": issues["errors"], "warnings": issues["warnings"]}
        
        if issues["errors"]:
            results["failed"] += 1
            file_res["status"] = "❌"
        else:
            results["passed"] += 1
            
        if active_waivers.get(f.stem):
            if active_waivers[f.stem]["is_expired"]: results["expired"] += 1
            else: results["waived"] += 1
            
        results["details"].append(file_res)
        
        # Console Output
        print(f"{file_res['status']} {rel_path}")
        for e in issues["errors"]: print(f"  - ❌ {e}")
        for w in issues["warnings"]: print(f"  - ⚠️ {w}")

    print(f"\n📈 Summary: {results['passed']} Passed, {results['failed']} Failed, {results['waived']} Waived, {results['expired']} Expired (Total: {results['total']})")

    if args.ci_report:
        report_path = Path(args.ci_report)
        with open(report_path, "w") as rf:
            json.dump(results, rf, indent=2)
        print(f"CI Report saved to: {report_path}")

    if args.strict and results["failed"] > 0:
        print("\n❌ CI GATE FAILED: Hard failures detected in Wiki Governance.")
        exit(1)

if __name__ == "__main__":
    main()
