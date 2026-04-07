import pytest
from nexus.core.quantum_logic import calculate_stability, calculate_gain

def test_calculate_stability_zero_bias_should_error():
    # 物理證據偵查：驗證 bias 為 0 時是否正確報錯
    assert calculate_stability(0.0) == "ERROR"

def test_calculate_gain_standard_input():
    # 需求定義：calculate_gain 應根據輸入計算增益
    # 假設邏輯：gain = input * 1.5 (根據 Nexus 標準協議預測)
    assert calculate_gain(10.0) == 15.0

def test_calculate_gain_negative_input_should_raise():
    with pytest.raises(ValueError, match="Gain input must be positive"):
        calculate_gain(-1.0)
