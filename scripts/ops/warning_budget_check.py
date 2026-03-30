#!/usr/bin/env python3
import argparse
import re
import subprocess
import sys
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Check warning budget against Pytest runs.")
    parser.add_argument("--threshold", type=int, default=70, help="Maximum allowed warnings")
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[2]))
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    
    print(f"📊 [Warning Budget] Analyzing warning count (Threshold: {args.threshold})")
    
    # Run pytest to count warnings
    cmd = ["uv", "run", "pytest", "-q"]
    
    # Run the command and capture output
    res = subprocess.run(
        cmd,
        cwd=str(project_root),
        capture_output=True,
        text=True
    )
    
    output = res.stdout + res.stderr
    
    # Parse output for 'XX warnings' or '1 warning'
    # Format usually looks like "== 1 passed, 60 warnings in 0.42s =="
    match = re.search(r'(\d+)\s+warning', output, re.IGNORECASE)
    
    if match:
        warnings = int(match.group(1))
    else:
        # If tests failed or no warnings matched, we assume 0 or handle error
        if res.returncode != 0 and res.returncode != 1:
            print(f"❌ [Warning Budget] Failed to run pytest. Return code: {res.returncode}")
            print(output[-1000:])
            sys.exit(1)
        warnings = 0
        
    print(f"📈 Current Warning Count: {warnings}")
    
    if warnings > args.threshold:
        print(f"❌ Warning budget exceeded! ({warnings} > {args.threshold})")
        print("Please address some warnings before submitting.")
        sys.exit(1)
    else:
        print(f"✅ Warning budget satisfied ({warnings} <= {args.threshold}).")
        
    # Write to a metrics file for tracking
    metrics_dir = project_root / ".nexus" / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    report_file = metrics_dir / "warning_budget.json"
    
    import json
    from datetime import datetime, timezone
    
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "warnings": warnings,
        "threshold": args.threshold,
        "passed": warnings <= args.threshold
    }
    
    report_file.write_text(json.dumps(report, indent=2))
    sys.exit(0)

if __name__ == "__main__":
    main()
