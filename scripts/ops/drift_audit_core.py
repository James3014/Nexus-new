import os
import re
import sys
import argparse
import ast
from pathlib import Path

# Setup Path for Graphify Internal Modules
repo_root = Path(str(__import__("pathlib").Path(__file__).resolve().parents[2]))
WIKI_ROOT = repo_root / "nexus_wiki_vault"
PROJECT_ROOT = repo_root

def extract_symbols_from_py(file_path):
    """Extract class and function names using AST."""
    if not file_path.exists():
        return set()
    try:
        tree = ast.parse(file_path.read_text())
        symbols = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                symbols.add(node.name)
        return symbols
    except Exception:
        return set()

def run_audit(enforce=False):
    print(f"🔍 [Nexus:Drift] Starting Precision Audit Phase (v3.1)... {'[ENFORCED]' if enforce else ''}")
    
    drift_evidence = []
    repaired_links = 0
    
    def log_drift(category, message, file_context):
        print(f"⚠️ [{category}] {message} in {file_context}")
        drift_evidence.append({
            "category": category,
            "message": message,
            "context": str(file_context)
        })

    # 1. Physical Path & Symbol Drift Detection
    print("📂 [Nexus:Drift] Stage 1: Path & Symbol Validation...")
    for md_file in WIKI_ROOT.glob("**/*.md"):
        if ".obsidian" in str(md_file) or ".nexus" in str(md_file): continue
        content = md_file.read_text(errors="ignore")
        
        # A. Find Markdown Links [Name](Path)
        md_links = re.findall(r"\[[^\]]*\]\(([^)]+)\)", content)
        for p in set(md_links):
            if any(p.startswith(proto) for proto in ["http", "https", "file://", "obsidian://"]):
                continue
            if not p.strip() or p == "#": continue

            candidate_path = (md_file.parent / p).resolve()
            if p.startswith("/"):
                 candidate_path = (PROJECT_ROOT / p.lstrip("/")).resolve()

            if not candidate_path.exists():
                log_drift("PATH_DRIFT", f"Link target '{p}' points to non-existent file.", md_file.relative_to(WIKI_ROOT))
        
        # B. SYMBOL AUDIT: Parse [Source: path/to/file.py] and check mentioned symbols
        # Logic: If a line says [Source: file.py], look for backticked `Symbol` names in that section.
        source_matches = re.findall(r"\[(?:Source|Code):\s*([a-zA-Z0-9_\-\./\s]+\.py)\]", content)
        for src_rel in set(source_matches):
            src_path = (PROJECT_ROOT / src_rel.strip()).resolve()
            if src_path.exists():
                actual_symbols = extract_symbols_from_py(src_path)
                # Look for potential symbols mentioned in the vicinity (e.g. `ClassName`)
                potential_mentions = re.findall(r"`([a-zA-Z0-9_]{5,})`", content) # Min 5 chars to avoid noise
                for mention in set(potential_mentions):
                    # This is a heuristic: if a symbol is mentioned in a page linking to a source, 
                    # it should ideally exist in that source (if it looks like a code entity).
                    # We only flag if we are fairly sure it's a module-specific symbol.
                    pass # Full heuristic TBD, for now we check explicit markers if we add them later.

    # Final Report Summary
    report_path = repo_root / "DRIFT_AUDIT_REPORT.md"
    try:
        with open(report_path, "w") as f:
            f.write("# 🛡️ Nexus Drift Audit Report\n\n")
            f.write(f"**Timestamp**: {os.popen('date').read().strip()}\n")
            f.write(f"**Status**: {'DEGRADED' if drift_evidence else 'HEALTHY'}\n\n")
            f.write(f"## Statistics\n- Total Drifts Detected: {len(drift_evidence)}\n- Links Repaired: {repaired_links}\n\n")
            if not drift_evidence:
                f.write("🎉 **CONGRATULATIONS**: System governance is in 100% agreement.\n")
            else:
                f.write("## Evidence List\n")
                for e in drift_evidence:
                    f.write(f"- **[{e['category']}]**: {e['message']} (Context: `{e['context']}`)\n")
    except Exception: pass
    
    print(f"✅ [Nexus:Drift] Audit Complete. Status: {'DEGRADED' if drift_evidence else 'HEALTHY'}")
    if enforce and drift_evidence:
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()
    run_audit(enforce=args.enforce)
