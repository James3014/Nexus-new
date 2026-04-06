#!/usr/bin/env python3
import os
import re
import json
import subprocess
from pathlib import Path
from datetime import datetime
from collections import Counter

# 🛡️ Nexus Wiki Drift Audit (Agent Q - WS-I Hardened v3.1)
# [NEXUS IDENTITY: 06624d2 + CI-GUARDED]

REPO_ROOT = Path("/Users/jameschen/Workspace/nexus")
VAULT_ROOT = REPO_ROOT / "nexus_wiki_vault"
REPORT_PATH = REPO_ROOT / ".nexus" / "reports" / "wiki_drift_report.json"

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

# Exclusion list for recording-type pages (Agent Q)
EXCLUDE_PAGES = [
    "06_Ops/Ops - Governance Changelog.md",
    "06_Ops/Ops - Wiki Drift Audit.md",
    "90_Sources/Source Index.md",
    "90_Sources/Source - Coverage Heatmap.md",
    "90_Sources/Source - Operational Scripts Index.md"
]

# Bare filename whitelist for normalization (Agent Q+ v3.2)
BARE_FILENAME_MAP = {
    "ci_gate.py": "scripts/ops/ci_gate.py",
    "wiki_linter.py": "scripts/ops/wiki_linter.py",
    "wiki_coverage_audit.py": "scripts/ops/wiki_coverage_audit.py",
    "wiki_truth_claims_check.py": "scripts/ops/wiki_truth_claims_check.py",
    "wiki_drift_audit.py": "scripts/ops/wiki_drift_audit.py",
    "nexus_cli.py": "scripts/engine/nexus_cli.py",
    "handoff_bundle.py": "nexus/core/handoff_bundle.py",
    "errors.py": "nexus/core/errors.py",
    "orchestrator.py": "nexus/core/orchestrator.py",
    "memory_indexer.py": "nexus/services/memory_indexer.py",
    "cleanup_policy_memory.py": "scripts/ops/cleanup_policy_memory.py"
}

PROVENANCE_PATTERN = re.compile(r"\[(source|code|Source|Code):\s*(.*?)\]|\((source|code|Source|Code):\s*(.*?)\)", re.I)
IGNORE_LABELS = ["Reference", "Page", "Spec", "Module", "System Overview"]

