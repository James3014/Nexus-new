#!/usr/bin/env python3
"""
Quick test for persistent_worker.py

Usage:
  python scripts/bench/test_persistent_worker.py

Tests:
  1. Worker starts and imports Nexus runtime
  2. Worker accepts a task and returns result
  3. Worker handles shutdown gracefully
"""
import json
import subprocess
import sys
import time


def test_worker():
    print("Starting persistent worker...")
    proc = subprocess.Popen(
        [sys.executable, "scripts/bench/persistent_worker.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Wait for worker to be ready
    time.sleep(2)

    # Test 1: Simple task
    print("\n[Test 1] Sending simple task...")
    task = {
        "action": "task",
        "task_id": "test-001",
        "prompt": "Say hello in JSON format: {\"greeting\": \"...\"}",
        "context": {},
        "phase": "R",
        "timeout_sec": 30,
    }
    proc.stdin.write(json.dumps(task) + "\n")
    proc.stdin.flush()

    # Read response
    proc.stdout.flush()
    line = proc.stdout.readline()
    result = json.loads(line)
    print(f"  Response: {json.dumps(result, indent=2)}")
    assert result["task_id"] == "test-001", f"Expected task_id=test-001, got {result['task_id']}"
    assert result["status"] == "ok", f"Expected status=ok, got {result['status']}"
    assert "elapsed_sec" in result, "Missing elapsed_sec"
    print(f"  ✓ Task completed in {result['elapsed_sec']}s")

    # Test 2: Shutdown
    print("\n[Test 2] Sending shutdown...")
    proc.stdin.write(json.dumps({"action": "shutdown"}) + "\n")
    proc.stdin.flush()

    line = proc.stdout.readline()
    result = json.loads(line)
    print(f"  Response: {json.dumps(result, indent=2)}")
    assert result["status"] == "shutdown", f"Expected status=shutdown, got {result['status']}"
    print("  ✓ Shutdown acknowledged")

    # Wait for process to exit
    proc.wait(timeout=5)
    print(f"\n  Worker exited with code {proc.returncode}")

    # Check stderr for startup time
    stderr = proc.stderr.read()
    for line in stderr.split("\n"):
        if "ready in" in line:
            print(f"  {line.strip()}")

    print("\n✓ All tests passed!")
    return 0


if __name__ == "__main__":
    sys.exit(test_worker())
