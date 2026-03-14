import argparse
import sys
from pathlib import Path
from nexus.services.patcher import SafePatcher

def main():
    parser = argparse.ArgumentParser(description="Nexus v7 SafePatcher")
    parser.add_argument("--apply", required=True, help="Upgrade ID or task name")
    parser.add_argument("--dry-run", type=lambda x: (str(x).lower() == 'true'), default=True)
    
    args = parser.parse_args()
    
    project_root = Path(__file__).resolve().parents[1]
    patcher = SafePatcher(lock_dir=str(project_root / ".runs/patches"), project_root=project_root)
    
    print(f"🚀 [SafePatcher] Applying upgrade: {args.apply} (Dry-run: {args.dry_run})")
    
    # 模擬讀取 violations (實際情況會從 state 或 lint 取得)
    # 這裡我們模擬一個與升級相關的補丁
    mock_violations = [
        {
            "file": "README.md",
            "patch": "--- a/README.md\n+++ b/README.md\n@@ -1,1 +1,2 @@\n # Muse-Nexus\n+# Certified by v7.1 Superpowers\n",
            "reason": "Upgrade certification tag"
        }
    ]
    
    if args.dry_run:
        print("🧪 [SafePatcher] Dry-run mode: No changes applied.")
    else:
        success = patcher.apply(mock_violations)
        if success:
            print("✅ [SafePatcher] Upgrade applied successfully.")
        else:
            print("❌ [SafePatcher] Failed to apply upgrade.")
            sys.exit(1)

if __name__ == "__main__":
    main()