def get_git_mtime(path_str):
    try:
        res = subprocess.check_output(
            ["git", "log", "-1", "--format=%ct", path_str],
            cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
        return int(res) if res else 0
    except:
        return 0

def normalize_path(path_str):
    p = path_str.strip().replace("`", "").replace("'", "").replace("\"", "")
    p = re.sub(r"\s+Part\s+.*$", "", p, flags=re.I)
    p = re.sub(r"\s+L\d+.*$", "", p, flags=re.I)
    p = re.sub(r"#.*$", "", p)
    p = p.replace("\\ ", " ").strip()
    if p in BARE_FILENAME_MAP:
        return BARE_FILENAME_MAP[p]
    return p

def run_drift_audit():
    print("🛡️ WS-I: Starting Hardened Wiki Drift Audit v3.1 (Agent Q)...")
    claims = []
    seen_keys = set()
    raw_total = 0
    p0_count = 0
    p1_count = 0
    p2_count = 0
    
    p1_reasons = Counter()
    p1_pages = Counter()
    
    current_time = datetime.now().timestamp()
    p1_threshold = 45 * 24 * 60 * 60
    # Exclusion lists for auto-generated paths
    EXCLUDE_PATHS = ["wiki_audit.json", "ci_benchmark.csv", "wiki_coverage_report.json"]

    # 1. Load Previous Report if exists to calculate delta
    prev_total = 0
    if REPORT_PATH.exists():
        try:
            prev_total = json.loads(REPORT_PATH.read_text())["summary"]["total_drifts"]
        except: pass

    for md in VAULT_ROOT.glob("**/*.md"):
        if "99_Schema" in str(md): continue
        try:
            content = md.read_text(encoding="utf-8")
            matches = PROVENANCE_PATTERN.findall(content)
            rel_md = str(md.relative_to(VAULT_ROOT))
            
            for match in matches:
                # regex capture logic: 
                # [label: value] -> group(0)=label, group(1)=value or pattern based
                # Here we use a generic extract
                full_match = "".join([str(g) for g in match if g])
                if ":" not in full_match: continue
                
                label, path_str = full_match.split(":", 1)
                label = label.strip()
                path_str = path_str.strip()
                
                if label in IGNORE_LABELS or not path_str or "://" in path_str or path_str.startswith("/"):
                    continue
                
                raw_total += 1
                clean_path = normalize_path(path_str)
                if not clean_path: continue
                
                abs_path = REPO_ROOT / clean_path
                exists = abs_path.exists()
                git_mtime = get_git_mtime(clean_path) if exists else 0
                page_mtime = os.path.getmtime(md)
                
                age = current_time - page_mtime
                is_keypath = clean_path in KEY_PATHS
                is_recording_page = rel_md in EXCLUDE_PAGES or rel_md.startswith("90_Sources/Source - ")
                is_code = any(clean_path.endswith(ext) for ext in [".py", ".rs", ".sh", ".ts", ".tsx"])

                # Drift Reason Classification (Agent Q)
                reason = "INFO"
                level = "INFO"
                
                if not exists:
                    reason = "missing_path"
                    if is_keypath: level = "P0"
                    else: level = "P1"
                elif is_code and clean_path not in EXCLUDE_PATHS and not is_recording_page:
                    if is_keypath and age > p1_threshold:
                        reason = "stale_keypath"
                        level = "P1"
                    elif age > (60 * 24 * 60 * 60) or page_mtime < git_mtime:
                        reason = "stale_non_keypath"
                        level = "P2"
                elif rel_md.endswith(".md") and clean_path.endswith(".md"):
                    reason = "wiki_wiki_link"
                    level = "INFO"

                # Deduplication Key (Agent Q: Normalized Page + Normalized Target + Reason + Level)
                dedup_key = (rel_md, clean_path, reason, level)
                if dedup_key in seen_keys:
                    p1_reasons["duplicate_ref"] += 1
                    continue
                seen_keys.add(dedup_key)

                if level == "P1":
                    p1_count += 1
                    p1_reasons[reason] += 1
                    p1_pages[rel_md] += 1
                elif level == "P2": p2_count += 1
                elif level == "P0": p0_count += 1

                claims.append({
                    "id": f"{rel_md} -> {clean_path}",
                    "level": level,
                    "reason": reason,
                    "page": rel_md,
                    "target": clean_path,
                    "exists": exists,
                    "stale": (page_mtime < git_mtime) if exists else True
                })
        except Exception as e:
            print(f"Error reading {md}: {e}")
            continue

    dedup_total = len(claims)
    dedup_ratio = (1 - dedup_total / raw_total) * 100 if raw_total > 0 else 0
    delta = dedup_total - prev_total if prev_total > 0 else 0

    report = {
        "summary": {
            "p0_count": p0_count,
            "p1_count": p1_count,
            "p2_count": p2_count,
            "total_drifts": p0_count + p1_count + p2_count,
            "raw_total": raw_total,
            "dedup_total": dedup_total,
            "dedup_ratio": f"{dedup_ratio:.2f}%",
            "suppression_delta_vs_prev": delta,
            "p1_by_reason": dict(p1_reasons),
            "p1_by_page_top10": dict(p1_pages.most_common(10)),
            "p1_keypath_only_count": p1_reasons.get("stale_keypath", 0) + p1_reasons.get("missing_path", 0) if p0_count == 0 else 0,
            "blocking": p0_count > 0,
            "timestamp": datetime.now().isoformat()
        },
        "drifts": sorted(claims, key=lambda x: x["level"])
    }
    
    os.makedirs(REPORT_PATH.parent, exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)
        
    print(f"📊 Result: P0={p0_count}, P1={p1_count}, P2={p2_count}")
    print(f"📉 Suppression: {raw_total} -> {dedup_total} ({dedup_ratio:.2f}% reduction)")
    print(f"📌 P1 Breakdown: {dict(p1_reasons)}")
    
    return 1 if (p0_count > 0) else 0

if __name__ == "__main__":
    exit(run_drift_audit())
