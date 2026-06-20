"""Compare Rust verifier hashes vs Python canonicalization hashes."""
import json, subprocess, os, hashlib

FIXTURE_DIR = "schemas/python/fixtures"

print("=== Rust ↔ Python Hash Parity Check ===")

for fname in sorted(os.listdir(FIXTURE_DIR)):
    if not fname.endswith('.json'):
        continue
    fpath = os.path.join(FIXTURE_DIR, fname)
    
    # Get Python hash
    py_ok = False
    py_hash = "?"
    try:
        import sys
        sys.path.insert(0, os.path.join(os.getcwd(), "schemas", "python"))
        from canonicalizer import compute_canonical_json
        with open(fpath, 'r') as f:
            data = json.load(f)
        canon = compute_canonical_json(data)
        py_hash = hashlib.sha256(canon.encode()).hexdigest()[:16]
        py_ok = True
    except Exception as e:
        py_hash = f"ERR:{str(e)[:20]}"
        py_ok = False
    
    # Get Rust hash via CLI
    rust_ok = False
    rust_hash = "?"
    try:
        result = subprocess.run(
            ["cargo", "run", "--quiet", "--", "verify", fpath],
            capture_output=True, text=True, timeout=10,
            cwd=os.getcwd()
        )
        if result.returncode == 0:
            res_data = json.loads(result.stdout)
            rust_ok = True
            # Rust output includes hash field
            if 'computed_hash' in res_data:
                rust_hash = res_data['computed_hash'][:16]
            else:
                rust_hash = "N/A"
        else:
            rust_hash = f"FAIL:{result.stderr.strip()[:30]}"
    except Exception as e:
        rust_hash = f"ERR:{str(e)[:20]}"
    
    status = "OK" if (py_ok and rust_ok and py_hash == rust_hash) else "CHECK"
    print(f"{status} {fname}: py={py_hash} rust={rust_hash}")
