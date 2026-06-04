import time
import uuid
from typing import Dict, Any, Optional, Callable

class AdjustmentHandler:
    """
    ⚖️ Task M2: Predictable Adjustments with Cooldown
    職責: 讓系統的調節動作具備確定性與「反激盪」能力。
    """
    COOLDOWN_SECONDS = 3600 
    _last_adjustment_time = 0

    @staticmethod
    def request_adjustment(trigger_score: float, 
                           action: str, 
                           rationale: str,
                           clock: Callable[[], float] = time.time,
                           id_gen: Callable[[], str] = lambda: str(uuid.uuid4())) -> Dict[str, Any]:
        """
        支援時鐘與 ID 產生器注入，確保測試確定性。
        """
        current_time = clock()
        
        # 抑制控制迴路振盪 (Damping)
        if current_time - AdjustmentHandler._last_adjustment_time < AdjustmentHandler.COOLDOWN_SECONDS:
            return {
                'status': 'COOLDOWN_BLOCKED',
                'remaining_seconds': int(AdjustmentHandler.COOLDOWN_SECONDS - (current_time - AdjustmentHandler._last_adjustment_time)),
                'rationale': 'Prevents oscillation in the control loop.'
            }
        
        AdjustmentHandler._last_adjustment_time = current_time
        
        return {
            'adjustment_id': id_gen(),
            'timestamp': current_time,
            'trigger_score': trigger_score,
            'action': action,
            'rationale': rationale,
            'status': 'EXECUTED',
            'replayable': True
        }
