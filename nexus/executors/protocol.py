from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

class ProviderErrorType(Enum):
    """標準化 Provider 錯誤分類 (Enum)。"""
    QUOTA_LIMIT = "QUOTA_LIMIT"
    MODEL_UNSUPPORTED = "MODEL_UNSUPPORTED"
    SCHEMA_VIOLATION = "SCHEMA_VIOLATION"
    PROVIDER_CONTRACT_VIOLATION = "PROVIDER_CONTRACT_VIOLATION"
    OUTPUT_TRUNCATED = "OUTPUT_TRUNCATED"
    EXECUTOR_TIMEOUT = "EXECUTOR_TIMEOUT"
    AGENT_TOOL_INTERFERENCE = "AGENT_TOOL_INTERFERENCE"
    SANDBOX_PERMISSION_ERROR = "SANDBOX_PERMISSION_ERROR"
    EXECUTOR_RUNTIME_ERROR = "EXECUTOR_RUNTIME_ERROR"
    UNKNOWN_PROVIDER_ERROR = "UNKNOWN_PROVIDER_ERROR"

class ExecutorStatusEnum(Enum):
    """執行器運作狀態 (Enum)。"""
    SUCCESS = "SUCCESS"
    NO_PATCH = "NO_PATCH"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    EXECUTION_FAIL = "EXECUTION_FAIL"

@dataclass
class RepairResult:
    """修復結果概要。"""
    summary: str
    patch_diff: Optional[str] = None

@dataclass
class ExecutionEvidence:
    """執行證據包。"""
    files_touched: List[str] = field(default_factory=list)
    raw_output: str = ""

@dataclass
class ExecutorMeta:
    """執行器元數據。"""
    model_name: str
    latency_ms: int = 0
    tokens_input: int = 0
    tokens_output: int = 0

class WorkspaceMeta(Enum):
    """工作區元數據模式 (選填)。"""
    ISOLATED = "ISOLATED"
    LOCAL = "LOCAL"

@dataclass
class TaskInstruction:
    """任務指令 (必填)。"""
    task_id: str
    objective: str
    constraints: List[str] = field(default_factory=list)
    rules: List[str] = field(default_factory=list)

@dataclass
class ContextPackSchema:
    """上下文包 (必填)。"""
    files: Dict[str, str] = field(default_factory=dict)
    linter_errors: List[Dict[str, Any]] = field(default_factory=list)
    history: List[str] = field(default_factory=list)

@dataclass
class ExecutorInput:
    """執行器輸入 (必填分層)。"""
    task_id: str
    phase: str
    workspace_root: str
    context_pack: ContextPackSchema
    rules: List[str] = field(default_factory=list)
    instruction: Optional[TaskInstruction] = None # 選填細節
    self_hosted_contract: Optional[Dict[str, Any]] = None

@dataclass
class ExecutorOutput:
    """執行器輸出 (必填/選填分層)。"""
    # --- 必填欄位 (Mandatory) ---
    executor_name: str
    phase: str
    status: ExecutorStatusEnum
    patch_generated: bool
    evidence_present: bool
    raw_exit_code: int
    files_touched: List[str] = field(default_factory=list)
    summary: str = ""

    # --- 選填欄位 (Optional) ---
    patch_diff: Optional[str] = None
    diagnosis: Optional[str] = None
    provider_error_type: Optional[ProviderErrorType] = None
    stderr_excerpt: Optional[str] = None
    artifacts: Dict[str, str] = field(default_factory=dict) # key -> path
    meta: Dict[str, Any] = field(default_factory=dict) 
