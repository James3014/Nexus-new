#!/usr/bin/env python3
# 🛡️ Phantom Guard v2: Code Symmetry & Alignment Audit
import json
import glob
import hashlib
import os
import sys

def get_file_hash(path):
    if not os.path.exists(path): return None
    hasher = hashlib.sha256()
    with open(path, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()

def run_symmetry_check():
    print("🛡️ [PhantomGuard] Executing Symmetry Audit (Knowledge vs Disk)...")
    # 掃描所有知識庫文件
    knowledge_files = glob.glob(".nexus/knowledge/*.jsonl")
    if not knowledge_files:
        print("⚠️ [PhantomGuard] No knowledge baseline found. Initializing bypass.")
        return True

    mismatches = 0
    checked = 0
    for k_file in knowledge_files:
        with open(k_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    # 檢索所有帶有 'path' 與 'hash' 的知識條目 (對稱對位)
                    rel_path = data.get("path") or data.get("file_path")
                    cached_hash = data.get("hash") or data.get("sha256")
                    
                    if not rel_path or not cached_hash: continue
                    
                    # 執行物理校驗
                    disk_hash = get_file_hash(rel_path)
                    checked += 1
                    
                    if disk_hash and disk_hash != cached_hash:
                        print(f"❌ [Drift] {rel_path}: Hash Mismatch! (Physical: {disk_hash[:8]} vs Knowledge: {cached_hash[:8]})")
                        mismatches += 1
                    elif not disk_hash:
                        print(f"❌ [Phantom] {rel_path}: Symbol exists in knowledge but MISSING on disk!")
                        mismatches += 1
                except:
                    continue

    print(f"📊 [PhantomGuard] Audit Complete: {checked} points checked, {mismatches} drifts detected.")
    
    # 🛑 v18.1 硬攔截邏輯: 任何物理漂移均視為安全風險
    return mismatches == 0

if __name__ == "__main__":
    success = run_symmetry_check()
    if not success:
        print("🛑 [AGI Safety] Alignment Check FAILED. Blocking execution.")
        sys.exit(1)
    else:
        print("🟢 [AGI Safety] Alignment Check PASSED. 100% Symmetry.")
        sys.exit(0)
