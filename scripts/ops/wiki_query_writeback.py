#!/usr/bin/env python3
import os
import json
import argparse
import datetime
from pathlib import Path

# 🛡️ Nexus Wiki Query Writeback v1.1
# Purpose: Automate the conversion of high-value query results into Wiki documentation.
# Policy: nexus_wiki_vault/06_Ops/Ops - Query Writeback Policy.md

REPO_ROOT = Path(str(__import__("pathlib").Path(__file__).resolve().parents[2]))
VAULT_ROOT = REPO_ROOT / "nexus_wiki_vault"
REPORT_PATH = REPO_ROOT / ".nexus" / "reports" / "wiki_writeback_report.json"

MANDATORY_METADATA = [
    "query_context", 
    "evidence_link", 
    "timestamp", 
    "confidence_score"
]

def validate_metadata(metadata):
    missing = [k for k in MANDATORY_METADATA if k not in metadata]
    return missing

def format_wiki_page(title, content, metadata):
    frontmatter = "---\n"
    frontmatter += f"title: {title}\n"
    frontmatter += "type: discovery\n"
    frontmatter += "status: draft\n"
    for k, v in metadata.items():
        frontmatter += f"{k}: {v}\n"
    frontmatter += "---\n\n"
    
    body = f"# {title}\n\n"
    body += "## One-sentence summary\nAuto-generated from query writeback.\n\n"
    body += "## Role / responsibility\nPersistence of dynamic discovery.\n\n"
    body += "## Content\n" + content + "\n\n"
    body += "## Source notes\n[source: scripts/ops/wiki_query_writeback.py]\n"
    
    return frontmatter + body

def perform_writeback(title, content, metadata, apply=False):
    missing = validate_metadata(metadata)
    if missing:
        return False, f"Missing mandatory metadata: {missing}"
    
    page_content = format_wiki_page(title, content, metadata)
    file_name = title.replace(" ", "_").lower() + ".md"
    # Write to 08_Analysis for new discoveries
    target_path = VAULT_ROOT / "08_Analysis" / file_name
    
    if apply:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(page_content)
        return True, f"Written to {target_path}"
    else:
        return True, f"[DRY-RUN] Would write to {target_path}"

def main():
    parser = argparse.ArgumentParser(description="🛡️ Nexus Wiki Query Writeback Automation")
    parser.add_argument("--apply", action="store_true", help="Apply changes to Wiki")
    parser.add_argument("--dry-run", action="store_true", help="Audit only (default, kept for compatibility)")
    parser.add_argument("--input-json", type=str, help="Path to JSON file for batch ingestion")
    parser.add_argument("--title", type=str, help="Title of the new Wiki page")
    parser.add_argument("--content", type=str, help="Content of the new Wiki page")
    parser.add_argument("--metadata-json", type=str, help="JSON string of metadata")
    
    args = parser.parse_args()
    
    stats = {
        "received": 0,
        "valid": 0,
        "written": 0,
        "skipped": 0,
        "failed": 0
    }
    
    items = []
    if args.input_json:
        input_path = Path(args.input_json)
        if input_path.exists():
            items = json.loads(input_path.read_text())
            if not isinstance(items, list):
                items = [items]
        else:
            print(f"❌ Input file not found: {args.input_json}")
            return
    elif args.title:
        metadata = json.loads(args.metadata_json) if args.metadata_json else {}
        items = [{
            "title": args.title,
            "content": args.content,
            "metadata": metadata
        }]

    if not items:
        print("🛡️ Nexus Wiki Query Writeback: No input provided. Initializing report...")
        report = {
            "timestamp": str(datetime.datetime.now()),
            "status": "ready",
            "policy_link": "nexus_wiki_vault/06_Ops/Ops - Query Writeback Policy.md",
            "enforced_keys": MANDATORY_METADATA,
            "summary": stats,
            "recent_writebacks": []
        }
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(REPORT_PATH, "w") as f:
            json.dump(report, f, indent=2)
        print(f"Report initialized at {REPORT_PATH}")
        return

    results = []
    for item in items:
        stats["received"] += 1
        title = item.get("title")
        content = item.get("content")
        metadata = item.get("metadata", {})
        
        if "timestamp" not in metadata:
            metadata["timestamp"] = str(datetime.datetime.now())
            
        success, msg = perform_writeback(title, content, metadata, apply=args.apply)
        
        if success:
            stats["valid"] += 1
            if args.apply:
                stats["written"] += 1
            else:
                stats["skipped"] += 1
        else:
            stats["failed"] += 1
            
        print(f"{'✅' if success else '❌'} {msg}")
        results.append({
            "title": title,
            "success": success,
            "message": msg,
            "timestamp": metadata.get("timestamp"),
            "apply": args.apply
        })
    
    # Update Report
    report = {
        "timestamp": str(datetime.datetime.now()),
        "summary": stats,
        "recent_writebacks": results
    }
    
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Report saved to: {REPORT_PATH}")

if __name__ == "__main__":
    main()
