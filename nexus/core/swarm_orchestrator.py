from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from nexus.executors.protocol import ExecutorOutput, ExecutorStatusEnum
from nexus.core.state_contracts import NexusState, StepRecord

class TypedHandoffAdapter:
    """
    🧬 Typed Handoff Adapter (v22 Swarm)
    功能：將執行器輸出 (ExecutorOutput) 標準化並同步至 NexusState。
    原則：重用既有契約，強化 Phase 核驗。
    """
    VALID_PHASES = {"P", "D", "X", "R", "A", "C"}
    # 🧬 v22 Adaptive Mapping: 支援長名稱回退至核心字母
    PHASE_MAP = {
        "PLAN": "P", "PREPARE": "P",
        "DEBUG": "D", "DEVELOP": "D",
        "EXPLORE": "X", "X-RAY": "X", "OBSERVE": "X",
        "RESEARCH": "R", "REVIEW": "R",
        "AUDIT": "A", "ACCEPT": "A",
        "CRYSTALLIZE": "C", "COMMIT": "C"
    }

    def sync_output_to_state(self, state: NexusState, output: ExecutorOutput) -> NexusState:
        """將 ExecutorOutput 資料流對接至 NexusState 體系"""
        
        # 1. Phase 安全校核 (Gatekeeper)
        raw_phase = output.phase.upper()
        phase = self.PHASE_MAP.get(raw_phase, raw_phase) # 優先對應，否則維持原樣
        
        if phase not in self.VALID_PHASES:
            raise ValueError(f"Invalid phase: {raw_phase} (mapped to: {phase}). Must be one of {self.VALID_PHASES}")

        # 2. 狀態映射與枚舉轉譯
        # 將 ExecutorStatusEnum 映射至 StepRecord 狀態
        status_map = {
            ExecutorStatusEnum.SUCCESS: "completed",
            ExecutorStatusEnum.NO_PATCH: "completed",
            ExecutorStatusEnum.PROVIDER_ERROR: "failed",
            ExecutorStatusEnum.EXECUTION_FAIL: "failed",
        }
        step_status = status_map.get(output.status, "failed")

        # 3. 建立 StepRecord (PXDRAC 歷程記錄)
        new_step = StepRecord(
            phase=phase,
            step_id=f"{phase}_{output.executor_name}_{int(datetime.now().timestamp())}",
            status=step_status,
            started_at=datetime.now(), # 簡化起見，此處重啟
            ended_at=datetime.now(),
            summary=output.summary,
            metadata={
                "executor": output.executor_name,
                "exit_code": output.raw_exit_code,
                "patch_generated": output.patch_generated,
                "files_touched": output.files_touched,
                "artifacts": output.artifacts
            }
        )

        # 4. 更新 NexusState
        state.current_phase = phase
        state.current_step_id = new_step.step_id
        state.steps_history.append(new_step)
        
        # 如果 patch 成功，更新 metadata 中的 aos_score (compat field)
        if output.patch_generated and output.status == ExecutorStatusEnum.SUCCESS:
            current_score = float(state.metadata.get("aos_score", 0.0))
            state.metadata["aos_score"] = current_score + 0.5

        return state

class SwarmOrchestratorAdapter:
    """
    🎭 Swarm Orchestrator Adapter
    作為 NexusOrchestrator 的 Augmentation Layer (中繼協調層)。
    """
    def __init__(self, main_orchestrator: Any):
        self.main_orchestrator = main_orchestrator
        self.handoff = TypedHandoffAdapter()

    def process_swarm_outcome(self, outcome: ExecutorOutput):
        """處理群集任務結果，並同步至主編排器狀態"""
        current_state = getattr(self.main_orchestrator, "state", None)
        if current_state and isinstance(current_state, NexusState):
            updated_state = self.handoff.sync_output_to_state(current_state, outcome)
            self.main_orchestrator.state = updated_state
            print(
                f"✅ [SwarmOrchestrator] State synced: Phase {outcome.phase} | "
                f"AOS: {updated_state.metadata.get('aos_score', 0.0)}"
            )
