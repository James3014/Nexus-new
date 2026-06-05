import os
from pathlib import Path
from nexus.bridge.fast_matcher import FastMatcherBridge

def test_fast_matcher_drift_zero():
    project_root = Path(os.getcwd())
    bridge = FastMatcherBridge(project_root)
    
    assert bridge.rust_available, "Rust module must be available"
    
    # Execute Python scan
    py_results = bridge.py_scan(str(project_root), [])
    
    # Execute Rust scan
    rs_meta = bridge.rust_core.fast_scan(str(project_root), [])
    rs_results = sorted([
        os.path.relpath(m.path, str(project_root)) for m in rs_meta
    ])
    
    py_set = set(py_results)
    rs_set = set(rs_results)
    
    # Assert total parity for Drift-Zero
    assert py_set == rs_set, (
        f"Drift mismatch! "
        f"py_count={len(py_set)}, rs_count={len(rs_set)}. "
        f"py_only_samples={sorted(list(py_set - rs_set))[:5]}, "
        f"rs_only_samples={sorted(list(rs_set - py_set))[:5]}"
    )
