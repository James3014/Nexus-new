import os
from typing import Dict, List, Any, Optional
from nexus.selection.contracts import SelectionVerdict
from nexus.selection.score_aggregator import ScoreAggregator
from nexus.calibration.tuner import TemperatureScaler

class ConfidenceCalibrator:
    """
    ⚖️ Task T4: Confidence Calibrator (Score Layer)
    職責: 對驗證分數進行物理校準，並可選應用 Temperature Scaling。
    """
    def __init__(self, tie_threshold: float = 0.05):
        self.tie_threshold = tie_threshold
        self.ts_enabled = os.getenv("NEXUS_USE_TS", "0") == "1"
        self.scaler = TemperatureScaler(temperature=1.2) # 基線溫度

    def calibrate(self, verdicts: List[Any], base_confidence: float) -> Dict[str, Any]:
        # 1. 彙總
        agg_data = ScoreAggregator.aggregate(verdicts)
        
        # 2. 應用 Temperature Scaling (若啟用)
        calibrated_confidence = base_confidence
        if self.ts_enabled:
            calibrated_confidence = self.scaler.apply(base_confidence)
            print(f"🌡️ [Calibration] Adjusted Confidence: {base_confidence:.2f} -> {calibrated_confidence:.2f}")
        
        # 3. 評分縮放 (模擬環境噪音補償)
        calibrated_scores = {cid: score * 1.05 for cid, score in agg_data["scores"].items()}
        
        return {
            "scores": calibrated_scores,
            "conflicts": agg_data["conflicts"],
            "tie_threshold": self.tie_threshold,
            "calibrated_confidence": calibrated_confidence
        }
