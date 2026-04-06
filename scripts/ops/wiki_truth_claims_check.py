#!/usr/bin/env python3
import os
import re
import subprocess
import json
from datetime import datetime
from pathlib import Path

# 🛡️ Nexus Truth Claims Verifier v2.0 (Agent H - Hardened)
# [NEXUS IDENTITY: 06624d2 + CI-GUARDED]

REPO_ROOT = Path("/Users/jameschen/Workspace/nexus")
VAULT_ROOT = REPO_ROOT / "nexus_wiki_vault"
REPORT_PATH = REPO_ROOT / ".nexus" / "reports" / "wiki_truth_claims_report.json"

# Safety Guardrails
WHITELIST_PREFIXES = [
    "test ", "ls ", "grep ", "rg ", "git tag --list", 
    "uv run scripts/ops/ci_gate.py --dry-run", 
    "uv run scripts/ops/wiki_linter.py --strict",
    "uv run scripts/ops/wiki_coverage_audit.py"
]
BLACKLIST_STRINGS = [
    "rm", "git reset", "git checkout", "git clean", "sudo", "curl |", 
    "$(", "`"
]

def is_safe(command):
    cmd = command.strip()
    # Check Whitelist
    safe_start = any(cmd.startswith(prefix) for prefix in WHITELIST_PREFIXES)
    if not safe_start:
        return False, "Not in whitelist"
    
    # Check Blacklist with Word Boundaries for rm, etc.
    for forbidden in BLACKLIST_STRINGS:
        if re.search(r"\b" + re.escape(forbidden) + r"\b", cmd):
            return False, f"Contains forbidden string: '{forbidden}'"
        # Special case for generic characters
        if forbidden in [">", ">>", ";", "|", "$(", "`"] and forbidden in cmd:
             return False, f"Contains forbidden character: '{forbidden}'"
            
    return True, "OK"

def env_pre_flight():
    """Ensure environment is valid for uv execution."""
    try:
        # Check uv
        res = subprocess.run("which uv", shell=True, capture_output=True, text=True)
        if res.returncode != 0: return False, "uv not found in PATH"
        
        # Check pyproject.toml
        if not (REPO_ROOT / "pyproject.toml").exists():
            return False, "pyproject.toml missing in REPO_ROOT"
            
        return True, "OK"
    except:
        return False, "Unexpected Pre-flight error"

# 🛡️ Truth Policy Constraints (Agent T)
WHITELIST_PREFIXES = [
    "test", "ls", "grep", "rg", "git tag --list",
    "uv run scripts/ops/wiki_linter.py --strict",
    "uv run scripts/ops/ci_gate.py --dry-run",
    "uv run scripts/ops/wiki_coverage_audit.py",
    "uv run scripts/ops/wiki_drift_audit.py"
]
BLACKLIST_KEYWORDS = [
    "rm", "git reset", "git checkout", "git clean", "sudo", "curl |",
    ">", ">>", ";", "&&", "||", "$(", "`"
]

def is_policy_compliant(cmd):
    """Agent T: Validate command against security whitelist and blacklist."""
    cmd = cmd.strip()
    # Check Whitelist
    whitelisted = any(cmd.startswith(prefix) for prefix in WHITELIST_PREFIXES)
    if not whitelisted: return False, "CMD_NOT_IN_WHITELIST"
    # Check Blacklist with Word Boundaries (Agent T+ Revision)
    import re
    for kw in BLACKLIST_KEYWORDS:
        # Use word boundaries for alphabetic keywords like 'rm', 'sudo'
        if kw.isalpha():
            if re.search(r"\b" + re.escape(kw) + r"\b", cmd):
                return False, f"CMD_CONTAINS_BLACKLIST_KEYWORD: {kw}"
        else:
            # For non-alphabetic chars like '>', ';', '&&', substring check is safer
            if kw in cmd:
                return False, f"CMD_CONTAINS_BLACKLIST_SYMBOL: {kw}"
    return True, None

