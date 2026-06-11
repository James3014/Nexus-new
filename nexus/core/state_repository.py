from pathlib import Path
import json
import os
from nexus.core.state_contracts import NexusState
from nexus.core.config import NexusGlobalConfig

class StateRepository:
    def __init__(self, path: Path):
        self.path = Path(path)

    def save(self, state: NexusState):
        import tempfile
        json_data = state.model_dump_json()

        # 🧪 [v26.2] Atomic Overwrite: write-then-rename to prevent corruption and bloat
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=str(self.path.parent), suffix=".tmp"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write(json_data)
            os.replace(tmp_path, str(self.path))
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def load(self) -> NexusState:
        if not self.path.exists():
            return NexusState(task_id="new-task")

        try:
            content = self.path.read_text(encoding="utf-8").strip()
            if not content:
                return NexusState(task_id="empty")
            return NexusState.model_validate_json(content)
        except Exception as exc:
            # Fail-closed: do not swallow file corruption
            raise RuntimeError(f"State corruption detected in {self.path}: {exc}") from exc
