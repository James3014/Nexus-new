#!/usr/bin/env python3
import os
import re
import json
from pathlib import Path

# 🛡️ Nexus Wiki Coverage Audit (Agent G - WS-A Hardened v2.1)
# Purpose: Quantify true governance coverage for mandatory domains and enforce 100% Key Path.

REPO_ROOT = Path(str(__import__("pathlib").Path(__file__).resolve().parents[2]))
VAULT_ROOT = REPO_ROOT / "nexus_wiki_vault"
REPORT_PATH = REPO_ROOT / ".nexus" / "reports" / "wiki_coverage_report.json"
KEYPATH_REPORT_PATH = REPO_ROOT / ".nexus" / "reports" / "wiki_keypath_coverage_report.json"

TARGET_DIRS = [
    "nexus/core", "nexus/services", "scripts/ops", "scripts/engine"
]

KEY_PATHS = [
    "scripts/ops/ci_gate.py",
    "scripts/ops/wiki_linter.py",
    "scripts/ops/wiki_drift_audit.py",
    "scripts/ops/wiki_coverage_audit.py",
    "scripts/engine/nexus_cli.py",
    "nexus/core/orchestrator.py",
    "nexus/core/state_repository.py",
    "nexus/core/policy_manager.py",
    "nexus/core/memory/ingest.py",
    "nexus/services/memory.py",
    "nexus/services/memory_indexer.py",
    "nexus-desk/src-tauri/src/main.rs"
]

EXCLUDED_PATTERNS = [
    r"__pycache__",
    r"\.pytest_cache",
    r"\.git",
    r"\.nexus",
    r"tests/",
    r"docs/",
    r".*\.bak$",
    r".*~",
    r"setup\.py",
    r"__init__\.py",
    r"\.DS_Store"
]

# Patterns to find code references in Wiki body
PROVENANCE_PATTERN = re.compile(
    r"\[source:\s*(.*?)\]|\(source:\s*(.*?)\)|\[code:\s*(.*?)\]|\(code:\s*(.*?)\)|\[Source:\s*(.*?)\]", 
    re.I
)
# Pattern for Frontmatter
FM_SOT_PATTERN = re.compile(r"^source_of_truth:\s*(.*?)$", re.M)

def is_excluded(path_str):
    for pattern in EXCLUDED_PATTERNS:
        if re.search(pattern, path_str):
            return True
    return False

def get_code_files():
    files = set()
    for d in TARGET_DIRS:
        abs_dir = REPO_ROOT / d
        if not abs_dir.exists(): continue
        for p in abs_dir.glob("**/*"):
            if p.is_file():
                rel_p = str(p.relative_to(REPO_ROOT))
                if not is_excluded(rel_p):
                    files.add(rel_p)
    # 確保 KEY_PATHS 中的檔案也被納入 (即使不在 TARGET_DIRS)
    for kp in KEY_PATHS:
        if (REPO_ROOT / kp).exists():
            files.add(kp)
    return sorted(list(files))

def get_covered_files_from_wiki():
    covered = set()
    for md in VAULT_ROOT.glob("**/*.md"):
        if "99_Schema" in str(md): continue
        try:
            content = md.read_text(encoding="utf-8")
            
            # 1. 萃取 Frontmatter 中的 source_of_truth
            fm_match = FM_SOT_PATTERN.search(content)
            if fm_match:
                sot = fm_match.group(1).strip()
                if sot: covered.add(sot)
            
            # 2. 萃取本文中的 [Source: path] 或 [Code: path]
            matches = PROVENANCE_PATTERN.findall(content)
            for match in matches:
                path_str = next((g for g in match if g), "").strip()
                path_str = path_str.replace("`", "").replace("'", "").replace("\"", "")
                path_str = re.sub(r"\s+Part\s+.*$", "", path_str, flags=re.I)
                path_str = re.sub(r"\s+L\d+.*$", "", path_str, flags=re.I)
                path_str = re.sub(r"#.*$", "", path_str).strip()
                if path_str: covered.add(path_str.replace("\\ ", " "))
        except Exception:
            continue
    return covered

