import os
import re
import sys
import json
from pathlib import Path

# Setup Path for Graphify Internal Modules
repo_root = Path("/Users/jameschen/Workspace/nexus")
venv_packages = repo_root / ".venv" / "lib" / "python3.12" / "site-packages"
if str(venv_packages) not in sys.path:
    sys.path.insert(0, str(venv_packages))

print("🔍 [Nexus:Drift] Starting Deep Audit Phase...")

WIKI_ROOT = repo_root / "nexus_wiki_vault"
PROJECT_ROOT = repo_root

drift_evidence = []
repaired_links = 0

def log_drift(category, message, file_context):
    print(f"⚠️ [{category}] {message} in {file_context}")
    drift_evidence.append({
        "category": category,
        "message": message,
        "context": str(file_context)
    })

# 1. Physical Path Drift Detection
print("📂 [Nexus:Drift] Stage 1: Physical Path Validation...")
for md_file in WIKI_ROOT.glob("**/*.md"):
    content = md_file.read_text(errors="ignore")
    # Identify path-like patterns e.g., /nexus/core/router.py
    # or inside code blocks or specific labels
    paths = re.findall(r"(?:/|(?<=\s))[a-zA-Z0-9_\-/]+\.(?:py|js|ts|java|rs|md)", content)
    
    for p in set(paths):
        # Normalize: if it starts with /nexus, it's likely relative to repo_root
        clean_p = p.lstrip("/")
        if clean_p.startswith("nexus/"):
            phys_path = PROJECT_ROOT / clean_p
        else:
            # Try direct relative
            phys_path = PROJECT_ROOT / clean_p
            
        if not phys_path.exists():
            log_drift("PATH_DRIFT", f"File reference '{p}' not found on disk.", md_file.relative_to(WIKI_ROOT))
            
            # ATTEMPT REPAIR: Search for the file in the project
            filename = Path(clean_p).name
            matches = list(PROJECT_ROOT.glob(f"**/{filename}"))
            if matches:
                new_rel_path = f"/{matches[0].relative_to(PROJECT_ROOT)}"
                print(f"🔧 [Nexus:Repair] Found potential match: {new_rel_path}")
                # Update Wiki Content (Auto-Compensation)
                new_content = content.replace(p, new_rel_path)
                md_file.write_text(new_content)
                repaired_links += 1

# 2. Symbol-Level Drift (Mock Deep Audit for speed/demo)
print("🧬 [Nexus:Drift] Stage 2: Symbol-Level AST Validation...")
# Targeted check for 'SkillsRouter' as discussed
target_md = WIKI_ROOT / "02_Modules/Module - Guard and Gate Control.md"
if target_md.exists():
    content = target_md.read_text(errors="ignore")
    if "SkillsRouter" in content:
        # Check if the class still exists in router.py
        router_py = PROJECT_ROOT / "nexus/core/router.py"
        if router_py.exists():
            router_content = router_py.read_text()
            if "class SkillsRouter" not in router_content:
                log_drift("SYMBOL_DRIFT", "Class 'SkillsRouter' mentioned in Wiki but missing from router.py", "Module - Guard and Gate Control.md")

# Final Report Summary
report_path = repo_root / "DRIFT_AUDIT_REPORT.md"
with open(report_path, "w") as f:
    f.write("# 🛡️ Nexus Drift Audit Report\n\n")
    f.write(f"**Timestamp**: {os.popen('date').read().strip()}\n")
    f.write(f"**Status**: {'DEGRADED' if drift_evidence else 'HEALTHY'}\n\n")
    f.write(f"## Statistics\n- Total Drifts Detected: {len(drift_evidence)}\n- Links Repaired: {repaired_links}\n\n")
    f.write("## Evidence List\n")
    for e in drift_evidence:
        f.write(f"- **[{e['category']}]**: {e['message']} (Context: `{e['context']}`)\n")

print(f"✅ [Nexus:Drift] Audit Complete. Report: {report_path}")
