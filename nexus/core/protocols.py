from typing import Protocol, Any, Dict, List, Optional
from pathlib import Path

class EngineProtocol(Protocol):
    """Protocol for NexusEngine."""
    project_root: Path
    run_dir: Optional[Path]

    def run_bug(self, task_desc: str, **kwargs) -> Dict[str, Any]:
        """Runs a bug fix task."""
        ...

    def run_feature(self, task_desc: str, **kwargs) -> Dict[str, Any]:
        """Runs a new feature task."""
        ...

    def run_benchmark(self, manifest_path: str, **kwargs) -> None:
        """Runs a benchmark suite."""
        ...

class PipelineProtocol(Protocol):
    """Protocol for NexusPipeline."""
    def run(self, state: Any, **kwargs) -> Dict[str, Any]:
        """Runs the pipeline with the given state."""
        ...

class MemoryProtocol(Protocol):
    """Protocol for MemoryService."""
    def semantic_search(self, query: str, table_name: str = "policy", limit: int = 3) -> List[Dict[str, Any]]:
        """Performs semantic search."""
        ...

    def aggregate_memory(self, query: Optional[str] = None) -> Dict[str, Any]:
        """Aggregates memory sources."""
        ...


class PipelineContextProtocol(Protocol):
    """
    R17: Pipeline 單次執行上下文的協議介面。
    替換所有 Mixin 方法簽章中的 `ctx: Any`，提供靜態型別安全。
    """
    # ── 識別欄位 ──────────────────────────────────────────────
    task_id: str
    task_desc: str
    task_type: str      # "bug" | "feature"
    dry_run: bool
    decision_counter: int

    # ── 注入的服務元件 ─────────────────────────────────────────
    state: Any          # NexusState — 避免循環 import，保留 Any
    planner: Any
    hub: Any            # ContextHub
    repairer: Any
    researcher: Any
    accumulator: Any    # TokenAccumulator
    event_store: Any    # EventStore (nullable)
    research_policy: Any

    # ── 執行時狀態 ─────────────────────────────────────────────
    pack: Dict[str, Any]
    prediction: Dict[str, Any]
    research_pack: Dict[str, Any]
    kwargs: Dict[str, Any]


class LinterProtocol(Protocol):
    """R11: Linter 服務介面。"""
    def scan(self, files: List[str]) -> Dict[str, Any]: ...


class GitProtocol(Protocol):
    """R11: Git 服務介able面。"""
    project_root: Path
    def get_changes(self, scope: str, base_ref: str) -> tuple[List[str], str]: ...


class ReviewerProtocol(Protocol):
    """R11: 審核器服務介面。"""
    execution_mode: str
    persona_hint: str
    task: str
    scope: str
    base_ref: str
    apply_patch: bool
    
    linter: LinterProtocol
    git: GitProtocol
    llm: Any # 避免循環，保留 Any
    patcher: Any
    context_hub: Any

    def set_execution_mode(self, mode: str, reason: str) -> None: ...
    def _build_review_result(self, status: str, summary: str, **kwargs) -> Dict[str, Any]: ...
    def _record_tokens(self, data: Dict[str, Any]) -> None: ...
    def _collect_physical_proof(self, files: List[str]) -> tuple[str, str]: ...
