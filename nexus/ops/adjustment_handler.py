import time
import uuid
from typing import Dict, Any

class AdjustmentHandler:
    """
    ⚖️ Task M2: Predictable Adjustments with Cooldown
    職責: 讓系統的調節動作具備確定性與「反激盪」能力。
    """
    COOLDOWN_SECONDS = 3600 # 預設冷卻時間 1 小時
    _last_adjustment_time = 0

    @staticmethod
    def request_adjustment(trigger_score, action, rationale) -> Dict[str, Any]:
        current_time = time.time()
        
        # 檢查冷卻時間，防止控制迴路振盪 (SoC: 抑制抖動)
        if current_time - AdjustmentHandler._last_adjustment_time < AdjustmentHandler.COOLDOWN_SECONDS:
            return {
                'status': 'COOLDOWN_BLOCKED',
                'remaining_seconds': int(AdjustmentHandler.COOLDOWN_SECONDS - (current_time - AdjustmentHandler._last_adjustment_time)),
                'rationale': 'Prevents oscillation in the control loop.'
            }
        
        AdjustmentHandler._last_adjustment_time = current_time
        
        return {
            'adjustment_id': str(uuid.uuid4()),
            'timestamp': current_time,
            'trigger_score': trigger_score,
            'action': action,
            'rationale': rationale,
            'status': 'EXECUTED',
            'replayable': True
        }
