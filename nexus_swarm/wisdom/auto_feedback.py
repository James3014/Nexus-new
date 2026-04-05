# nexus_swarm/wisdom/auto_feedback.py
from typing import Dict, Any, List
from nexus_swarm.wisdom.feedback_api import FeedbackAPI

class AutoFeedback:
    def __init__(self, feedback_api=None):
        self.api = feedback_api or FeedbackAPI()
    
    def on_regression_detected(self, task_id: str, regression_files: List[str]):
        """
        🚀 當檢測到代碼回歸時，自動提交 Unsafe Missed。
        代表現有的 Wisdom 或 Guard 未能攔截此類風險。
        """
        return self.api.submit_feedback({
            'task_id': task_id,
            'pattern_id': f'regression-count-{len(regression_files)}',
            'type': 'unsafe_missed',
            'actor': 'auto_system',
            'source': 'regression_test',
            'notes': f'Files regressed: {", ".join(regression_files)}'
        })
    
    def on_false_positive_block(self, task_id: str, phantom_score: float):
        """
        🚀 當檢測到疑似假陽性攔截時，自動提交 False Positive。
        用於優化攔截精度，減少開發阻力。
        """
        return self.api.submit_feedback({
            'task_id': task_id,
            'pattern_id': 'phantom_block_fp',
            'type': 'false_positive',
            'actor': 'auto_system',
            'source': 'phantom_guard',
            'notes': f'Phantom score detected: {phantom_score:.2f}'
        })

if __name__ == "__main__":
    fb = AutoFeedback()
    print("🚀 [Auto Feedback] Initialized. Testing automated hooks...")
    res1 = fb.on_regression_detected("T-SIM-001", ["main.rs", "lib.rs"])
    print(f"Regression Hook: {res1['status']}")
    res2 = fb.on_false_positive_block("T-SIM-002", 0.88)
    print(f"FP Hook: {res2['status']}")
