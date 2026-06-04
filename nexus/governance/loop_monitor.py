from typing import List

class LoopMonitor:
    """
    👁️ Task M4: Meta-Monitoring & Safety Halt
    職責: 監控治理迴路本身的穩定性，識別振盪並在需要時安全停機。
    """
    OSCILLATION_THRESHOLD = 0.3 # 變動率超過 30% 視為失穩
    MAX_HISTORY = 10

    @staticmethod
    def evaluate_loop_stability(history: List[float]) -> dict:
        if len(history) < 3:
            return {"status": "INSUFFICIENT_DATA", "safety_halt": False}
        
        # 使用滑動平均值的變動率來偵測振盪
        history = history[-LoopMonitor.MAX_HISTORY:]
        variances = [abs(history[i] - history[i-1]) for i in range(1, len(history))]
        avg_variance = sum(variances) / len(variances)
        
        if avg_variance > LoopMonitor.OSCILLATION_THRESHOLD:
            return {
                "status": "OSCILLATING",
                "avg_variance": round(avg_variance, 3),
                "safety_halt": True,
                "reason": "Governance loop unstable. Triggering Safety Halt."
            }
            
        return {
            "status": "META_STABLE",
            "avg_variance": round(avg_variance, 3),
            "safety_halt": False
        }
