#!/usr/bin/env python3
import os
import re
import json
from pathlib import Path

# 🛡️ Nexus Wiki Link Integrity Audit (Agent U - v1.0)
# [NEXUS IDENTITY: a670624 + CI-GUARDED]

REPO_ROOT = Path(str(__import__("pathlib").Path(__file__).resolve().parents[2]))
VAULT_ROOT = REPO_ROOT / "nexus_wiki_vault"
REPORT_PATH = REPO_ROOT / ".nexus" / "reports" / "wiki_link_report.json"

WIKILINK_PATTERN = re.compile(r"\[\[(.*?)\]\]")

def run_link_audit():
    print("🛡️ WS-U: Starting Wiki Link Integrity Audit...")
    all_mds = list(VAULT_ROOT.glob("**/*.md"))
    page_map = {} # basename -> rel_path
    
    # 1. Map all valid pages
    for md in all_mds:
        if "99_Schema" in str(md): continue
        page_map[md.stem] = str(md.relative_to(VAULT_ROOT))

    inbound_links = {p: [] for p in page_map.keys()}
    broken_links = []
    
    # 2. Parse links
    for md in all_mds:
        if "99_Schema" in str(md): continue
        rel_md = str(md.relative_to(VAULT_ROOT))
        content = md.read_text(encoding="utf-8")
        links = WIKILINK_PATTERN.findall(content)
        
        for link in links:
            # Handle aliases [[Target|Alias]]
            target = link.split("|")[0].strip()
            if target in page_map:
                inbound_links[target].append(rel_md)
            else:
                broken_links.append({"from": rel_md, "target": target})

    # 3. Detect Orphans (Exclude systemic base pages)
    SYSTEMIC_PAGES = ["System Overview"]
    orphans = [p for p, links in inbound_links.items() if not links and p not in SYSTEMIC_PAGES]

    report = {
        "summary": {
            "orphan_count": len(orphans),
            "broken_link_count": len(broken_links),
            "total_pages": len(page_map),
            "timestamp": os.path.getmtime(VAULT_ROOT) # Using vault mtime as proxy
        },
        "orphans": sorted(orphans),
        "broken_details": broken_links
    }
    
    os.makedirs(REPORT_PATH.parent, exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)
        
    print(f"📊 Link Audit: {len(orphans)} Orphans, {len(broken_links)} Broken Links.")
    return 0

if __name__ == "__main__":
    run_link_audit()
