import sys
import os

# Add the local python directory to path
sys.path.append(str(__import__("pathlib").Path(__file__).resolve().parents[2] / "nexus-reflex/python"))

import nexus_reflex as nexus

print("// Nexus-Reflex SDK Test: Starting...")

# Test 1: Scan
print("\n[Test 1] Symbolic Scan")
tree = nexus.scan(str(__import__("pathlib").Path(__file__).resolve().parents[2] / "nexus-reflex/python"))
if tree:
    print(f"// Success: Found {len(tree.get('children', []))} top-level items.")
    print(f"// Root Path: {tree.get('path')}")
else:
    print("// Failed: Scan returned None.")

# Test 2: Dry Run Action
print("\n[Test 2] Dry Run Action")
action = {
    "type": "create_file",
    "path": "test_sdk_output.txt",
    "content": "Hello from Python SDK!",
    "dry_run": True,
    "request_id": "REQ-PY-TEST",
    "actor": "Sir-SDK-Test",
    "intent": "Verify Python-Rust Bridge"
}
result = nexus.apply_action(action)
print(result)

print("\n// Nexus-Reflex SDK Test: Complete.")