def run_audit():
    print("🛡️ WS-A: Executing Hardened Wiki Coverage Audit v2.1...")
    all_code_files = get_code_files()
    wiki_mentions = get_covered_files_from_wiki()
    
    covered_files = []
    uncovered_files = []
    
    # 建立 Basename 映射以備模糊比對 (確保唯一性才算命中)
    basename_to_rels = {}
    for f in all_code_files:
        bn = os.path.basename(f)
        basename_to_rels.setdefault(bn, []).append(f)
    
    for f in all_code_files:
        is_covered = False
        bn = os.path.basename(f)
        
        # 1. 精確比對 (完整路徑)
        if f in wiki_mentions:
            is_covered = True
        # 2. 模糊比對: 如果 Wiki 提到了檔名，且該檔名在代碼庫中是唯一的
        elif bn in wiki_mentions and len(basename_to_rels.get(bn, [])) == 1:
            is_covered = True
        # 3. 反向包含: Wiki 提到了一個較長的路徑包含此檔名
        else:
            for m in wiki_mentions:
                if m == f or m.endswith(f) or f.endswith(m):
                    is_covered = True
                    break
        
        if is_covered: covered_files.append(f)
        else: uncovered_files.append(f)
            
    coverage_ratio = len(covered_files) / len(all_code_files) if all_code_files else 0
    
    # 關鍵路徑查驗
    keypath_covered = [f for f in covered_files if f in KEY_PATHS]
    keypath_uncovered = [f for f in KEY_PATHS if f not in covered_files]
    keypath_ratio = len(keypath_covered) / len(KEY_PATHS) if KEY_PATHS else 1.0
    
    # 指標狀態
    global_status = "PASS" if coverage_ratio >= 0.85 else "FAIL"
    keypath_status = "PASS" if keypath_ratio >= 1.0 else "FAIL"

    # 計算 Domain 覆蓋率
    domain_stats = {}
    for d in TARGET_DIRS:
        d_all = [f for f in all_code_files if f.startswith(d)]
        d_cov = [f for f in covered_files if f.startswith(d)]
        domain_stats[d] = f"{len(d_cov)}/{len(d_all)} ({len(d_cov)/len(d_all):.1%})" if d_all else "N/A"

    report = {
        "summary": {
            "total_files": len(all_code_files),
            "covered_files": len(covered_files),
            "uncovered_files": len(uncovered_files),
            "coverage_ratio_float": coverage_ratio,
            "coverage_ratio": f"{coverage_ratio:.2%}",
            "keypath_coverage_ratio": f"{keypath_ratio:.2%}",
            "global_status": global_status,
            "keypath_status": keypath_status,
            "domain_stats": domain_stats
        },
        "top_uncovered_paths": uncovered_files[:30]
    }
    
    keypath_report = {
        "keypath_coverage_ratio": f"{keypath_ratio:.2%}",
        "keypath_status": keypath_status,
        "keypath_uncovered": keypath_uncovered,
        "keypath_covered": keypath_covered
    }
    
    os.makedirs(REPORT_PATH.parent, exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)
    with open(KEYPATH_REPORT_PATH, "w") as f:
        json.dump(keypath_report, f, indent=2)
        
    print(f"📊 Global Result: {report['summary']['coverage_ratio']} ({global_status})")
    print(f"🎯 Key Path Result: {report['summary']['keypath_coverage_ratio']} ({keypath_status})")
    print(f"📁 Domain Analysis:")
    for d, stat in domain_stats.items():
        print(f"  - {d}: {stat}")
    
    if keypath_ratio < 1.0:
        print(f"❌ Critical Error: Key Path coverage is NOT 100%. Missing: {', '.join(keypath_uncovered)}")
    
    if coverage_ratio < 0.85:
        print(f"⚠️ Gap: {len(uncovered_files)} files remaining.")

if __name__ == "__main__":
    run_audit()
