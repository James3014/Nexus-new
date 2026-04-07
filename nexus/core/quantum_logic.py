def calculate_stability(bias: float):
    # 物理證據修復：對於 0.0 或極小偏置應精確回傳 ERROR
    if abs(bias) < 0.0000001:
        return "ERROR"
    return "STABLE"

def calculate_gain(value: float):
    # 根據 Nexus 標準增益協議 1.5 實作
    if value < 0:
        raise ValueError("Gain input must be positive")
    return value * 1.5

def verify_nexus_core():
    # 模擬核心檢查
    return calculate_stability(0.0) == "ERROR"
