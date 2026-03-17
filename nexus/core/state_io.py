from pathlib import Path
from typing import Any, Optional
from nexus.core.state_contracts import NexusState
from nexus.core.state_repository import StateRepository
from nexus.core.metrics_writer import MetricsWriter
from nexus.core.contract_writer import ContractWriter

class StateIO:
    """
    💾 Nexus State IO Manager (Facade)
    負責狀態的持久化與讀取，授權給 Repository 與 Writers 處理。
    """
    def __init__(
        self,
        project_root: str,
        state_file: Optional[str] = None,
        run_dir: Optional[str] = None,
    ):
        self.project_root = Path(project_root).resolve()
        self.run_dir = Path(run_dir) if (run_dir and str(run_dir) != "None") else None
        
        if self.run_dir:
            self.run_dir.mkdir(parents=True, exist_ok=True)
            self.state_file = self.run_dir / ".musestate"
        elif state_file:
            self.state_file = Path(state_file)
        else:
            noise_dir = self.project_root / ".nexus" / "misc"
            noise_dir.mkdir(parents=True, exist_ok=True)
            self.state_file = noise_dir / ".musestate"
            
        self.repository = StateRepository(self.state_file)
        
        metrics_file = self.run_dir / ".nexus_metrics" if self.run_dir else self.state_file.parent / ".nexus_metrics"
        self.metrics_writer = MetricsWriter(metrics_file)
        
        contract_base = self.run_dir if self.run_dir else self.state_file.parent
        self.contract_writer = ContractWriter(contract_base)

    def load_global_state(self) -> NexusState:
        return self.repository.load()

    def save_global_state(self, state: NexusState):
        self.repository.save(state)
        self.metrics_writer.write(
            task_id=state.task_id,
            tokens=state.total_token_usage,
            audit_pass=state.audit_pass_count,
            retries=state.retry_count
        )

    def write_contract(self, filename: str, data: Any):
        self.contract_writer.write(filename, data)
