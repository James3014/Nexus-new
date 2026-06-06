
import os
import sys
from pathlib import Path
from nexus.bridge.fast_matcher import FastMatcherBridge

def debug_mismatch():
    root = Path(os.getcwd())
    bridge = FastMatcherBridge(root)
    
    print("🔍 Running Python scan (full)...")
    py_results = bridge.py_scan(str(root), [])
    print(f"✅ Python found {len(py_results)} files.")
    
    if not bridge.rust_available:
        print("❌ Rust core not available.")
        return
        
    print("🔍 Running Rust scan (full)...")
    rs_meta = bridge.rust_core.fast_scan(str(root), [])
    rs_results = sorted([os.path.relpath(m.path, str(root)) for m in rs_meta])
    print(f"✅ Rust found {len(rs_results)} files.")
    
    py_set = set(py_results)
    rs_set = set(rs_results)
    
    only_py = sorted(list(py_set - rs_set))
    only_rs = sorted(list(rs_set - py_set))
    
    from collections import Counter
    if only_py:
        print(f"⚠️ Only in Python ({len(only_py)}):")
        dirs = Counter([f.split('/')[0] for f in only_py])
        for d, count in dirs.items():
            print(f"  - {d}: {count}")
            
    if only_rs:
        print(f"⚠️ Only in Rust ({len(only_rs)}):")
        dirs = Counter([f.split('/')[0] for f in only_rs])
        for d, count in dirs.items():
            print(f"  - {d}: {count}")
            
    if py_set == rs_set:
        print("🎉 [MATCH] Python and Rust scan results are identical!")
    else:
        print("❌ [MISMATCH] Results still differ.")

if __name__ == "__main__":
    debug_mismatch()
