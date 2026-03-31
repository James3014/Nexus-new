import logging
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set

logger = logging.getLogger(__name__)

@dataclass
class NexusTaskNode:
    """蜂群任務圖節點 (DAG Node)"""
    id: str
    description: str
    dependencies: List[str] = field(default_factory=list)
    status: str = "pending"  # pending, ready, running, completed, failed
    agent_role: str = "general"
    result: Optional[Any] = None

class TacticalGraphPlanner:
    """增強型蜂群計畫器 (Swarm Graph Planner)
    
    吸收 Automaton 的 Task Graph 基因，實現非線性任務調度與虛擬工作區隔離。
    數據真值轉向 Nexus 生產環境。
    """
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.nodes: Dict[str, NexusTaskNode] = {}
        self.worktree_paths: Dict[str, Path] = {}

    def add_task(self, task_id: str, desc: str, deps: List[str] = None, role: str = "general"):
        """物理注入一個任務節點及其依賴關係。"""
        node = NexusTaskNode(id=task_id, description=desc, dependencies=deps or [], agent_role=role)
        self.nodes[task_id] = node
        logger.info("swarm_task_added [%s] deps=%s", task_id, deps)

    def get_ready_tasks(self) -> List[NexusTaskNode]:
        """掃描 DAG 圖，提取所有依賴已滿足且可執行的「Ready」任務。"""
        ready = []
        completed_ids = {n_id for n_id, n in self.nodes.items() if n.status == "completed"}
        
        for n_id, node in self.nodes.items():
            if node.status != "pending":
                continue
            
            if all(dep in completed_ids for dep in node.dependencies):
                node.status = "ready"
                ready.append(node)
        
        return ready

    def create_virtual_workspace(self, task_id: str) -> Path:
        """物理建立 Git Worktree 作為任務的「虛擬工作區 (Virtual Workspace)」。"""
        worktree_path = self.project_root / ".nexus" / "workspaces" / task_id
        if worktree_path.exists():
            return worktree_path

        try:
            logger.info("creating_virtual_workspace_via_worktree [%s]", task_id)
            # 使用 git worktree add 建立隔離的物理開發空間
            subprocess.run(
                ["git", "worktree", "add", str(worktree_path), "HEAD"],
                cwd=str(self.project_root),
                check=True,
                capture_output=True
            )
            self.worktree_paths[task_id] = worktree_path
            return worktree_path
        except subprocess.CalledProcessError as exc:
            logger.error("virtual_workspace_creation_failed [%s]: %s", task_id, exc.stderr.decode())
            raise

    def cleanup_workspace(self, task_id: str):
        """物理清除 Git Worktree。數據真值收割完後必須清理。"""
        worktree_path = self.worktree_paths.get(task_id)
        if worktree_path and worktree_path.exists():
            subprocess.run(
                ["git", "worktree", "remove", str(worktree_path), "--force"],
                cwd=str(self.project_root),
                check=False
            )
            logger.info("virtual_workspace_cleaned [%s]", task_id)
