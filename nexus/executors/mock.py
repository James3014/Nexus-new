import time
from .base import BaseExecutor
from .protocol import ExecutorInput, ExecutorOutput, ExecutorStatusEnum, ProviderErrorType, RepairResult, ExecutionEvidence, ExecutorMeta

class MockExecutor(BaseExecutor):
    """
    Mock 執行器：用於驗證 Nexus Core 的協議完整性與 Workflow 循環。
    支援模擬多種執行狀態。
    """
    
    def __init__(self, mode: str = "SUCCESS"):
        self.mode = mode

    def execute(self, input_data: ExecutorInput) -> ExecutorOutput:
        """根據模式模擬回傳。"""
        start_time = time.time()
        
        if self.mode == "SUCCESS":
            return ExecutorOutput(
                executor_name="mock_executor",
                phase=input_data.phase,
                status=ExecutorStatusEnum.SUCCESS,
                patch_generated=True,
                evidence_present=True,
                raw_exit_code=0,
                files_touched=["mock_file.py"],
                summary="[Mock] Successfully fixed the issue.",
                patch_diff="--- a/mock_file.py\n+++ b/mock_file.py\n@@ -1,1 +1,1 @@\n-old\n+new",
                diagnosis="[Mock] Root cause identified as a typo.",
                meta={"model": "mock-v1", "latency_ms": 100}
            )
            
        elif self.mode == "NO_PATCH":
            return ExecutorOutput(
                executor_name="mock_executor",
                phase=input_data.phase,
                status=ExecutorStatusEnum.NO_PATCH,
                patch_generated=False,
                evidence_present=False,
                raw_exit_code=0,
                summary="[Mock] No changes needed. All checks passed.",
                meta={"model": "mock-v1"}
            )
            
        elif self.mode == "QUOTA":
            return ExecutorOutput(
                executor_name="mock_executor",
                phase=input_data.phase,
                status=ExecutorStatusEnum.PROVIDER_ERROR,
                patch_generated=False,
                evidence_present=False,
                raw_exit_code=1,
                provider_error_type=ProviderErrorType.QUOTA_LIMIT,
                summary="[Mock] Rate limit exceeded.",
                meta={"model": "mock-v1"}
            )
            
        else: # EXECUTION_FAIL
            return ExecutorOutput(
                executor_name="mock_executor",
                phase=input_data.phase,
                status=ExecutorStatusEnum.EXECUTION_FAIL,
                patch_generated=False,
                evidence_present=False,
                raw_exit_code=127,
                stderr_excerpt="Command not found or crashed.",
                summary="[Mock] Executor crashed abnormally.",
                meta={"model": "mock-v1"}
            )
