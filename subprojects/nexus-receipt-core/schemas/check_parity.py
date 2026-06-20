"""Generate canonical JSON and SHA-256 for all fixtures (Python)."""
import json, sys, os
from collections import OrderedDict
import hashlib

sys.path.insert(0, os.path.join(os.getcwd(), "schemas", "python"))
from canonicalizer import canonicalize, compute_canonical_json

fixtures_dir = os.path.join(os.getcwd(), "schemas", "python", "fixtures")

print("=== Python Canonicalization Parity ===")
print(f"Fixture count: {sum(1 for f in os.listdir(fixtures_dir) if f.endswith('.json'))}")

for fname in sorted(os.listdir(fixtures_dir)):
    if not fname.endswith('.json'):
        continue
    fpath = os.path.join(fixtures_dir, fname)
    try:
        with open(fpath, 'r') as f:
            data = json.load(f)
        canon = compute_canonical_json(data)
        sha = hashlib.sha256(canon.encode()).hexdigest()
        print(f"OK  {fname}: {sha}")
    except Exception as e:
        print(f"ERR {fname}: {e}")
