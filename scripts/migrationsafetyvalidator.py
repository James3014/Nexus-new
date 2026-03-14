import argparse
import sys
from pathlib import Path
from core.migration_validator import MigrationValidator

def main():
    parser = argparse.ArgumentParser(description="Nexus v7 Migration Safety Validator")
    parser.add_argument("--mode", required=True, choices=["gatekeeper", "audit"])
    parser.add_argument("--changes", required=True, help="Domain or folder being changed")
    
    args = parser.parse_args()
    
    project_root = Path(__file__).resolve().parents[1]
    validator = MigrationValidator(project_root)
    
    print(f"🛡️ [Validator] Gatekeeper Mode: Scanning changes in '{args.changes}'...")
    
    if args.mode == "gatekeeper":
        success = validator.run_full_scan()
        if success:
            print(f"✅ [Validator] '{args.changes}' passed safety audit.")
        else:
            print(f"❌ [Validator] '{args.changes}' failed safety audit.")
            sys.exit(1)

if __name__ == "__main__":
    main()
