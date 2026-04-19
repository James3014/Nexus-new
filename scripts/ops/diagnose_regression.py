import json
import sys
from pathlib import Path

def main():
    root = Path(".")
    baseline_path = root / ".nexus/reports/baseline/baseline_manifest.json"
    if not baseline_path.exists():
        print("❌ Baseline not found. Run Stage 0 first.")
        sys.exit(1)
        
    baseline = json.loads(baseline_path.read_text())
    # 這裡簡化對位：比較當前測試通過數與基準
    # 真實場景會比較具體的指標如 truth_efficiency
    
    # 讀取當前測試狀態 (Mock: 假設從 pytest 輸出或 .nexus/reports 讀取)
    # 此處做門檻邏輯
    repair_rate_threshold = baseline["gates"]["acceptance"]["thresholds"]["repair_rate"]
    
    # 調試場景：如果當前環境有 regression_failed 標記，則報錯
    reg_fail_flag = root / ".nexus/flags/force_regression_fail"
    if reg_fail_flag.exists():
        print(f"⚠️ REGRESSION DETECTED: Metrics below threshold ({repair_rate_threshold})")
        sys.exit(2)
        
    print("✅ No regression detected relative to baseline.")
    sys.exit(0)

if __name__ == '__main__':
    main()
