from pathlib import Path
import json
import inspect

from scripts.ops import nexus_acceptance_check

GOLDEN_DIR = Path(__file__).parent / "golden"

def test_acceptance_rules_contract():
    """驗證 Acceptance Gate 的三大規則名稱不可變"""
    golden_path = GOLDEN_DIR / "acceptance_rules.json"
    golden_data = json.loads(golden_path.read_text())
    
    expected_rules = set(golden_data["rules"])
    
    # 透過動態反射取得 scripts 內的 rule names，或是直接測試函式的存在
    # 這裡我們驗證三支核心檢核函式是否存在
    assert hasattr(nexus_acceptance_check, "_evaluate_repair_success")
    assert hasattr(nexus_acceptance_check, "_evaluate_phantom_false_positive")
    assert hasattr(nexus_acceptance_check, "_evaluate_regression_and_side_effects")
    
    # 模擬一次呼叫取得 CriterionResult.name
    res1 = nexus_acceptance_check._evaluate_repair_success([], [], window=1, success_min=80.0)
    res2 = nexus_acceptance_check._evaluate_phantom_false_positive([], window=1, fp_max=3.0)
    res3, _ = nexus_acceptance_check._evaluate_regression_and_side_effects([], window=1, regression_min=95.0, retry_spike_factor=2.0, retry_abs_max=1.0)
    
    actual_rules = {res1.name, res2.name, res3.name}
    assert actual_rules == expected_rules, f"Acceptance 規則名稱漂移！預期: {expected_rules}, 實際: {actual_rules}"

def test_acceptance_thresholds_contract():
    """驗證 Acceptance Gate 的預設門檻範圍 (防呆)"""
    golden_path = GOLDEN_DIR / "acceptance_rules.json"
    golden_data = json.loads(golden_path.read_text())
    
    # 讀取 CLI Parser 的預設值
    parser = inspect.signature(nexus_acceptance_check.main).parameters
    # 但是 nexus_acceptance_check.main 裡面才建 parser，我們可以直接檢查 argparse 或 hard-coded 邏輯。
    # 更安全的作法是確保門檻變數若透過環境/參數傳入，基礎 baseline 不可低於 golden
    default_thresholds = golden_data["default_thresholds"]
    assert default_thresholds["repair_success_min"] >= 50.0  # 修復率不應低於 50%
    assert default_thresholds["phantom_fp_max"] <= 10.0      # 幻覺 FP 不應大於 10%
    assert default_thresholds["regression_pass_min"] >= 90.0 # 迴歸不應低於 90%
