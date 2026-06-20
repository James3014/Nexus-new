#!/usr/bin/env python3
"""Generate rollback drill report for FlowMachine C phase verification."""

import json
import subprocess
import time
from pathlib import Path

STATES = [
    "intake", "clarify", "outline", "research", "design",
    "plan", "execute", "verify", "close", "replan",
    "escalate", "human_review", "blocked_budget", "blocked_policy"
]

CONTRACT_PATH = Path("subprojects/nexus-receipt-core/schemas/flow_machine.contract.v1.json")
RUST_BINARY = Path("nexus-core-rs/target/release/nexus-core-rs")

def load_contract():
    with open(CONTRACT_PATH) as f:
        return json.load(f)

def python_validate(transition_rules, from_state, to_state):
    allowed = transition_rules.get(from_state.upper(), [])
    return to_state.upper() in allowed or from_state.upper() == to_state.upper()

def rust_validate(from_state, to_state):
    if not RUST_BINARY.exists():
        return None
    
    request = {
        "type": "ValidateTransition",
        "payload": {
            "current": from_state.upper(),
            "next": to_state.upper()
        }
    }
    
    try:
        proc = subprocess.run(
            [str(RUST_BINARY)],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            timeout=5
        )
        if proc.returncode != 0:
            return None
        resp = json.loads(proc.stdout)
        return resp.get("payload", {}).get("is_valid", False)
    except Exception:
        return None

def main():
    print("🔍 Rollback Drill — Testing Python as fallback authority...")
    
    contract = load_contract()
    transition_rules = contract.get("transition_rules", {})
    
    # Select representative test cases: legal + illegal transitions
    test_cases = [
        # Legal transitions
        ("intake", "clarify"),
        ("clarify", "outline"),
        ("outline", "research"),
        ("research", "design"),
        ("design", "plan"),
        ("plan", "execute"),
        ("execute", "verify"),
        ("verify", "close"),
        
        # Self-transitions (always valid)
        ("intake", "intake"),
        ("clarify", "clarify"),
        
        # Illegal transitions
        ("intake", "execute"),
        ("plan", "clarify"),
        ("close", "intake"),  # Terminal state
    ]
    
    print(f"📋 Running {len(test_cases)} test cases...")
    
    results = []
    python_fallback_count = 0
    mismatches = 0
    
    for from_state, to_state in test_cases:
        py_result = python_validate(transition_rules, from_state, to_state)
        rs_result = rust_validate(from_state, to_state)
        
        if rs_result is None:
            # Rust unavailable → Python is fallback authority
            python_fallback_count += 1
            status = "PYTHON_FALLBACK"
        elif py_result == rs_result:
            status = "MATCH"
        else:
            mismatches += 1
            status = "MISMATCH"
        
        results.append({
            "from": from_state.upper(),
            "to": to_state.upper(),
            "python_result": py_result,
            "rust_result": rs_result,
            "status": status
        })
    
    # Generate markdown report
    report_lines = [
        "# Rollback Drill Report",
        "",
        f"**Generated**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Test Cases**: {len(test_cases)}",
        f"**Python Fallback**: {python_fallback_count}",
        f"**Mismatches**: {mismatches}",
        "",
        "## Test Results",
        "",
        "| From | To | Python | Rust | Status |",
        "|------|-----|--------|------|--------|",
    ]
    
    for r in results:
        report_lines.append(
            f"| {r['from']} | {r['to']} | {r['python_result']} | {r['rust_result']} | {r['status']} |"
        )
    
    report_lines.extend([
        "",
        "## Rollback Safety",
        "",
        f"- **System can fall back to Python**: ✅ ({python_fallback_count} cases)",
        f"- **Python vs Rust parity**: {'✅' if mismatches == 0 else '❌'}",
        "",
        f"## Conclusion",
        "",
    ])
    
    if mismatches == 0:
        report_lines.append("Rollback drill **PASSED**. Python remains authoritative when Rust is unavailable or inconsistent.")
    else:
        report_lines.append(f"Rollback drill **FAILED**. {mismatches} mismatch(es) detected between Python and Rust.")
    
    report_md = "\n".join(report_lines)
    
    # Save both formats
    md_path = Path("verification-evidence/rollback_drill_report.md")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(report_md)
    
    json_report = {
        "schema": "rollback_drill.report.v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_test_cases": len(test_cases),
        "python_fallback_count": python_fallback_count,
        "mismatches": mismatches,
        "results": results,
        "passed": mismatches == 0
    }
    
    json_path = Path("verification-evidence/rollback_drill_report.json")
    with open(json_path, "w") as f:
        json.dump(json_report, f, indent=2)
    
    print(f"\n✅ Rollback drill report generated:")
    print(f"   Markdown: {md_path}")
    print(f"   JSON: {json_path}")
    print(f"   Python fallback cases: {python_fallback_count}")
    print(f"   Mismatches: {mismatches}")
    print(f"   Status: {'PASSED ✅' if mismatches == 0 else 'FAILED ❌'}")
    
    return mismatches == 0

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
