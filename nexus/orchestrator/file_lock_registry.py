import json
import os
from pathlib import Path
from typing import Dict, List, Set, Optional
from pydantic import BaseModel

class LockEntry(BaseModel):
    task_id: str
    files: List[str]

class FileLockRegistry:
    def __init__(self, lock_file: str = ".nexus/multi_agent/locks/file_locks.json"):
        self.lock_file = Path(lock_file)
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        self.locks: Dict[str, str] = {} # file_path -> task_id
        self._load()

    def _load(self):
        if self.lock_file.exists():
            try:
                with open(self.lock_file, "r") as f:
                    data = json.load(f)
                    self.locks = data.get("locks", {})
            except Exception:
                self.locks = {}

    def _save(self):
        with open(self.lock_file, "w") as f:
            json.dump({"locks": self.locks}, f, indent=2)

    def acquire(self, task_id: str, files: List[str]) -> List[str]:
        """
        Attempts to acquire locks for a list of files.
        Returns a list of conflicting files (files already locked by others).
        If no conflicts, saves the locks and returns an empty list.
        """
        conflicts = []
        for f in files:
            normalized_path = os.path.normpath(f)
            if normalized_path in self.locks and self.locks[normalized_path] != task_id:
                conflicts.append(normalized_path)
        
        if not conflicts:
            for f in files:
                normalized_path = os.path.normpath(f)
                self.locks[normalized_path] = task_id
            self._save()
        
        return conflicts

    def release(self, task_id: str):
        """Releases all locks held by a task."""
        to_remove = [f for f, t in self.locks.items() if t == task_id]
        for f in to_remove:
            del self.locks[f]
        if to_remove:
            self._save()

    def check_access(self, task_id: str, file_path: str) -> bool:
        """Checks if a task has access to a specific file."""
        normalized_path = os.path.normpath(file_path)
        return self.locks.get(normalized_path) == task_id

    def get_task_files(self, task_id: str) -> List[str]:
        """Returns all files currently locked by a task."""
        return [f for f, t in self.locks.items() if t == task_id]
# v24.13 final hardening
