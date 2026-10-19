from .base import BaseExecutor
from .protocol import (
    ExecutorInput, 
    ExecutorOutput, 
    ExecutorStatusEnum, 
    ProviderErrorType
)

class AntigravityExecutor(BaseExecutor):
    """
    🌌 AntigravityExecutor (V5 Steel Stub)
    用於驗證 Executor Swap 能力的正式適配器。
    """
    def __init__(self, model_name: str = "antigravity-v1"):
        self.model_name = model_name

    def execute(self, input_data: ExecutorInput, timeout: int = 60) -> ExecutorOutput:
        # 模擬一個簡單的成功回傳或錯誤，用於 Swap 測試
        return ExecutorOutput(
            executor_name="antigravity_stub",
            phase=input_data.phase,
            status=ExecutorStatusEnum.SUCCESS,
            patch_generated=False,
            evidence_present=True,
            raw_exit_code=0,
            files_touched=[],
            summary="Antigravity stub executed successfully for protocol verification.",
            meta={"model_name": self.model_name, "tokens_output": 0}
        )
