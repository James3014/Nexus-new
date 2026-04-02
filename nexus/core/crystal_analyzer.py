from typing import Any, Dict, List, Optional, Tuple
import json
from datetime import datetime
from nexus.core.state_contracts import NexusState, TraumaRecord

class TraumaEngine:
    """🧠 Trinity Trauma Engine: 將失敗轉化為負向權重 (PHA-040)"""
    
    @staticmethod
    def process_failures(state: NexusState):
        """分析 A 階段失敗紀錄並更新 Trauma"""
        last_audit = None
        for step in reversed(state.steps_history):
            if step.phase == "A":
                last_audit = step
                break
        
        if last_audit and last_audit.status == "rejected":
            # 🛡️ 捕捉失敗簽章 (e.g., FileNotFoundError, ValidationError)
            signature = last_audit.metadata.get("error_type", "UnknownFailure")
            print(f"🧠 [TraumaEngine] Capturing trauma: {signature}")
            
            # 更新權重
            record = TraumaRecord(
                failure_signature=signature,
                penalty=-0.1, # 每個失敗懲罰 10%
                expiry=None # 目前永不過期
            )
            state.autonomic_weights.trauma_records.append(record)
            
            # 連動 Learning Velocity: (Success Rate - Failure Rate)
            trauma_count = len(state.autonomic_weights.trauma_records)
            state.learning_velocity = max(-1.0, 1.0 - (state.retry_count * 0.2) - (trauma_count * 0.1))
            
    @staticmethod
    def apply_weights(state: NexusState):
        """根據 Trauma 修正當前 Skill 權重"""
        # 未來整合至 SkillsRouter 
        pass
