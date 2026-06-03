from typing import List
from nexus.calibration.models import ReliabilitySlice

class CalibrationMetrics:
    """
    📈 Task T3: Reliability Metrics
    職責: 計算 ECE (Expected Calibration Error) 與可信度分布報表。
    """
    @staticmethod
    def compute_ece(bins: List[ReliabilitySlice]) -> float:
        total_samples = sum(b.sample_count for b in bins)
        if total_samples == 0: return 0.0
        
        ece = 0.0
        for b in bins:
            # ECE = sum( (bin_count / total) * abs(conf - acc) )
            error = abs(b.mean_confidence - b.observed_accuracy)
            weight = b.sample_count / total_samples
            ece += weight * error
        return ece
