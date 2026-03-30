from typing import Dict, Any, List, Optional
from pathlib import Path
from nexus.core.protocols import EngineProtocol, PipelineProtocol, MemoryProtocol

class StubEngine(EngineProtocol):
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.run_dir = self.project_root / "run"

    def run_bug(self, task_desc: str, **kwargs) -> Dict[str, Any]:
        return {"status": "success", "task_id": "stub-bug-123"}

    def run_feature(self, task_desc: str, **kwargs) -> Dict[str, Any]:
        return {"status": "success", "task_id": "stub-feat-123"}

    def run_benchmark(self, manifest_path: str, **kwargs) -> None:
        pass

class StubPipeline(PipelineProtocol):
    def run(self, state: Any, **kwargs) -> Dict[str, Any]:
        return {"status": "success", "trace_id": "stub-trace-456"}

class StubMemory(MemoryProtocol):
    def semantic_search(self, query: str, table_name: str = "policy", limit: int = 3) -> List[Dict[str, Any]]:
        return [{"id": "stub-rule-1", "content": "stub-content", "relevance": 0.9}]

    def aggregate_memory(self, query: Optional[str] = None) -> Dict[str, Any]:
        return {"reminders": [], "total_sources": 0}
