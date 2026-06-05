import os
import time
import fnmatch
import logging
from typing import List, Dict, Any
from pathlib import Path
from nexus.bridge.dual_run import DualRunComparator, MismatchLedger, MismatchEntry

logger = logging.getLogger(__name__)

class FastMatcherBridge:
    """
    🦀 Rust FastMatcher Bridge (v1 Shadow Mode)
    負責在 Python Orchestrator 中 Dual-run Python 與 Rust 掃描核心。
    """
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.ledger = MismatchLedger(project_root / ".nexus/reports/rust_mismatch.jsonl")
        self.comparator = DualRunComparator(self.ledger)
        
        # 嘗試載入 Rust 核心
        try:
            import nexus_core
            self.rust_available = True
            self.rust_core = nexus_core
        except ImportError:
            self.rust_available = False
            self.rust_core = None

    def py_scan(self, root: str, patterns: List[str]) -> List[str]:
        """與 Rust 等價的 Python 實作 (用於比對)"""
        results = []
        
        # 讀取 .gitignore 中被忽略的樣式
        ignore_patterns = []
        gitignore_path = os.path.join(root, '.gitignore')
        if os.path.exists(gitignore_path):
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        ignore_patterns.append(line)
        
        for root_dir, dirs, files in os.walk(root):
            # 1. inplace 過濾目錄以避免 os.walk 遍歷它們
            dirs[:] = [
                d for d in dirs 
                if not d.startswith('.') 
                and d not in ['__pycache__', 'node_modules', 'target', 'scratch', 'perplexity']
                and not any(ip.strip('/') == d for ip in ignore_patterns if ip.endswith('/'))
            ]
            
            for filename in files:
                # 2. 過濾隱藏檔案
                if filename.startswith('.'):
                    continue
                    
                full_path = os.path.join(root_dir, filename)
                rel_path = os.path.relpath(full_path, root)
                
                # 3. 過濾路徑組件中包含被忽略目錄的項目
                parts = Path(rel_path).parts
                if any(p.startswith('.') or p in ['target', 'scratch', 'perplexity'] for p in parts):
                    continue
                    
                # 4. 過濾符合 .gitignore 的檔案和通配符
                is_ignored = False
                for ip in ignore_patterns:
                    if ip.endswith('/'):
                        clean_ip = ip.strip('/')
                        if rel_path.startswith(clean_ip) or f"/{clean_ip}/" in rel_path:
                            is_ignored = True
                            break
                    else:
                        if fnmatch.fnmatch(rel_path, ip) or fnmatch.fnmatch(filename, ip):
                            is_ignored = True
                            break
                if is_ignored:
                    continue
                    
                if not patterns:
                    results.append(rel_path)
                else:
                    if any(fnmatch.fnmatch(rel_path, p) for p in patterns):
                        results.append(rel_path)
        return sorted(results)





    def scan(self, patterns: List[str], use_shadow: bool = True) -> List[str]:
        """執行掃描，若開啟 Shadow Mode 則執行 Dual-run"""
        root_str = str(self.project_root.absolute())
        
        # 1. Primary: Python
        start_py = time.time()
        py_results = self.py_scan(root_str, patterns)
        py_time = time.time() - start_py
        
        # 2. Shadow: Rust (若可用)
        if use_shadow and self.rust_available:
            try:
                start_rs = time.time()
                rs_meta = self.rust_core.fast_scan(root_str, patterns)
                rs_time = time.time() - start_rs
                
                # 轉化為與 Python 等價的列表格式
                # 需將絕對路徑轉回相對路徑以進行比對
                rs_results = sorted([
                    os.path.relpath(m.path, root_str) for m in rs_meta
                ])
                
                # 3. 執行比對並記錄 Ledger
                py_set = set(py_results)
                rs_set = set(rs_results)
                
                # 核心指標對位 (排除 time_s 與 hash 隨機性)
                match = (len(py_set) == len(rs_set)) and (py_set == rs_set)
                
                if not match:
                    only_py = sorted(list(py_set - rs_set))
                    only_rs = sorted(list(rs_set - py_set))
                    
                    diff_details = {
                        "py_only_count": len(only_py),
                        "rs_only_count": len(only_rs),
                        "mismatch_samples": only_py[:10]
                    }

                    entry = MismatchEntry(
                        module_name="FastMatcher",
                        input_hash=str(hash(str({"patterns": patterns, "root": root_str}))),
                        py_output={"count": len(py_results)},
                        rs_output={"count": len(rs_results)},
                        match=False,
                        diff_reason="SET_MISMATCH",
                        diff_details=diff_details
                    )
                    self.ledger.record_mismatch(entry)
                else:
                    logger.info(f"✅ [Shadow] FastMatcher parity check passed. Count: {len(py_results)}")
                    
            except Exception as e:
                print(f"⚠️ [Shadow] Rust FastMatcher failed: {e}")
                
        return py_results # 始終以 Python 為主輸出