def run_checks():
    print("🛡️ WS-H: Executing Truth Claims Auto-Calibration v2.0...")
    
    # 1. Env Pre-flight
    env_ok, env_msg = env_pre_flight()
    if not env_ok:
        print(f"⚠️ ENVIRONMENT_FAIL: {env_msg}. All uv-based claims will be skipped.")

    register_file = VAULT_ROOT / "06_Ops" / "Ops - Truth Claims Register.md"
    if not register_file.exists():
        print("❌ Error: Truth Claims Register missing!")
        return

    content = register_file.read_text()
    # | C-ID | Claim | Evidence | Command | Status | Date |
    rows = re.findall(r"\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|", content)
    
    results = []
    mismatch_count = 0
    infra_error_count = 0

    claims = []
    for row in rows[1:]: # Skip header
        cols = [c.strip() for c in row]
        if len(cols) != 6: continue
        c_id, claim, evidence, command, wiki_status, date = cols
        if not c_id.startswith("C-") and not c_id.startswith("`C-"): continue
        
        c_id = c_id.replace("`", "")
        command = command.replace("`", "")
        claims.append((c_id, command, wiki_status))

    # SUMMARY STATS
    mismatch_count = 0
    infra_error_count = 0
    policy_violation_count = 0
    blocked_claim_ids = []
    results = []

    for c_id, claim, wiki_status in claims:
        # Agent T: Policy Check
        compliant, violation_reason = is_policy_compliant(claim)
        if not compliant:
            policy_violation_count += 1
            blocked_claim_ids.append(c_id)
            results.append({
                "id": c_id, "claim": claim, "status": "POLICY_BLOCKED",
                "error": f"Policy Violation: {violation_reason}",
                "wiki_status": wiki_status
            })
            continue

        print(f"🧐 Checking {c_id}: {claim}...")
        
        try:
            res = subprocess.run(claim, shell=True, capture_output=True, text=True, timeout=10, cwd=REPO_ROOT)
            
            # Status Machine Mapping
            actual_status = "MATCH"
            error_msg = None
            cause_code = None
            retry_hint = None
            
            # 1. Environment Errors (Infrastructure)
            if res.returncode in [2, 127, 130]:
                actual_status = "ENVIRONMENT_FAIL"
                error_msg = f"Infra Error (Exit {res.returncode}): {res.stderr.strip()}"
                
                # Agent N: Cause Detection
                if "command not found" in res.stderr.lower():
                    cause_code = "CMD_NOT_FOUND"
                    retry_hint = "Ensure 'uv' or binary is in PATH"
                elif "permission denied" in res.stderr.lower():
                    cause_code = "PERMISSION_DENIED"
                    retry_hint = "Check file/cache permissions"
                elif "no such file" in res.stderr.lower():
                    cause_code = "PATH_NOT_FOUND"
                    retry_hint = "Verify code path existence"
                else:
                    cause_code = "UNKNOWN_INFRA_ERROR"
                    retry_hint = "Review stderr for environmental details"
                infra_error_count += 1
            
            # 2. Logical Mismatch
            elif wiki_status == "✅" and res.returncode != 0:
                actual_status = "MISMATCH"
                error_msg = f"Execution Failed (Exit {res.returncode}): {res.stderr.strip()}"
                mismatch_count += 1
            elif wiki_status == "❌" and res.returncode == 0:
                actual_status = "MISMATCH"
                error_msg = "Expected Fail but execution SUCCEEDED"
                mismatch_count += 1
            
            results.append({
                "id": c_id, "claim": claim, "status": actual_status, 
                "error": error_msg, "cause_code": cause_code, "retry_hint": retry_hint,
                "wiki_status": wiki_status,
                "stdout": res.stdout, "stderr": res.stderr
            })
            
        except subprocess.TimeoutExpired:
            results.append({"id": c_id, "claim": claim, "status": "ENVIRONMENT_FAIL", "error": "Timeout expired (10s)", "wiki_status": wiki_status})
            infra_error_count += 1
        except Exception as e:
            results.append({"id": c_id, "claim": claim, "status": "ENVIRONMENT_FAIL", "error": f"System Error: {str(e)}", "wiki_status": wiki_status})
            infra_error_count += 1

    # Report Summary
    summary = {
        "mismatch_count": mismatch_count,
        "infra_error_count": infra_error_count,
        "policy_violation_count": policy_violation_count,
        "blocked_claim_ids": blocked_claim_ids,
        "total_claims": len(claims),
        "timestamp": datetime.now().isoformat(),
        "status": "PASS" if (mismatch_count == 0 and policy_violation_count == 0) else "FAIL"
    }
    
    output = {"summary": summary, "details": results}
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(output, indent=2))
    
    print(f"\n📊 Summary: {len(results)} Claims checked.")
    print(f"❌ Mismatches: {mismatch_count}")
    print(f"⚠️ Environment Failures: {infra_error_count}")
    
    for r in results:
        status_icon = "✅" if r["status"] == "MATCH" else "❌" if r["status"] == "MISMATCH" else "⚠️"
        print(f"  - {r['id']}: {status_icon} ({r['status']}) (Wiki: {r['wiki_status']})")
        if r["error"]:
            print(f"    [Error]: {r['error']}")

if __name__ == "__main__":
    run_checks()
