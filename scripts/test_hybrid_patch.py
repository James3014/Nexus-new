#!/usr/bin/env python3
import os
import subprocess

def main():
    print("🎬 Starting Hybrid Patching Battle Test...")
    
    # 1. Clear any old patches
    if os.path.exists("nexus_fix_FRAG_001.patch"):
        os.remove("nexus_fix_FRAG_001.patch")

    # 2. Run the Patcher
    print("🕸️  Running Hybrid Patcher...")
    subprocess.run(["python3", "scripts/engine/hybrid_patcher.py"])

    # 3. Verify Output
    patch_file = "nexus_fix_FRAG_001.patch"
    if os.path.exists(patch_file):
        print(f"✅ SUCCESS: Patch file {patch_file} generated.")
        
        with open(patch_file, "r") as f:
            content = f.read()
            if "export class QuestionsAdapter" in content:
                print("✅ VALIDATION: Adapter code found in patch.")
                print("-" * 15 + " PATCH CONTENT " + "-" * 15)
                print(content)
                print("-" * 40)
            else:
                print("❌ VALIDATION: Adapter code missing from patch!")
    else:
        print("❌ FAILED: Patch file not generated!")

if __name__ == "__main__":
    main()
