#!/usr/bin/env python3
"""
🛡️ Nexus Startup Contract Checker
強制執行啟動前規約檢查，確保 Agent 在可治理環境中運行。
"""
import os
import sys
import json
import hashlib
import time
import subprocess
from pathlib import Path

# 強制要求的檔案清單
REQUIRED_FILES = [
    "AGENTS.md",
    "scripts/ops/_nexus_preflight.sh",
    "scripts/engine/nexus_cli.py",
    "nexus/core/hallucination_guard.py",
    "nexus/schemas/hallucination_index_v1.json"
]

# 強制要求的 CLI 命令
REQUIRED_SURFACES = [
    "acceptance-check",
    "contract-check"
]

def check_files(project_root: Path) -> dict:
    results = {}
    for f in REQUIRED_FILES:
        path = project_root / f
        results[f] = path.exists() and os.access(path, os.R_OK)
    return results

def check_cli(project_root: Path) -> dict:
    results = {}
    cli_path = project_root / "scripts/engine/nexus_cli.py"
    try:
        output = subprocess.check_output([sys.executable, str(cli_path), "nexus", "--help"], text=True)
        for cmd in REQUIRED_SURFACES:
            results[cmd] = cmd in output
    except Exception as e:
        results["error"] = str(e)
    return results

def run_check():
    project_root = Path(__file__).parent.parent.parent.absolute()
    file_results = check_files(project_root)
    cli_results = check_cli(project_root)
    
    all_passed = all(file_results.values()) and all(cli_results.values())
    
    report = {
        "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        "project_root": str(project_root),
        "file_check": file_results,
        "cli_check": cli_results,
        "passed": all_passed,
        "commit_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    }
    
    report_dir = project_root / ".nexus/reports/startup_hardening"
    report_dir.mkdir(parents=True, exist_ok=True)
    
    check_report_path = report_dir / "startup_contract_check_report.json"
    check_report_path.write_text(json.dumps(report, indent=2))
    
    if all_passed:
        ack = {
            "ack_token": hashlib.sha256(f"{report['commit_sha']}-{report['timestamp']}".encode()).hexdigest()[:16],
            "status": "ENFORCED",
            "runner": os.getenv("NEXUS_RUNNER", "unknown"),
            "timestamp": report["timestamp"]
        }
        (report_dir / "startup_contract_ack.json").write_text(json.dumps(ack, indent=2))
        print(f"✅ Nexus Startup Contract PASSED. Token: {ack['ack_token']}")
        return 0
    else:
        print("❌ Nexus Startup Contract FAILED!")
        for f, res in file_results.items():
            if not res: print(f"  - Missing File: {f}")
        for cmd, res in cli_results.items():
            if not res: print(f"  - Missing CLI Surface: {cmd}")
        return 1

if __name__ == "__main__":
    sys.exit(run_check())
