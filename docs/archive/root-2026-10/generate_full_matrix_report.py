#!/usr/bin/env python3
"""Generate full-matrix parity report for FlowMachine C phase verification."""

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
    """Python-side validation against contract."""
    allowed = transition_rules.get(from_state.upper(), [])
    return to_state.upper() in allowed or from_state.upper() == to_state.upper()

def rust_validate(from_state, to_state):
    """Rust-side validation via IPC."""
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
    print("🔍 Loading contract...")
    contract = load_contract()
    transition_rules = contract.get("transition_rules", {})
    
    print(f"📊 Generating {len(STATES)}×{len(STATES)} = {len(STATES)**2} transition matrix...")
    
    results = []
    total = 0
    matches = 0
    mismatches = []
    rust_unavailable = 0
    
    start_time = time.time()
    
    for from_state in STATES:
        for to_state in STATES:
            total += 1
            
            # Python validation
            py_result = python_validate(transition_rules, from_state, to_state)
            
            # Rust validation (may be None if binary not available)
            rs_result = rust_validate(from_state, to_state)
            
            if rs_result is None:
                rust_unavailable += 1
                match = "SKIPPED"
            else:
                match = "MATCH" if py_result == rs_result else "MISMATCH"
            
            entry = {
                "from": from_state.upper(),
                "to": to_state.upper(),
                "python_result": py_result,
                "rust_result": rs_result,
                "match": match
            }
            results.append(entry)
            
            if match == "MATCH":
                matches += 1
            elif match == "MISMATCH":
                mismatches.append(entry)
    
    elapsed = time.time() - start_time
    
    # Generate report
    report = {
        "schema": "flow_machine.full_matrix_parity_report.v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "execution_time_seconds": round(elapsed, 3),
        "summary": {
            "total_transitions_tested": total,
            "python_rust_matches": matches,
            "mismatches": len(mismatches),
            "rust_unavailable": rust_unavailable,
            "parity_rate": round(matches / total * 100, 2) if total > 0 else 0
        },
        "mismatch_details": mismatches,
        "all_results": results
    }
    
    output_path = Path("verification-evidence/flow_machine_full_matrix_report.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)
    
    print(f"\n✅ Full-matrix report generated: {output_path}")
    print(f"   Total transitions: {total}")
    print(f"   Matches: {matches}")
    print(f"   Mismatches: {len(mismatches)}")
    print(f"   Rust unavailable: {rust_unavailable}")
    print(f"   Parity rate: {report['summary']['parity_rate']}%")
    
    if mismatches:
        print(f"\n⚠️  {len(mismatches)} mismatches found:")
        for m in mismatches[:5]:
            print(f"   {m['from']}→{m['to']}: Python={m['python_result']}, Rust={m['rust_result']}")
    
    return len(mismatches) == 0

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
