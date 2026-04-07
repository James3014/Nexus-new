import os
import re
import sys
from pathlib import Path

# Setup Path for Graphify Internal Modules
repo_root = Path("/Users/jameschen/Workspace/nexus")
WIKI_ROOT = repo_root / "nexus_wiki_vault"
PROJECT_ROOT = repo_root

print("🔍 [Nexus:Drift] Starting Precision Audit Phase (v2)...")

drift_evidence = []
repaired_links = 0

def log_drift(category, message, file_context):
    print(f"⚠️ [{category}] {message} in {file_context}")
    drift_evidence.append({
        "category": category,
        "message": message,
        "context": str(file_context)
    })

# 1. Physical Path Drift Detection (Markdown Aware)
print("📂 [Nexus:Drift] Stage 1: Markdown-Link Physical Validation...")

for md_file in WIKI_ROOT.glob("**/*.md"):
    if ".obsidian" in str(md_file): continue
    content = md_file.read_text(errors="ignore")
    
    # Identify Markdown Links [Name](Path)
    # This regex now supports spaces and relative dots
    md_links = re.findall(r"\[[^\]]*\]\(([^)]+)\)", content)
    
    for p in set(md_links):
        # Filter non-file system protocols
        if any(p.startswith(proto) for proto in ["http", "https", "file://", "obsidian://"]):
            continue
        
        # Calculate physical path relative to the current file
        # IMPORTANT: Wiki links are often relative to the current file
        candidate_path = (md_file.parent / p).resolve()
        
        # Also check if it's relative to Project Root (for absolute-style paths /scripts/...)
        if p.startswith("/"):
             candidate_path = (PROJECT_ROOT / p.lstrip("/")).resolve()

        if not candidate_path.exists():
            # Check if it might be an intentional reference to a non-existent file?
            # In governance, it's a drift.
            log_drift("PATH_DRIFT", f"Link target '{p}' points to non-existent file.", md_file.relative_to(WIKI_ROOT))
            
            # ATTEMPT REPAIR only if it's a basename that exists elsewhere
            filename = Path(p).name
            if filename:
                matches = list(WIKI_ROOT.glob(f"**/{filename}")) + list(PROJECT_ROOT.glob(f"**/{filename}"))
                if matches and not ".obsidian" in str(matches[0]):
                    # Check for ambiguous matches
                    if len(set(matches)) == 1:
                        new_rel = os.path.relpath(matches[0], md_file.parent)
                        print(f"🔧 [Nexus:Repair] Auto-compensating: {p} -> {new_rel}")
                        new_content = content.replace(f"({p})", f"({new_rel})")
                        md_file.write_text(new_content)
                        repaired_links += 1

# Final Report Summary
report_path = repo_root / "DRIFT_AUDIT_REPORT.md"
with open(report_path, "w") as f:
    f.write("# 🛡️ Nexus Drift Audit Report\n\n")
    f.write(f"**Timestamp**: {os.popen('date').read().strip()}\n")
    f.write(f"**Status**: {'DEGRADED' if drift_evidence else 'HEALTHY'}\n\n")
    f.write(f"## Statistics\n- Total Drifts Detected: {len(drift_evidence)}\n- Links Repaired: {repaired_links}\n\n")
    if not drift_evidence:
        f.write("🎉 **CONGRATULATIONS**: System governance is in 100% agreement. No topology drift detected.\n")
    else:
        f.write("## Evidence List\n")
        for e in drift_evidence:
            f.write(f"- **[{e['category']}]**: {e['message']} (Context: `{e['context']}`)\n")

print(f"✅ [Nexus:Drift] Audit Complete. Status: {'DEGRADED' if drift_evidence else 'HEALTHY'}")
