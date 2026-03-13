import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime
from core.state_contracts import NexusState, StepRecord

class StateIO:
    """
    💾 Nexus State IO Manager
    負責狀態的持久化與讀取，支援 .musestate JSONL 與各階段 JSON 合同。
    """
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.state_file = self.project_root / ".musestate"
        
    def load_global_state(self) -> NexusState:
        """從 .musestate 讀取最新的全域狀態。"""
        if not self.state_file.exists():
            return NexusState(task_id="new-task")
            
        # 讀取 JSONL 的最後一行作為當前狀態 (簡化版)
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                if not lines:
                    return NexusState(task_id="empty-task")
                last_line = json.loads(lines[-1].strip())
                return NexusState(**last_line)
        except Exception as e:
            print(f"⚠️ [StateIO] Failed to load state: {e}")
            return NexusState(task_id="error-task")

    def save_global_state(self, state: NexusState):
        """將狀態追加到 .musestate JSONL 中。"""
        # Pydantic v2 使用 model_dump_json() 或 model_dump()
        data = state.model_dump()
        # 轉換 datetime 為 string
        def json_serial(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError("Type not serializable")

        with open(self.state_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, default=json_serial) + "\n")
        print(f"💾 [StateIO] Global state persisted to {self.state_file}")

    def write_contract(self, filename: str, data: Any):
        """寫入通用的 JSON 合同檔案 (如 plan.json, diagnosis.json)。"""
        target = self.project_root / filename
        with open(target, "w", encoding="utf-8") as f:
            if hasattr(data, "model_dump"):
                json.dump(data.model_dump(), f, indent=4)
            else:
                json.dump(data, f, indent=4)
        print(f"📄 [StateIO] Contract {filename} written.")

if __name__ == "__main__":
    # 簡單測試
    io = StateIO(".")
    state = io.load_global_state()
    state.current_phase = "D"
    state.steps_history.append(StepRecord(
        phase="P", step_id="init", status="completed", 
        started_at=datetime.now(), ended_at=datetime.now()
    ))
    io.save_global_state(state)
