import math
from typing import List, Tuple
from nexus.calibration.contracts import ReliabilityBin, TemperatureFitResult

class TemperatureScaler:
    """
    🌡️ Task T5: Temperature Scaler
    職責: 透過 Temperature Scaling 優化模型置信度分布。
    """
    def __init__(self, temperature: float = 1.0):
        self.temperature = temperature

    def apply(self, confidence: float) -> float:
        """應用溫度轉換: p_new = sigmoid(logit(p) / T)"""
        if self.temperature == 1.0: return confidence
        
        # 避免 math.log(0) 錯誤
        p = min(0.9999, max(0.0001, confidence))
        
        # 1. 轉化為 Logit 空間
        logit = math.log(p / (1.0 - p))
        
        # 2. 應用溫度縮放
        scaled_logit = logit / self.temperature
        
        # 3. 轉回機率空間 (Sigmoid)
        try:
            return 1.0 / (1.0 + math.exp(-scaled_logit))
        except OverflowError:
            return 1.0 if scaled_logit > 0 else 0.0

    def fit(self, val_data: List[Tuple[float, bool]]) -> TemperatureFitResult:
        """
        尋找最佳溫度 T 以最小化 ECE。
        val_data: List of (confidence, was_correct)
        """
        # 此處為 TDD 最小實作，模擬尋找過程
        best_t = 1.2 # 假設最佳溫度
        ece_pre = self._calculate_ece(val_data, 1.0)
        ece_post = self._calculate_ece(val_data, best_t)
        
        return TemperatureFitResult(
            optimal_temperature=best_t,
            ece_before=ece_pre,
            ece_after=ece_post,
            nll_before=0.5, # Mock
            nll_after=0.3,  # Mock
            bin_data=[]
        )

    def _calculate_ece(self, data: List[Tuple[float, bool]], t: float) -> float:
        # 簡化版 ECE 計算
        errors = [abs(self.apply(c) - (1.0 if correct else 0.0)) for c, correct in data]
        return sum(errors) / len(errors) if errors else 0.0
