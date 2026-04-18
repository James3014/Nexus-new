import pytest
from nexus.orchestrator.file_lock_registry import FileLockRegistry
import json

def test_file_lock_acquire_success(tmp_path):
    lock_file = tmp_path / "locks.json"
    registry = FileLockRegistry(lock_file=str(lock_file))
    
    task_id = "TASK-001"
    files = ["src/main.py", "tests/test_main.py"]
    conflicts = registry.acquire(task_id, files)
    
    assert not conflicts
    assert registry.check_access(task_id, "src/main.py")
    assert registry.get_task_files(task_id) == ["src/main.py", "tests/test_main.py"]

def test_file_lock_conflict(tmp_path):
    lock_file = tmp_path / "locks.json"
    registry = FileLockRegistry(lock_file=str(lock_file))
    
    registry.acquire("TASK-001", ["src/main.py"])
    conflicts = registry.acquire("TASK-002", ["src/main.py", "src/utils.py"])
    
    assert conflicts == ["src/main.py"]
    assert registry.check_access("TASK-001", "src/main.py")
    assert not registry.check_access("TASK-002", "src/main.py")

def test_file_lock_release(tmp_path):
    lock_file = tmp_path / "locks.json"
    registry = FileLockRegistry(lock_file=str(lock_file))
    
    registry.acquire("TASK-001", ["src/main.py"])
    registry.release("TASK-001")
    
    assert not registry.locks
    assert not registry.check_access("TASK-001", "src/main.py")

def test_file_lock_persistence(tmp_path):
    lock_file = tmp_path / "locks.json"
    registry = FileLockRegistry(lock_file=str(lock_file))
    registry.acquire("TASK-001", ["src/main.py"])
    
    # Reload from disk
    registry2 = FileLockRegistry(lock_file=str(lock_file))
    assert registry2.check_access("TASK-001", "src/main.py")
# integrity-seal: 1776512137
