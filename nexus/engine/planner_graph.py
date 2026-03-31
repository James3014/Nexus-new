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
    # --- v20 Hierarchical Data ---
    parent_id: Optional[str] = None
    sub_tasks: List[str] = field(default_factory=list)

class HierarchicalGraphPlanner:
    """分層蜂群計畫器 (v21-A Simple Global)
    
    實現 Level-0 (Global) 調度：根據延遲感知自動分發任務。
    數據真值轉向 Nexus 全球聯邦。
    """
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.nodes: Dict[str, NexusTaskNode] = {}
        self.worktree_paths: Dict[str, Path] = {}
        # v21-A: 全球叢集緩存
        self.cluster_metadata: List[Dict] = []

    def load_federation_context(self, fed_nodes: List[Dict]):
        """從聯邦層載入全球節點上下文。"""
        self.cluster_metadata = fed_nodes

    def pick_closest_cluster(self, capability: str = "swarm-dag") -> Optional[str]:
        """
        🎯 延遲感知選擇演算法 (Latency-Aware Selection)
        在具備能力的線上節點中，挑選延遲 (Latency) 最低的叢集。
        """
        candidates = [
            n for n in self.cluster_metadata 
            if n.get("status") == "ONLINE" and capability in n.get("capabilities", [])
        ]
        
        if not candidates:
            return "local-master"
            
        # 物理排序：延遲最低優先
        sorted_nodes = sorted(candidates, key=lambda x: x.get("latency", 999.0))
        best_node = sorted_nodes[0]
        
        logger.info("global_dispatch_selected [%s] region=%s latency=%.1fms", 
                    best_node['node_id'], best_node['region'], best_node['latency'])
        return best_node['node_id']

    def add_task(self, task_id: str, desc: str, deps: List[str] = None, role: str = "general", parent_id: str = None):
        """物理注入一個任務節點，支援父子層級關係與全球派發。"""
        node = NexusTaskNode(id=task_id, description=desc, dependencies=deps or [], agent_role=role, parent_id=parent_id)
        self.nodes[task_id] = node
        if parent_id and parent_id in self.nodes:
            self.nodes[parent_id].sub_tasks.append(task_id)
        logger.info("swarm_task_added [%s] parent=%s deps=%s", task_id, parent_id, deps)

    def get_ready_tasks(self, parent_id: str = None) -> List[NexusTaskNode]:
        """掃描特定層級（或全局）的「Ready」任務，支援 v21-A 物理派發。"""
        ready = []
        completed_ids = {n_id for n_id, n in self.nodes.items() if n.status == "completed"}
        
        for n_id, node in self.nodes.items():
            if node.status != "pending": continue
            if node.parent_id != parent_id: continue
            
            if all(dep in completed_ids for dep in node.dependencies):
                # 🛡️ v21-A Check: 延遲感知預檢
                if parent_id and self.nodes[parent_id].status != "running":
                    continue
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
