#!/usr/bin/env python3
import subprocess
import os

def run_wasm_check(name, cmd):
    print(f"--- Running {name} ---")
    try:
        # We use check_output to capture results
        result = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode()
        return result.strip()
    except subprocess.CalledProcessError as e:
        return f"ERROR: {e.output.decode().strip()}"

def main():
    print("🕸️ Starting Nexus Sandbox Security Verification...")

    # 1. Escape Test: Try to access /etc/passwd (Should fail/return False)
    # Note: Wasmer/WASI by default has no access to root / unless mapped.
    print("\n[Test 1] Filesystem Escape Check (/etc/passwd)")
    res1 = run_wasm_check("Escape Check", [
        "wasmer", "run", "wasmer/python", "--", "-c", 
        "import os; print(os.access('/etc/passwd', os.R_OK))"
    ])
    print(f"Result: {res1}")
    if "False" in res1 or "ERROR" in res1:
        print("✅ SUCCESS: Sandbox blocked system access.")
    else:
        print("❌ FAILED: Sandbox ESCAPED to system files!")

    # 2. Jail Test: access current directory (Should pass if mapped)
    print("\n[Test 2] Repository Jail Check (README.md)")
    cwd = os.getcwd()
    res2 = run_wasm_check("Jail Check", [
        "wasmer", "run", "--volume", f"{cwd}:/workspace", "wasmer/python", "--", "-c", 
        "import os; print(os.access('/workspace/README.md', os.R_OK))"
    ])
    print(f"Result: {res2}")
    if "True" in res2:
        print("✅ SUCCESS: Sandbox correctly accessed allowed directory.")
    else:
        print("❌ FAILED: Sandbox blocked allowed access (Check mapping).")

    # 3. Network Test: Try to import socket and connect (Should fail)
    print("\n[Test 3] Network Isolation Check")
    res3 = run_wasm_check("Network Check", [
        "wasmer", "run", "wasmer/python", "--", "-c", 
        "import socket; socket.create_connection(('8.8.8.8', 53), timeout=1)"
    ])
    print(f"Result: {res3}")
    if "ERROR" in res3 or "Exception" in res3:
        print("✅ SUCCESS: Sandbox blocked network access.")
    else:
        print("❌ FAILED: Sandbox ESCAPED to network!")

if __name__ == "__main__":
    main()
