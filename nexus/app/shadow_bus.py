from __future__ import annotations
import os
import json
import time
import logging
import concurrent.futures
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

@dataclass
class ShadowTask:
    task_id: str
    intent: str
    mode: str
    status: str
    start_time: float
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

def _execute_shadow_worker(task_id: str, intent: str, mode: str) -> Dict[str, Any]:
    """頂層函數，避免 pickle 錯誤"""
    try:
        # 模擬背景預演邏輯
        time.sleep(1)
        return {
            "task_id": task_id,
            "status": "SUCCESS",
            "trajectory": f"Path for {intent} validated via {mode}",
            "confidence": 0.88,
            "advice": f"Spec for {intent} pre-generated."
        }
    except Exception as e:
        return {"task_id": task_id, "status": "FAILED", "error": str(e)}

class ShadowBus:
    def __init__(self, project_root: Path, max_workers: int = 4):
        self.project_root = project_root
        self.shadow_dir = self.project_root / ".nexus" / "shadow_runs"
        self.shadow_dir.mkdir(parents=True, exist_ok=True)
        self.executor = concurrent.futures.ProcessPoolExecutor(max_workers=max_workers)
        self.active_tasks: Dict[str, ShadowTask] = {}

    def spawn_speculative_run(self, task_id: str, intent: str, mode: str = "hyper") -> str:
        task = ShadowTask(
            task_id=task_id, intent=intent, mode=mode,
            status="running", start_time=time.time()
        )
        self.active_tasks[task_id] = task
        future = self.executor.submit(_execute_shadow_worker, task_id, intent, mode)
        future.add_done_callback(lambda f: self._on_task_complete(task_id, f))
        return task_id

    def _on_task_complete(self, task_id: str, future: concurrent.futures.Future):
        try:
            result = future.result()
            task = self.active_tasks.get(task_id)
            if task:
                task.status = "completed" if result.get("status") == "SUCCESS" else "failed"
                task.result = result
                self._persist_shadow_log(task)
        except Exception as e:
            print(f"Task {task_id} failed: {e}")

    def _persist_shadow_log(self, task: ShadowTask):
        log_file = self.shadow_dir / f"{task.task_id}.json"
        log_file.write_text(json.dumps(asdict(task), indent=2, ensure_ascii=False))

    def get_advice(self, task_id: str) -> Optional[Dict[str, Any]]:
        task = self.active_tasks.get(task_id)
        if task and task.status == "completed":
            return task.result
        return None

if __name__ == '__main__':
    bus = ShadowBus(Path("."))
    tid = bus.spawn_speculative_run("smoke_001", "Test Oracle Engine")
    print(f"Spawned: {tid}")
    time.sleep(2)
    advice = bus.get_advice(tid)
    print(f"Result: {advice}")
