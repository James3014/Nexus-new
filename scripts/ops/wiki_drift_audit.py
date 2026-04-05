#!/usr/bin/env python3
import os
import re
import json
import subprocess
from pathlib import Path

# 🛡️ Nexus Wiki Drift Audit (Agent 3 - WS3)
# Purpose: Detect physical path breakage and stale documentation claims.

REPO_ROOT = Path("/Users/jameschen/Workspace/nexus")
VAULT_ROOT = REPO_ROOT / "nexus_wiki_vault"
REPORT_PATH = REPO_ROOT / ".nexus" / "reports" / "wiki_drift_report.json"

PROVENANCE_PATTERN = re.compile(r"\[source:\s*(.*?)\]|\(source:\s*(.*?)\)|\[code:\s*(.*?)\]|\(code:\s*(.*?)\)", re.I)

def get_git_mtime(path_str):
    try:
        # Get the last commit timestamp for the file
        res = subprocess.check_output(
            ["git", "log", "-1", "--format=%ct", path_str],
            cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
        return int(res) if res else 0
    except:
        return 0

def run_drift_audit():
    print("🛡️ WS3: Starting Wiki Drift Audit...")
    claims = []
    missing_paths = []
    valid_paths = []
    
    for md in VAULT_ROOT.glob("**/*.md"):
        if "99_Schema" in str(md): continue
        content = md.read_text()
        matches = PROVENANCE_PATTERN.findall(content)
        
        rel_md = str(md.relative_to(VAULT_ROOT))
        
        for match in matches:
            path_str = next((g for g in match if g), "").strip()
            path_str = path_str.replace("`", "").replace("'", "").replace("\"", "")
            # Clean up Part/L123 metadata
            clean_path = re.sub(r"\s+Part\s+.*$", "", path_str, flags=re.I)
            clean_path = re.sub(r"\s+L\d+.*$", "", clean_path, flags=re.I)
            clean_path = re.sub(r"#.*$", "", clean_path).strip()
            
            if not clean_path: continue
            
            # Resolve physical path (ignore external / or URI for now)
            if clean_path.startswith("/") or "://" in clean_path:
                continue
                
            abs_path = REPO_ROOT / clean_path
            exists = abs_path.exists()
            
            claim = {
                "page": rel_md,
                "raw_claim": path_str,
                "resolved_path": clean_path,
                "exists": exists,
            }
            
            if exists:
                claim["git_mtime"] = get_git_mtime(clean_path)
                valid_paths.append(clean_path)
            else:
                missing_paths.append(claim)
                
            claims.append(claim)

    # Detect stale candidates (those with very old git mtime vs page mtime)
    stale_candidates = [c for c in claims if c.get("git_mtime", 0) > 0 and (os.path.getmtime(VAULT_ROOT / c["page"]) < c["git_mtime"])]

    report = {
        "summary": {
            "total_claims": len(claims),
            "valid_claims": len(valid_paths),
            "missing_claims": len(missing_paths),
            "stale_candidates": len(stale_candidates)
        },
        "missing_details": missing_paths[:50],
        "stale_details": stale_candidates[:20]
    }
    
    os.makedirs(REPORT_PATH.parent, exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)
        
    print(f"✅ Drift audit complete. Missing: {len(missing_paths)}, Stale: {len(stale_candidates)}")
    print(f"📄 Report saved to: {REPORT_PATH}")
    
    if missing_paths:
        return 1
    return 0

if __name__ == "__main__":
    exit(run_drift_audit())
