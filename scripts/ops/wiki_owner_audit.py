#!/usr/bin/env python3
import os
import yaml
import json
from datetime import datetime, timedelta
from pathlib import Path

# 🛡️ Nexus Wiki Ownership & Review Audit (Agent V - v1.0)
# [NEXUS IDENTITY: a670624 + CI-GUARDED]

REPO_ROOT = Path(str(__import__("pathlib").Path(__file__).resolve().parents[2]))
VAULT_ROOT = REPO_ROOT / "nexus_wiki_vault"
REPORT_PATH = REPO_ROOT / ".nexus" / "reports" / "wiki_owner_report.json"

CORE_DIRS = ["00_Home", "06_Ops", "05_Protocols", "02_Modules"]

def run_owner_audit():
    print("🛡️ WS-V: Starting Ownership & Review SLA Audit...")
    all_mds = []
    for d in CORE_DIRS:
        all_mds.extend(list((VAULT_ROOT / d).glob("**/*.md")))
        
    missing_owner = []
    stale_review = []
    current_time = datetime.now()
    threshold_days = 30
    
    for md in all_mds:
        rel_md = str(md.relative_to(VAULT_ROOT))
        try:
            content = md.read_text(encoding="utf-8")
            if content.startswith("---"):
                _, frontmatter_text, _ = content.split("---", 2)
                data = yaml.safe_load(frontmatter_text)
                
                # Check Owner
                owner = data.get("owner")
                if not owner or owner == "unknown":
                    missing_owner.append(rel_md)
                
                # Check Stale (last_compiled)
                last_compiled_str = data.get("last_compiled")
                if last_compiled_str:
                    try:
                        last_compiled = datetime.strptime(str(last_compiled_str), "%Y-%m-%d")
                        if (current_time - last_compiled).days > threshold_days:
                            stale_review.append(rel_md)
                    except:
                        stale_review.append(rel_md)
                else:
                    stale_review.append(rel_md) # Missing date counts as stale
            else:
                missing_owner.append(rel_md)
                stale_review.append(rel_md)
        except:
            continue

    report = {
        "summary": {
            "missing_owner_count": len(missing_owner),
            "stale_review_count": len(stale_review),
            "total_core_pages": len(all_mds),
            "timestamp": current_time.isoformat()
        },
        "missing_owner": sorted(missing_owner),
        "stale_pages_top": sorted(stale_review)
    }
    
    os.makedirs(REPORT_PATH.parent, exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)
        
    print(f"📊 Owner Audit: {len(missing_owner)} Missing Owner, {len(stale_review)} Stale Review.")
    return 0

if __name__ == "__main__":
    run_owner_audit()
