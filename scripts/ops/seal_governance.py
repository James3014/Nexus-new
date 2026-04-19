from pathlib import Path
import sys
import os

# 確保找到 nexus 模組
sys.path.append(os.getcwd())

from nexus.delivery.anti_drift import AntiDrift

def main():
    root = Path(".")
    manifest = root / "nexus/config/governance_manifest.json"
    print(f"Generating governance seal at {manifest}...")
    hashes = AntiDrift.generate_manifest(root, manifest)
    for f, h in hashes.items():
        print(f"  {f}: {h[:16]}...")
    print("Governance Seal Applied.")

if __name__ == '__main__':
    main()
