from pathlib import Path
import json
from nexus.core.state_contracts import NexusState

class StateRepository:
    def __init__(self, path: Path):
        self.path = Path(path)
        
    def save(self, state: NexusState):
        data = state.model_dump()
        with open(self.path, "a", encoding="utf-8") as f:
            # Handle datetime serialization if needed, model_dump(mode='json') is Pydantic v2
            f.write(state.model_dump_json() + "\n")
            
    def load(self) -> NexusState:
        if not self.path.exists():
            return NexusState(task_id="new-task")
        with open(self.path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            if not lines:
                return NexusState(task_id="empty")
            return NexusState.model_validate_json(lines[-1].strip())
