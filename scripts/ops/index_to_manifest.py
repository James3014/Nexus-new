import re
import yaml
import os
import sys

INDEX_PATH = "docs/INDEX.md"
MANIFEST_PATH = "task_manifest.yaml"

# 定義模組與 Worker 的映射關係
OWNERSHIP_MAP = {
    "infra": "worker-1",
    "scripts/ops": "worker-1",
    "gate": "worker-2",
    "tests": "worker-2",
    "core/memory": "worker-3",
    "core/policy": "worker-3",
    "docs": "worker-4",
    "INDEX": "worker-4"
}

def parse_index_next():
    if not os.path.exists(INDEX_PATH):
        return []
    with open(INDEX_PATH, "r") as f:
        content = f.read()
    
    next_section = re.search(r"## Next\n(.*?)(?=\n##|\Z)", content, re.DOTALL)
    if not next_section:
        return []
    
    tasks = []
    for line in next_section.group(1).strip().split("\n"):
        match = re.search(r"^\d+\.\s*(.*)", line.strip())
        if match:
            tasks.append(match.group(1).strip())
    return tasks

def assign_worker(task_name):
    for path, worker in OWNERSHIP_MAP.items():
        if path in task_name.lower():
            return worker
    return "worker-1"  # 預設分配給 infra

def sync_manifest(next_tasks):
    with open(MANIFEST_PATH, "r") as f:
        manifest = yaml.safe_load(f)
    
    current_tasks = {t["id"] for t in manifest.get("tasks", [])}
    
    for i, task_text in enumerate(next_tasks):
        task_id = f"index.task.{i+1}"
        if task_id not in current_tasks:
            worker = assign_worker(task_text)
            new_task = {
                "id": task_id,
                "description": task_text,
                "worker": worker,
                "depends_on": [manifest["tasks"][-1]["id"]] if manifest.get("tasks") else [],
                "run": f"uv run scripts/engine/nexus_cli.py nexus:runner --task {task_id}",
                "done_when": {"type": "phase_result_ok"}
            }
            manifest.setdefault("tasks", []).append(new_task)
            print(f"  [+] Assigned to {worker}: {task_text}")

    with open(MANIFEST_PATH, "w") as f:
        yaml.dump(manifest, f, sort_keys=False)

if __name__ == "__main__":
    tasks = parse_index_next()
    sync_manifest(tasks)
