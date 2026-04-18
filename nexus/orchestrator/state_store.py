import json
from pathlib import Path
from typing import Dict, Optional
from nexus.orchestrator.task_contract import Task

class StateStore:
    def __init__(self, storage_dir: str = ".nexus/multi_agent/tasks"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def save_task(self, task: Task):
        path = self.storage_dir / f"{task.task_id}.json"
        with open(path, "w") as f:
            f.write(task.model_dump_json(indent=2))

    def load_task(self, task_id: str) -> Optional[Task]:
        path = self.storage_dir / f"{task_id}.json"
        if not path.exists():
            return None
        with open(path, "r") as f:
            return Task.model_validate_json(f.read())

    def list_tasks(self) -> Dict[str, Task]:
        tasks = {}
        for path in self.storage_dir.glob("*.json"):
            task = Task.model_validate_json(path.read_text())
            tasks[task.task_id] = task
        return tasks
# integrity-seal: 1776512137
