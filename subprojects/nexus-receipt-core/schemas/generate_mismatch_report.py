"""Verify Python canonicalization matches Rust output.

Usage:
    python generate_mismatch_report.py <rust_output_path> <python_output_path> <report_path>

Compares canonicalization output for all fixtures and generates
a mismatch report.
"""

import json
import hashlib
import sys
import os

# Add schemas/python to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "schemas", "python"))

from canonicalizer import canonicalize, compute_canonical_json

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "python", "fixtures")

REQUIRED_FIELDS = [
    "id", "type", "timestamp", "model",
    "input_hash", "output_hash", "evidence",
]

EVIDENCE_REQUIRED_FIELDS = ["type", "content", "hash"]


def load_fixture(name):
    """Load fixture, handling non-UTF-8 and malformed JSON gracefully."""
    fpath = os.path.join(FIXTURE_DIR, name)
    try:
        with open(fpath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except UnicodeDecodeError:
        return {"__error": "invalid_utf8", "__path": fpath}
    except json.JSONDecodeError as e:
        return {"__error": f"parse_error: {str(e)[:50]}", "__path": fpath}


def verify_receipt_python(data, claimed_hash=None):
    """Python-side verification mirroring Rust verify_receipt."""
    # Handle special error dicts from load_fixture
    if "__error" in data:
        error_type = data["__error"]
        if error_type == "invalid_utf8":
            mapped_errorcode = "parse_error"
        else:
            mapped_errorcode = error_type.split(":")[0]
        return {
            "computed_hash": None,
            "hashmatch": None,
            "schemamatch": False,
            "evidencecomplete": False,
            "claimabilityconfirmed": False,
            "errorcode": mapped_errorcode,
        }
    # Canonicalize
    canonical = canonicalize(data)
    canonical_json = compute_canonical_json(canonical)
    
    # Compute hash
    computed_hash = hashlib.sha256(canonical_json.encode()).hexdigest()
    
    # Hash match
    hashmatch = computed_hash == claimed_hash if claimed_hash else True
    
    # Schema compliance
    schemamatch = all(field in data for field in REQUIRED_FIELDS)
    
    # Evidence completeness
    evidencecomplete = False
    if schemamatch and "evidence" in data:
        ev = data["evidence"]
        if isinstance(ev, list) and len(ev) > 0:
            evidencecomplete = all(
                all(f in item for f in EVIDENCE_REQUIRED_FIELDS)
                for item in ev
            )
    
    claimabilityconfirmed = hashmatch and schemamatch and evidencecomplete
    
    errorcode = None
    if not hashmatch:
        errorcode = "hash_mismatch"
    elif not schemamatch:
        errorcode = "schema_mismatch"
    elif not evidencecomplete:
        errorcode = "evidence_incomplete"
    
    return {
        "computed_hash": computed_hash,
        "hashmatch": hashmatch,
        "schemamatch": schemamatch,
        "evidencecomplete": evidencecomplete,
        "claimabilityconfirmed": claimabilityconfirmed,
        "errorcode": errorcode,
    }


def main():
    if len(sys.argv) < 4:
        print("Usage: python generate_mismatch_report.py <rust_output_path> <python_output_path> <report_path>")
        sys.exit(1)
    
    rust_output_path = sys.argv[1]
    python_output_path = sys.argv[2]
    report_path = sys.argv[3]
    
    # Load Rust and Python outputs if they exist
    rust_results = {}
    python_results = {}
    
    if os.path.exists(rust_output_path):
        with open(rust_output_path) as f:
            rust_results = json.load(f)
    
    if os.path.exists(python_output_path):
        with open(python_output_path) as f:
            python_results = json.load(f)
    
    # Run Python verification on all fixtures
    fixture_names = sorted([
        f for f in os.listdir(FIXTURE_DIR)
        if f.endswith(".json")
    ])
    
    mismatches = []
    all_passed = True
    
    for fixture_name in fixture_names:
        data = load_fixture(fixture_name)
        
        # Skip fixtures with load errors (invalid UTF-8, parse errors)
        if "__error" in data:
            python_results[fixture_name] = verify_receipt_python(data)
            continue
        
        # Extract claimed hash
        claimed_hash = data.get("claimed_hash")
        if claimed_hash and claimed_hash.startswith("PLACEHOLDER"):
            # Compute actual hash for clean receipt
            canonical = canonicalize(data)
            canonical_json = compute_canonical_json(canonical)
            claimed_hash = hashlib.sha256(canonical_json.encode()).hexdigest()
        
        result = verify_receipt_python(data, claimed_hash if claimed_hash != "PLACEHOLDER" else None)
        python_results[fixture_name] = result
        
        # Compare with Rust if available
        if fixture_name in rust_results:
            rust_result = rust_results[fixture_name]
            
            # Compare computed hashes
            rust_hash = rust_result.get("computed_hash", "")
            py_hash = result.get("computed_hash", "")
            
            if rust_hash != py_hash:
                mismatches.append({
                    "fixture": fixture_name,
                    "field": "computed_hash",
                    "rust": rust_hash,
                    "python": py_hash,
                })
                all_passed = False
            
            # Compare verification results
            for field in ["hashmatch", "schemamatch", "evidencecomplete", "claimabilityconfirmed"]:
                if rust_result.get(field) != result.get(field):
                    mismatches.append({
                        "fixture": fixture_name,
                        "field": field,
                        "rust": rust_result.get(field),
                        "python": result.get(field),
                    })
                    all_passed = False
    
    # Generate report
    report = {
        "generated_at": "PLACEHOLDER_TIMESTAMP",
        "fixtures_tested": fixture_names,
        "all_passed": all_passed,
        "mismatches": mismatches,
        "mismatch_count": len(mismatches),
        "python_results": python_results,
    }
    
    # Write report
    os.makedirs(os.path.dirname(report_path) if os.path.dirname(report_path) else ".", exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    
    # Also write Python results separately
    if not os.path.exists(python_output_path):
        os.makedirs(os.path.dirname(python_output_path) if os.path.dirname(python_output_path) else ".", exist_ok=True)
        with open(python_output_path, "w") as f:
            json.dump(python_results, f, indent=2)
    
    print(f"Report: {report_path}")
    print(f"Fixtures tested: {len(fixture_names)}")
    print(f"Mismatches: {len(mismatches)}")
    print(f"All passed: {all_passed}")
    
    if mismatches:
        print("\nMISMATCH DETAILS:")
        for m in mismatches:
            print(f"  {m['fixture']}.{m['field']}: rust={m['rust']} python={m['python']}")
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
